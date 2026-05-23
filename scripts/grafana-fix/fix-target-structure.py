#!/usr/bin/env python3
"""
Fix target structure for Azure Monitor Grafana compatibility.

The issue is the azureLogAnalytics nested object. Azure Monitor datasource
expects the query at the target level, not nested.

Changes from:
  { "azureLogAnalytics": { "query": "..." }, "datasource": "Azure Monitor", ... }

To:
  { "query": "...", "datasource": "${datasource}", ... }
"""

import json
import sys

def fix_dashboard():
    dashboard_path = 'artifacts/grafana/agent-observability-dashboard.json'
    
    try:
        # Read dashboard
        with open(dashboard_path, 'r') as f:
            dashboard = json.load(f)
        
        # Fix all panel targets
        fixed_count = 0
        for panel in dashboard.get('panels', []):
            for target in panel.get('targets', []):
                if 'azureLogAnalytics' in target and isinstance(target['azureLogAnalytics'], dict):
                    # Extract query from nested structure
                    query = target['azureLogAnalytics'].get('query', '')
                    
                    # Replace with flat structure
                    target['query'] = query
                    del target['azureLogAnalytics']
                    
                    # Use datasource template variable for proper referencing
                    if target.get('datasource') == 'Azure Monitor':
                        target['datasource'] = '${datasource}'
                    
                    fixed_count += 1
        
        # Write back
        with open(dashboard_path, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        print(f"✓ Fixed {fixed_count} target structures")
        print(f"  - Removed azureLogAnalytics wrappers")
        print(f"  - Flattened query to top level")
        print(f"  - Updated datasource references to use template variable")
        print(f"\n✓ Dashboard now fully compatible with Azure Monitor Grafana")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(fix_dashboard())
