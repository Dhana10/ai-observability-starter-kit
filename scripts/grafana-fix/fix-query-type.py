#!/usr/bin/env python3
import json

with open('artifacts/grafana/agent-observability-dashboard.json', 'r') as f:
    dashboard = json.load(f)

for panel_idx, panel in enumerate(dashboard.get('panels', [])):
    if 'targets' in panel:
        for target_idx, target in enumerate(panel['targets']):
            if 'query' in target and 'azureLogAnalytics' not in target:
                query = target.pop('query')
                target.pop('queryType', None)
                target.pop('datasource', None)
                
                target['azureLogAnalytics'] = {
                    'query': query,
                    'resources': ['${appi_resource}'],
                    'resultFormat': 'time_series'
                }
                target['queryType'] = 'Azure Log Analytics'
                target['refId'] = 'A'
                target['subscription'] = '${subscription}'

# Add datasource to first panel if missing
if dashboard.get('panels'):
    dashboard['panels'][0]['datasource'] = {
        'type': 'grafana-azure-monitor-datasource',
        'uid': '${ds_azmon}'
    }

with open('artifacts/grafana/agent-observability-dashboard.json', 'w') as f:
    json.dump(dashboard, f, indent=2)

print('✓ Fixed all panel query structures')
print('✓ Changed queryType to "Azure Log Analytics"')
print('✓ Moved query into azureLogAnalytics object')
print('✓ Added refId and subscription fields')
