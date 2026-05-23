#!/usr/bin/env python3
import json

with open('artifacts/grafana/agent-observability-dashboard.json', 'r') as f:
    dashboard = json.load(f)

# Check if appi_resource variable already exists
existing_vars = {v.get('name'): v for v in dashboard['templating']['list']}

if 'appi_resource' not in existing_vars:
    appi_resource_var = {
        "current": {
            "selected": False,
            "text": "your-app-insights-resource-id",
            "value": "your-app-insights-resource-id"
        },
        "description": "Full Application Insights resource ID (format: /subscriptions/{subId}/resourceGroups/{rg}/providers/microsoft.insights/components/{name})",
        "hide": 0,
        "label": "Application Insights resource ID",
        "name": "appi_resource",
        "options": [
            {
                "selected": True,
                "text": "your-app-insights-resource-id",
                "value": "your-app-insights-resource-id"
            }
        ],
        "query": "",
        "skipUrlSync": False,
        "type": "constant"
    }
    
    dashboard['templating']['list'].append(appi_resource_var)
    print('✓ Added appi_resource template variable')
else:
    print('✓ appi_resource variable already exists')

with open('artifacts/grafana/agent-observability-dashboard.json', 'w') as f:
    json.dump(dashboard, f, indent=2)

print('✓ Dashboard template updated')
