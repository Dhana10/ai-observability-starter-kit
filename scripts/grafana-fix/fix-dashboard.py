#!/usr/bin/env python3
"""Fix the dashboard datasource and tag issues."""

import json
from pathlib import Path

def fix_dashboard():
    """Fix datasource references and add missing tags."""
    dashboard_path = Path(__file__).parent.parent / 'artifacts' / 'grafana' / 'agent-observability-dashboard.json'
    
    print("Fixing dashboard issues...")
    
    with open(dashboard_path, 'r') as f:
        dashboard = json.load(f)
    
    # Fix datasource references in all panels
    panels_fixed = 0
    for panel in dashboard.get('panels', []):
        for target in panel.get('targets', []):
            if target.get('datasource') == 'Azure Log Analytics':
                target['datasource'] = 'Azure Monitor'
                panels_fixed += 1
    
    # Add missing tag if not present
    tags = dashboard.get('tags', [])
    if 'GrafanaDashboardResourceType=microsoft.insights/components' not in tags:
        tags.append('GrafanaDashboardResourceType=microsoft.insights/components')
        dashboard['tags'] = tags
    
    # Write back
    with open(dashboard_path, 'w') as f:
        json.dump(dashboard, f, indent=2)
    
    print(f"✓ Fixed {panels_fixed} panel datasource references")
    print(f"✓ Added Grafana gallery tag")
    print(f"✓ Dashboard saved to: {dashboard_path}")

if __name__ == '__main__':
    fix_dashboard()
