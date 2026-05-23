#!/usr/bin/env python3
"""
Fix datasource references in targets for Azure Monitor Grafana.

Ensures all target datasource references are set to "Azure Monitor" 
(the actual datasource in embedded Grafana).
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
                # Set datasource to "Azure Monitor" for all targets
                if target.get('datasource') != 'Azure Monitor':
                    target['datasource'] = 'Azure Monitor'
                    fixed_count += 1
        
        # Write back
        with open(dashboard_path, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        print(f"✓ Updated {fixed_count} target datasources to 'Azure Monitor'")
        print(f"\n✓ Dashboard ready for Azure Monitor Grafana import")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(fix_dashboard())
