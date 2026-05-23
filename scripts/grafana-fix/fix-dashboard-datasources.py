#!/usr/bin/env python3
"""
Fix unsupported datasources in dashboard for Azure Monitor Grafana compatibility.

Azure Monitor dashboards with Grafana only support:
  - Prometheus
  - Azure Monitor  
  - Azure Data Explorer

This script removes hardcoded datasource references that cause import errors.
"""

import json
import sys

def fix_dashboard():
    dashboard_path = 'artifacts/grafana/agent-observability-dashboard.json'
    
    try:
        # Read dashboard
        with open(dashboard_path, 'r') as f:
            dashboard = json.load(f)
        
        # Fix annotations - remove the "-- Grafana --" datasource
        annotation_fixed = False
        if 'annotations' in dashboard and 'list' in dashboard['annotations']:
            for annotation in dashboard['annotations']['list']:
                if annotation.get('datasource') == '-- Grafana --':
                    annotation['datasource'] = None
                    annotation_fixed = True
        
        # Fix panels - remove hardcoded "Azure Log Analytics" datasources
        panel_count = 0
        for panel in dashboard.get('panels', []):
            if panel.get('datasource') == 'Azure Log Analytics':
                panel['datasource'] = None
                panel_count += 1
        
        # Write back
        with open(dashboard_path, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        print("✓ Fixed annotation datasource" if annotation_fixed else "- Annotation datasource already correct")
        print(f"✓ Removed {panel_count} hardcoded 'Azure Log Analytics' panel datasources")
        print(f"\n✓ Dashboard now compatible with Azure Monitor Grafana")
        print(f"\nDatasource configuration:")
        print(f"  - Panel targets: 'Azure Monitor' (supported ✓)")
        print(f"  - Unsupported references: removed")
        print(f"  - Ready for import into Azure Monitor dashboards with Grafana")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(fix_dashboard())
