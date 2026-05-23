#!/usr/bin/env python3
"""
Fix datasource configuration for Azure Monitor embedded Grafana.

The issue is the datasource type. Embedded Grafana expects specific type names.
Try using datasource variables and remove custom datasource definitions.
"""

import json

dashboard_path = 'artifacts/grafana/agent-observability-dashboard.json'

with open(dashboard_path, 'r') as f:
    dashboard = json.load(f)

# Remove datasources section - let embedded Grafana use its built-in Azure Monitor
if 'datasources' in dashboard:
    del dashboard['datasources']
    print("✓ Removed custom datasource definitions")

# Add datasource template variable to templating
templating = dashboard.get('templating', {})
list_vars = templating.get('list', [])

# Check if datasource variable already exists
datasource_var_exists = any(v.get('name') == 'datasource' for v in list_vars)

if not datasource_var_exists:
    # Add datasource variable
    datasource_var = {
        "name": "datasource",
        "type": "datasource",
        "datasource": "prometheus",
        "current": {
            "value": "Azure Monitor",
            "text": "Azure Monitor"
        },
        "options": []
    }
    list_vars.insert(0, datasource_var)
    print("✓ Added datasource template variable")
else:
    print("- Datasource variable already exists")

# Update all targets to use datasource variable
fixed_count = 0
for panel in dashboard.get('panels', []):
    for target in panel.get('targets', []):
        if target.get('datasource') == 'Azure Monitor':
            target['datasource'] = '${datasource}'
            fixed_count += 1

print(f"✓ Updated {fixed_count} targets to use datasource variable")

# Save
with open(dashboard_path, 'w') as f:
    json.dump(dashboard, f, indent=2)

print("\n✓ Dashboard reconfigured for embedded Grafana")
print("  - Removed custom datasource definitions")
print("  - Using embedded Grafana's Azure Monitor datasource")
print("  - All targets now use ${datasource} variable")
