#!/usr/bin/env python3
"""Comprehensive validation that the dashboard is ready for import into Grafana."""

import json
from pathlib import Path
from typing import Dict, List, Tuple

def validate_panels(panels: List[Dict]) -> Tuple[bool, List[str]]:
    """Validate all panels are properly configured."""
    issues = []
    
    expected_panels = {
        'Total Operations': 'stat',
        'Total Input Tokens': 'stat',
        'Total Output Tokens': 'stat',
        'Avg Response Time': 'stat',
        'LLM Calls': 'stat',
        'Chat Sessions': 'stat',
        'Tool Calls': 'stat',
        'Avg TTFT': 'stat',
        'Operations Over Time': 'timeseries',
        'Token Consumption Over Time by Model': 'timeseries',
        'Model Usage Distribution': 'piechart',
        'Response Duration by Model (Avg / P90)': 'barchart',
        'Time First Token by Model (P50 / P90)': 'barchart',
    }
    
    found_panels = {p.get('title'): p.get('type') for p in panels}
    
    for expected_title, expected_type in expected_panels.items():
        if expected_title not in found_panels:
            issues.append(f"Missing panel: {expected_title}")
        elif found_panels[expected_title] != expected_type:
            issues.append(f"Panel '{expected_title}' has type '{found_panels[expected_title]}', expected '{expected_type}'")
    
    # Validate gridPos for all panels
    for panel in panels:
        title = panel.get('title', 'Unknown')
        if 'gridPos' not in panel:
            issues.append(f"Panel '{title}' missing gridPos")
        elif not all(k in panel['gridPos'] for k in ['h', 'w', 'x', 'y']):
            issues.append(f"Panel '{title}' has incomplete gridPos")
    
    # Validate data sources
    for panel in panels:
        title = panel.get('title', 'Unknown')
        if 'targets' in panel and panel['targets']:
            for target in panel['targets']:
                if target.get('datasource') != 'Azure Monitor':
                    issues.append(f"Panel '{title}' uses datasource '{target.get('datasource')}', expected 'Azure Monitor'")
    
    return len(issues) == 0, issues

def validate_queries(panels: List[Dict]) -> Tuple[bool, List[str]]:
    """Validate KQL queries are present and properly formatted."""
    issues = []
    query_count = 0
    
    for panel in panels:
        if 'targets' not in panel:
            continue
        
        for target in panel.get('targets', []):
            # Check for query in new flat structure or old nested structure
            query = target.get('query', '')
            if not query and 'azureLogAnalytics' in target:
                query = target['azureLogAnalytics'].get('query', '')
            
            if query:
                query_count += 1
                
                if not query.strip():
                    issues.append(f"Empty query in panel '{panel.get('title')}'")
                elif 'where TimeGenerated' not in query:
                    issues.append(f"Panel '{panel.get('title')}' query missing TimeGenerated filter")
    
    if query_count < 13:
        issues.append(f"Expected 13 queries, found {query_count}")
    
    return len(issues) == 0, issues

def validate_schema(dashboard: Dict) -> Tuple[bool, List[str]]:
    """Validate dashboard schema and metadata."""
    issues = []
    
    # Check version
    if dashboard.get('schemaVersion') != 38:
        issues.append(f"Schema version is {dashboard.get('schemaVersion')}, expected 38")
    
    # Check required fields
    required = ['title', 'uid', 'panels', 'templating', 'time']
    for field in required:
        if field not in dashboard:
            issues.append(f"Missing required field: {field}")
    
    # Validate templating
    templating = dashboard.get('templating', {}).get('list', [])
    expected_vars = ['subscription', 'resourceGroup', 'resource']
    found_vars = [v.get('name') for v in templating]
    
    for var in expected_vars:
        if var not in found_vars:
            issues.append(f"Missing template variable: {var}")
    
    # Check tags
    tags = dashboard.get('tags', [])
    if 'agent-observability' not in tags:
        issues.append("Missing 'agent-observability' tag")
    if 'GrafanaDashboardResourceType=microsoft.insights/components' not in tags:
        issues.append("Missing Grafana gallery tag")
    
    return len(issues) == 0, issues

def main():
    """Run comprehensive validation."""
    dashboard_path = Path(__file__).parent.parent / 'artifacts' / 'grafana' / 'agent-observability-dashboard.json'
    
    print("=" * 70)
    print("AGENT OBSERVABILITY DASHBOARD - IMPORT READINESS CHECK")
    print("=" * 70)
    
    try:
        with open(dashboard_path, 'r') as f:
            dashboard = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load dashboard: {e}")
        return False
    
    print(f"\nDashboard: {dashboard.get('title')}")
    print(f"UID: {dashboard.get('uid')}")
    print(f"Version: {dashboard.get('version')}")
    print(f"Schema: {dashboard.get('schemaVersion')}")
    print()
    
    # Run all validations
    all_pass = True
    
    # 1. Schema validation
    print("[1/4] Validating schema and metadata...")
    schema_pass, schema_issues = validate_schema(dashboard)
    if schema_pass:
        print("  ✓ Schema valid")
    else:
        print("  ✗ Schema issues found:")
        for issue in schema_issues:
            print(f"    - {issue}")
        all_pass = False
    print()
    
    # 2. Panel validation
    print("[2/4] Validating panels...")
    panels_pass, panel_issues = validate_panels(dashboard.get('panels', []))
    if panels_pass:
        print(f"  ✓ All 13 panels valid")
    else:
        print("  ✗ Panel issues found:")
        for issue in panel_issues:
            print(f"    - {issue}")
        all_pass = False
    print()
    
    # 3. Query validation
    print("[3/4] Validating KQL queries...")
    query_pass, query_issues = validate_queries(dashboard.get('panels', []))
    if query_pass:
        print(f"  ✓ All 13 queries present and valid")
    else:
        print("  ✗ Query issues found:")
        for issue in query_issues:
            print(f"    - {issue}")
        all_pass = False
    print()
    
    # 4. Import readiness
    print("[4/4] Import readiness check...")
    if all_pass:
        print("  ✓ Dashboard is ready for import")
        print()
        print("NEXT STEPS:")
        print("1. Open Azure Portal > Application Insights > Dashboards with Grafana")
        print("2. Click New > Import")
        print("3. Upload: artifacts/grafana/agent-observability-dashboard.json")
        print("4. Select subscription, resource group, and App Insights resource")
        print("5. Click Import")
        print()
        print("For detailed import instructions, see: artifacts/grafana/DASHBOARD_IMPORT_GUIDE.md")
        return True
    else:
        print("  ✗ Dashboard has issues and needs fixes before import")
        return False
    
    print("=" * 70)

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
