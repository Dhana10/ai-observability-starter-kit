#!/usr/bin/env python3
"""
Simplest fix: Remove datasource references entirely.

Embedded Grafana already has Azure Monitor datasource.
Just let it use the default.
"""

import json

dashboard_path = 'artifacts/grafana/agent-observability-dashboard.json'

with open(dashboard_path, 'r') as f:
    dashboard = json.load(f)

# Remove datasource definitions entirely
if 'datasources' in dashboard:
    del dashboard['datasources']
    print("✓ Removed datasource definitions")

# Remove datasource references from all targets
removed_count = 0
for panel in dashboard.get('panels', []):
    for target in panel.get('targets', []):
        if 'datasource' in target:
            del target['datasource']
            removed_count += 1

print(f"✓ Removed {removed_count} datasource references from targets")

with open(dashboard_path, 'w') as f:
    json.dump(dashboard, f, indent=2)

print("\n✓ Dashboard simplified for embedded Grafana")
print("  - No datasource definitions")
print("  - No datasource references in targets")
print("  - Will use embedded Grafana's default Azure Monitor datasource")
