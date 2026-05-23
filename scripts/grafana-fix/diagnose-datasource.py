#!/usr/bin/env python3
"""
Diagnose datasource issues in dashboard.

Azure Monitor embedded Grafana may require datasource UIDs instead of names.
This script checks the current structure and tries alternate formats.
"""

import json

dashboard_path = 'artifacts/grafana/agent-observability-dashboard.json'

with open(dashboard_path, 'r') as f:
    dashboard = json.load(f)

print("DATASOURCE DIAGNOSTIC")
print("=" * 70)

# Check panel datasources
print("\nPanel-level datasources:")
for i, panel in enumerate(dashboard['panels'][:3]):
    ds = panel.get('datasource')
    print(f"  Panel {i+1} ({panel.get('title')}): {ds}")

# Check target datasources
print("\nTarget-level datasources (first 3):")
for i, panel in enumerate(dashboard['panels'][:3]):
    if panel.get('targets'):
        for j, target in enumerate(panel['targets']):
            ds = target.get('datasource')
            query_type = target.get('queryType')
            print(f"  Panel {i+1} Target {j+1}: datasource='{ds}', queryType='{query_type}'")

# Check for datasource definitions
print("\nDatasources defined in dashboard:")
datasources = dashboard.get('datasources', [])
if datasources:
    for ds in datasources:
        print(f"  - {ds.get('name')} (uid: {ds.get('uid')}, type: {ds.get('type')})")
else:
    print("  None defined in dashboard")

# Check templating
print("\nTemplate variables:")
templating = dashboard.get('templating', {}).get('list', [])
for var in templating:
    print(f"  - {var.get('name')}: {var.get('type')}")

print("\n" + "=" * 70)
print("SOLUTION:")
print("Azure Monitor dashboards with Grafana typically use datasource variables")
print("or UUIDs. Will attempt fix using datasource variable approach...")
