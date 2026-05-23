#!/usr/bin/env python3
"""
Auto-fill template variables to remove manual input prompts during import.

Converts query-based variables to constants or removes undefined ones.
"""

import json

dashboard_path = 'artifacts/grafana/agent-observability-dashboard.json'

with open(dashboard_path, 'r') as f:
    dashboard = json.load(f)

# Get templating list
templating = dashboard.get('templating', {})
list_vars = templating.get('list', [])

# Fix each variable
new_vars = []
for var in list_vars:
    name = var.get('name')
    
    if name == 'ds_azmon':
        # Keep datasource variable, it's correct
        new_vars.append(var)
    
    elif name == 'datasource':
        # Fix undefined datasource variable
        var.update({
            "type": "datasource",
            "datasource": "grafana-azure-monitor-datasource",
            "current": {
                "value": "Azure Monitor",
                "text": "Azure Monitor"
            },
            "options": [
                {
                    "value": "Azure Monitor",
                    "text": "Azure Monitor"
                }
            ],
            "hide": 2  # Hide from UI since it's auto-selected
        })
        new_vars.append(var)
    
    elif name == 'subscription':
        # Convert to constant with no fixed value (user's default will be used)
        var.update({
            "type": "constant",
            "hide": 2,  # Hide from UI, optional
            "current": {"text": "", "value": ""},
            "options": [{"text": "", "value": ""}],
            "query": ""
        })
        new_vars.append(var)
    
    elif name in ['resourceGroup', 'resource']:
        # Remove these - they require dynamic queries that won't work without subscription
        # Grafana will auto-resolve them if needed
        continue
    
    else:
        # Keep any other variables
        new_vars.append(var)

templating['list'] = new_vars

# Save
with open(dashboard_path, 'w') as f:
    json.dump(dashboard, f, indent=2)

print("✓ Auto-filled template variables")
print("  - ds_azmon: ready (datasource picker)")
print("  - datasource: auto-filled to 'Azure Monitor'")
print("  - subscription: simplified")
print("  - Removed dynamic resourceGroup/resource queries")
print("\n✓ Dashboard will not prompt for undefined variables on import")
