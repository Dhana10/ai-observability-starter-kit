#!/usr/bin/env python3
import json

with open('artifacts/grafana/agent-observability-dashboard.json', 'r') as f:
    dashboard = json.load(f)

# Pre-fill all template variables with defaults
for var in dashboard['templating']['list']:
    name = var.get('name')
    
    if name == 'ds_azmon':
        # Datasource variable - keep as is
        var['current'] = {
            'selected': True,
            'text': 'grafana-azure-monitor-datasource',
            'value': 'grafana-azure-monitor-datasource'
        }
    
    elif name == 'datasource':
        var['current'] = {
            'selected': True,
            'text': 'Azure Monitor',
            'value': 'Azure Monitor'
        }
        var['options'] = [
            {
                'selected': True,
                'text': 'Azure Monitor',
                'value': 'Azure Monitor'
            }
        ]
    
    elif name == 'subscription':
        # Don't set a default - user must choose
        var['current'] = {'text': '', 'value': ''}
        var['hide'] = 0  # Make visible so user can select
    
    elif name == 'appi_resource':
        var['current'] = {
            'selected': True,
            'text': 'your-app-insights-resource-id',
            'value': 'your-app-insights-resource-id'
        }
        var['hide'] = 0  # Make visible

with open('artifacts/grafana/agent-observability-dashboard.json', 'w') as f:
    json.dump(dashboard, f, indent=2)

print('✓ Pre-filled all template variables')
print('  ds_azmon: grafana-azure-monitor-datasource')
print('  datasource: Azure Monitor')
print('  subscription: (user must select)')
print('  appi_resource: placeholder (user updates to real resource ID)')
