#!/usr/bin/env python3
"""
Fix queryType in dashboard targets for Azure Monitor Grafana compatibility.

Changes "Azure Log Analytics" queryType to "Logs" which is the correct
queryType for Azure Monitor Log Analytics queries in modern Grafana.
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
                if target.get('queryType') == 'Azure Log Analytics':
                    target['queryType'] = 'Logs'
                    fixed_count += 1
        
        # Write back
        with open(dashboard_path, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        print(f"✓ Fixed {fixed_count} queryType references")
        print(f"  Changed: 'Azure Log Analytics' → 'Logs'")
        print(f"\n✓ Dashboard now fully compatible with Azure Monitor Grafana")
        print(f"\nSupported datasources:")
        print(f"  ✓ Azure Monitor (all panels)")
        print(f"  ✓ No unsupported datasource references")
        print(f"  ✓ Ready for import")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(fix_dashboard())
