#!/usr/bin/env python3
"""
Reformat dashboard to match working structure.

Uses the correct datasource object references and template variable approach.
"""

import json
import copy

dashboard_path = 'artifacts/grafana/agent-observability-dashboard.json'

with open(dashboard_path, 'r') as f:
    dashboard = json.load(f)

# 1. Add datasource template variable
templating = dashboard.get('templating', {})
list_vars = templating.get('list', [])

# Remove any existing datasource var
list_vars = [v for v in list_vars if v.get('name') != 'ds_azmon']

# Add proper datasource template variable at beginning
datasource_var = {
    "current": {},
    "hide": 0,
    "label": "Azure Monitor data source",
    "name": "ds_azmon",
    "options": [],
    "query": "grafana-azure-monitor-datasource",
    "refresh": 1,
    "regex": "",
    "skipUrlSync": False,
    "type": "datasource"
}
list_vars.insert(0, datasource_var)
templating['list'] = list_vars

# 2. Update all panels to use datasource object reference
for panel in dashboard.get('panels', []):
    # Set panel-level datasource to null (will inherit from targets)
    panel['datasource'] = None
    
    # Update all targets
    for target in panel.get('targets', []):
        # Set datasource as object reference
        target['datasource'] = {
            "type": "grafana-azure-monitor-datasource",
            "uid": "${ds_azmon}"
        }
        
        # Keep queryType as "Logs" (compatible with Azure Log Analytics)
        if 'queryType' not in target or target['queryType'] != 'Logs':
            target['queryType'] = 'Logs'

# 3. Add datasources section with proper format
dashboard['datasources'] = [
    {
        "type": "grafana-azure-monitor-datasource",
        "uid": "${ds_azmon}"
    }
]

# 4. Update schema version
dashboard['schemaVersion'] = 39

# Save
with open(dashboard_path, 'w') as f:
    json.dump(dashboard, f, indent=2)

print("✓ Reformatted dashboard to working structure")
print("  - Added datasource template variable (ds_azmon)")
print("  - Updated all panels to use datasource object references")
print("  - Set datasources with proper type and uid")
print("  - Updated schema to v39")
print("\n✓ Dashboard now matches working format")
