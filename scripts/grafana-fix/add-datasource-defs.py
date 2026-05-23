#!/usr/bin/env python3
"""
Add datasource definitions to dashboard for Azure Monitor Grafana compatibility.

Azure Monitor embedded Grafana requires datasource definitions in the dashboard
for all datasources referenced by panels and targets.
"""

import json

def fix_datasources():
    dashboard_path = 'artifacts/grafana/agent-observability-dashboard.json'
    
    with open(dashboard_path, 'r') as f:
        dashboard = json.load(f)
    
    # Add datasource definitions array if missing
    if 'datasources' not in dashboard:
        dashboard['datasources'] = []
    
    # Check if Azure Monitor datasource already exists
    azure_monitor_exists = any(
        ds.get('name') == 'Azure Monitor' or ds.get('type') == 'grafana-azure-monitor-datasource'
        for ds in dashboard['datasources']
    )
    
    if not azure_monitor_exists:
        # Add Azure Monitor datasource definition
        # This is the format used in App Insights embedded Grafana
        azure_monitor_ds = {
            "name": "Azure Monitor",
            "type": "grafana-azure-monitor-datasource",
            "uid": "azure-monitor-uid",
            "access": "proxy",
            "isDefault": True,
            "jsonData": {
                "subscriptionId": "${subscription}"
            }
        }
        dashboard['datasources'].append(azure_monitor_ds)
        print("✓ Added Azure Monitor datasource definition")
    else:
        print("- Azure Monitor datasource already defined")
    
    # Save dashboard
    with open(dashboard_path, 'w') as f:
        json.dump(dashboard, f, indent=2)
    
    print(f"✓ Dashboard now has {len(dashboard['datasources'])} datasource(s)")
    print("\n✓ Datasources section properly configured")
    print("  - Azure Monitor datasource defined and ready")
    print("  - All targets can now reference this datasource")

if __name__ == '__main__':
    fix_datasources()
