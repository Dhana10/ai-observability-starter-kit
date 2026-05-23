#!/usr/bin/env python3
"""Generate the agent observability Grafana dashboard with proper templating."""

import json
from pathlib import Path

def create_dashboard():
    """Create the complete dashboard configuration."""
    dashboard = {
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": "-- Grafana --",
                    "enable": True,
                    "hide": True,
                    "iconColor": "rgba(0, 211, 255, 1)",
                    "name": "Annotations & Alerts",
                    "type": "dashboard"
                }
            ]
        },
        "description": "Agent Observability Dashboard - GenAI Agent Operations, Token Usage, and Model Performance",
        "editable": True,
        "gnetId": None,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "panels": [
            # Stat panels (8 total)
            {
                "datasource": "Azure Monitor",
                "description": "Total number of agent invocations",
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "thresholds"},
                        "mappings": [],
                        "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]},
                        "unit": "short"
                    },
                    "overrides": []
                },
                "gridPos": {"h": 4, "w": 3, "x": 0, "y": 0},
                "id": 2,
                "options": {
                    "colorMode": "background",
                    "graphMode": "none",
                    "justifyMode": "auto",
                    "orientation": "auto",
                    "reduceOptions": {"calcs": ["lastNotNull"], "values": False},
                    "textMode": "auto"
                },
                "targets": [
                    {
                        "azureLogAnalytics": {
                            "query": "AppRequests\n| where TimeGenerated > ago(24h)\n| where name contains \"invoke_agent\"\n| summarize total=count()"
                        },
                        "datasource": "Azure Monitor",
                        "queryType": "Azure Log Analytics"
                    }
                ],
                "title": "Total Operations",
                "type": "stat"
            },
            # ... (continuing with other stat panels)
        ],
        "refresh": "30s",
        "schemaVersion": 38,
        "style": "dark",
        "tags": ["agent-observability", "genai", "foundry", "GrafanaDashboardResourceType=microsoft.insights/components"],
        "templating": {
            "list": [
                {
                    "current": {"selected": False, "text": "", "value": ""},
                    "description": None,
                    "error": None,
                    "hide": 0,
                    "includeAll": False,
                    "label": "Subscription",
                    "multi": False,
                    "name": "subscription",
                    "options": [],
                    "query": "subscriptions()",
                    "refresh": 1,
                    "regex": "",
                    "skipUrlSync": False,
                    "sort": 1,
                    "type": "query"
                },
                {
                    "current": {"selected": False, "text": "", "value": ""},
                    "description": None,
                    "error": None,
                    "hide": 0,
                    "includeAll": False,
                    "label": "Resource Group",
                    "multi": False,
                    "name": "resourceGroup",
                    "options": [],
                    "query": "resourcegroups()",
                    "refresh": 1,
                    "regex": "",
                    "skipUrlSync": False,
                    "sort": 1,
                    "type": "query"
                },
                {
                    "current": {"selected": False, "text": "", "value": ""},
                    "description": None,
                    "error": None,
                    "hide": 0,
                    "includeAll": False,
                    "label": "Resource",
                    "multi": False,
                    "name": "resource",
                    "options": [],
                    "query": "resources()",
                    "refresh": 1,
                    "regex": "/Microsoft.Insights/components",
                    "skipUrlSync": False,
                    "sort": 1,
                    "type": "query"
                }
            ]
        },
        "time": {"from": "now-24h", "to": "now"},
        "timepicker": {
            "refresh_intervals": ["10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"]
        },
        "timezone": "browser",
        "title": "Agent Observability Dashboard",
        "uid": "agent-observability-custom",
        "version": 2
    }
    return dashboard

if __name__ == '__main__':
    dashboard_path = Path(__file__).parent.parent / 'artifacts' / 'grafana' / 'agent-observability-dashboard.json'
    
    print(f"Reading existing dashboard from: {dashboard_path}")
    
    if not dashboard_path.exists():
        print(f"ERROR: Dashboard file not found")
        exit(1)
    
    # Read existing dashboard to preserve panels
    with open(dashboard_path, 'r') as f:
        existing = json.load(f)
    
    # Update the schema with proper templating
    existing['templating'] = {
        "list": [
            {
                "current": {"selected": False, "text": "", "value": ""},
                "description": None,
                "error": None,
                "hide": 0,
                "includeAll": False,
                "label": "Subscription",
                "multi": False,
                "name": "subscription",
                "options": [],
                "query": "subscriptions()",
                "refresh": 1,
                "regex": "",
                "skipUrlSync": False,
                "sort": 1,
                "type": "query"
            },
            {
                "current": {"selected": False, "text": "", "value": ""},
                "description": None,
                "error": None,
                "hide": 0,
                "includeAll": False,
                "label": "Resource Group",
                "multi": False,
                "name": "resourceGroup",
                "options": [],
                "query": "resourcegroups()",
                "refresh": 1,
                "regex": "",
                "skipUrlSync": False,
                "sort": 1,
                "type": "query"
            },
            {
                "current": {"selected": False, "text": "", "value": ""},
                "description": None,
                "error": None,
                "hide": 0,
                "includeAll": False,
                "label": "Resource",
                "multi": False,
                "name": "resource",
                "options": [],
                "query": "resources()",
                "refresh": 1,
                "regex": "/Microsoft.Insights/components",
                "skipUrlSync": False,
                "sort": 1,
                "type": "query"
            }
        ]
    }
    
    # Update schema version and version
    existing['schemaVersion'] = 38
    existing['version'] = 2
    existing['refresh'] = '30s'
    existing['timezone'] = 'browser'
    existing['timepicker'] = {
        "refresh_intervals": ["10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"]
    }
    
    # Ensure all stat panels have colorMode
    for panel in existing.get('panels', []):
        if panel.get('type') == 'stat':
            if 'options' not in panel:
                panel['options'] = {}
            if 'colorMode' not in panel.get('options', {}):
                panel['options']['colorMode'] = 'background'
            # Ensure other options are set
            panel['options']['graphMode'] = panel['options'].get('graphMode', 'none')
            panel['options']['justifyMode'] = panel['options'].get('justifyMode', 'auto')
            panel['options']['orientation'] = panel['options'].get('orientation', 'auto')
            panel['options']['textMode'] = panel['options'].get('textMode', 'auto')
            if 'reduceOptions' not in panel['options']:
                panel['options']['reduceOptions'] = {
                    "calcs": ["lastNotNull"],
                    "values": False
                }
    
    # Write updated dashboard
    with open(dashboard_path, 'w') as f:
        json.dump(existing, f, indent=2)
    
    print(f"✓ Dashboard updated successfully!")
    print(f"  - Added 3 template variables (subscription, resourceGroup, resource)")
    print(f"  - Updated schema version to 38")
    print(f"  - Added color mode to all stat panels")
    print(f"  - File saved to: {dashboard_path}")
