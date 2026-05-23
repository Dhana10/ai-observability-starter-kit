#!/usr/bin/env python3
"""
Fix datasource for embedded Grafana using correct UID references.

Embedded Grafana in App Insights uses specific datasource UIDs.
"""

import json

dashboard_path = 'artifacts/grafana/agent-observability-dashboard.json'

with open(dashboard_path, 'r') as f:
    dashboard = json.load(f)

# Add proper datasource definition for embedded Grafana
dashboard['datasources'] = [
    {
        "name": "Azure Monitor",
        "type": "azure-monitor",
        "uid": "azuremonitor-uid",
        "access": "proxy",
        "isDefault": True
    }
]

# Update all targets to use datasource by reference
fixed_count = 0
for panel in dashboard.get('panels', []):
    for target in panel.get('targets', []):
        # Use datasource reference instead of name
        target['datasource'] = {
            "type": "azure-monitor",
            "uid": "azuremonitor-uid"
        }
        fixed_count += 1

print(f"✓ Updated {fixed_count} targets")
print("✓ Using proper Azure Monitor datasource references")

with open(dashboard_path, 'w') as f:
    json.dump(dashboard, f, indent=2)

print("✓ Dashboard reconfigured with correct datasource format")
