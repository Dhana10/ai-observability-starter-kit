#!/usr/bin/env python3
"""Validate the Grafana dashboard JSON for the agent observability demo."""

import json
import sys
from pathlib import Path

def validate_dashboard_json(filepath: str) -> bool:
    """Validate Grafana dashboard JSON structure and content."""
    try:
        with open(filepath, 'r') as f:
            dashboard = json.load(f)
        
        # Check required top-level fields
        required_fields = ['title', 'panels', 'schemaVersion', 'uid']
        missing = [field for field in required_fields if field not in dashboard]
        if missing:
            print(f"ERROR: Missing required fields: {missing}")
            return False
        
        print(f"✓ Dashboard title: {dashboard['title']}")
        print(f"✓ Schema version: {dashboard['schemaVersion']}")
        print(f"✓ UID: {dashboard['uid']}")
        
        # Validate panels
        panels = dashboard.get('panels', [])
        print(f"✓ Panel count: {len(panels)}")
        
        if len(panels) < 8:
            print(f"ERROR: Expected at least 8 panels, found {len(panels)}")
            return False
        
        # Check panel types
        panel_types = {}
        for idx, panel in enumerate(panels):
            ptype = panel.get('type', 'unknown')
            panel_types[ptype] = panel_types.get(ptype, 0) + 1
            
            # Verify each panel has required fields
            if 'title' not in panel:
                print(f"  ERROR: Panel {idx} missing title")
                return False
            if 'gridPos' not in panel:
                print(f"  ERROR: Panel {idx} ({panel.get('title')}) missing gridPos")
                return False
        
        print(f"✓ Panel types: {panel_types}")
        
        # Expected panel breakdown
        expected = {'stat': 8, 'timeseries': 2, 'piechart': 1, 'barchart': 2}
        for ptype, expected_count in expected.items():
            actual = panel_types.get(ptype, 0)
            if actual != expected_count:
                print(f"  WARNING: Expected {expected_count} {ptype} panels, found {actual}")
        
        # Validate stat panels have proper styling
        stat_panels = [p for p in panels if p.get('type') == 'stat']
        if stat_panels:
            print(f"✓ Stat panels: {len(stat_panels)}")
            for panel in stat_panels:
                if 'colorMode' not in panel.get('options', {}):
                    print(f"  WARNING: Stat panel '{panel.get('title')}' missing colorMode")
        
        # Validate templating
        templating = dashboard.get('templating', {}).get('list', [])
        print(f"✓ Template variables: {len(templating)}")
        for var in templating:
            print(f"  - {var.get('name')}: {var.get('type')}")
        
        # Check for proper tags
        tags = dashboard.get('tags', [])
        print(f"✓ Tags: {tags}")
        if 'agent-observability' not in tags:
            print(f"  WARNING: Missing 'agent-observability' tag")
        
        print("\n✓ Dashboard JSON is valid and properly structured!")
        return True
        
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON syntax: {e}")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == '__main__':
    dashboard_path = Path(__file__).parent.parent / 'artifacts' / 'grafana' / 'agent-observability-dashboard.json'
    
    if not dashboard_path.exists():
        print(f"ERROR: Dashboard file not found: {dashboard_path}")
        sys.exit(1)
    
    success = validate_dashboard_json(str(dashboard_path))
    sys.exit(0 if success else 1)
