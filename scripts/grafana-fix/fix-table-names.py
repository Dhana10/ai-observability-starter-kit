#!/usr/bin/env python3
import json
import re

with open('artifacts/grafana/agent-observability-dashboard.json', 'r') as f:
    dashboard = json.load(f)

# Map incorrect table names to correct ones
table_mapping = {
    'AppRequests': 'requests',
    'AppDependencies': 'dependencies',
    'AppTraces': 'traces',
    'AppMetrics': 'customMetrics',
    'AppExceptions': 'exceptions'
}

fixed_count = 0

for panel in dashboard.get('panels', []):
    if 'targets' in panel:
        for target in panel['targets']:
            if 'azureLogAnalytics' in target and 'query' in target['azureLogAnalytics']:
                query = target['azureLogAnalytics']['query']
                original_query = query
                
                # Replace table names
                for old_table, new_table in table_mapping.items():
                    # Use word boundaries to avoid partial replacements
                    query = re.sub(r'\b' + old_table + r'\b', new_table, query)
                
                if query != original_query:
                    target['azureLogAnalytics']['query'] = query
                    fixed_count += 1
                    print(f"✓ Fixed query in panel: {panel.get('title', 'Untitled')}")

with open('artifacts/grafana/agent-observability-dashboard.json', 'w') as f:
    json.dump(dashboard, f, indent=2)

print(f'\n✓ Fixed {fixed_count} queries')
print('Table name mappings applied:')
for old, new in table_mapping.items():
    print(f'  {old} → {new}')
