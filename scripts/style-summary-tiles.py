"""Replace the 8 individual summary stat panels with 2 multi-target Stat
panels. Each consolidated Stat panel renders 4 colored tiles INSIDE its own
container, with the group title ('Agent Summary Statistics' / 'Chat & Tool
Summary') displayed in the panel's title bar.

Idempotent: removes any prior summary panels (ids 2-9 and 1001-1002) before
inserting the new consolidated ones.
"""
from __future__ import annotations

import json
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "artifacts" / "grafana" / "agent-observability-dashboard.json"

# Old per-tile stat panels + any previously injected text headers.
OLD_IDS = {2, 3, 4, 5, 6, 7, 8, 9, 1001, 1002}

DS = {"type": "grafana-azure-monitor-datasource", "uid": "${ds_azmon}"}


def target(ref_id: str, name: str, query: str) -> dict:
    # Rename the scalar 'total' column to the display name so the Stat panel
    # renders one tile labeled exactly with that name.
    wrapped = f"{query.rstrip()}\n| project [\"{name}\"] = todouble(total)"
    return {
        "datasource": DS,
        "azureLogAnalytics": {
            "query": wrapped,
            "resources": ["${appi_resource}"],
            "resultFormat": "table",
        },
        "queryType": "Azure Log Analytics",
        "refId": ref_id,
        "subscription": "${subscription}",
    }


def override(field_name: str, color: str, unit: str) -> dict:
    return {
        "matcher": {"id": "byName", "options": field_name},
        "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": color}},
            {"id": "displayName", "value": field_name},
            {"id": "unit", "value": unit},
            {
                "id": "thresholds",
                "value": {
                    "mode": "absolute",
                    "steps": [{"color": color, "value": None}],
                },
            },
        ],
    }


def build_group(panel_id: int, title: str, description: str, x: int,
                tiles: list[tuple[str, str, str, str, str]]) -> dict:
    """tiles = list of (refId, display_name, color, unit, query)."""
    overrides = [override(name, color, unit) for _r, name, color, unit, _q in tiles]
    targets = [target(r, name, q) for r, name, _c, _u, q in tiles]
    return {
        "type": "stat",
        "title": title,
        "description": description,
        "datasource": DS,
        "gridPos": {"h": 7, "w": 12, "x": x, "y": 0},
        "id": panel_id,
        "pluginVersion": "8.0.0",
        "fieldConfig": {
            "defaults": {
                "color": {"mode": "thresholds"},
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": "blue", "value": None}],
                },
                "unit": "short",
            },
            "overrides": overrides,
        },
        "options": {
            "graphMode": "none",
            "orientation": "vertical",
            "textMode": "value_and_name",
            "colorMode": "background",
            "justifyMode": "center",
            "reduceOptions": {
                "values": False,
                "calcs": ["lastNotNull"],
                "fields": "",
            },
        },
        "targets": targets,
    }


AGENT_TILES = [
    ("A", "Total Operations", "blue", "short",
     "requests\n| where timestamp > ago(24h)\n| where name contains \"invoke_agent\"\n| summarize total=count()"),
    ("B", "Total Input Tokens", "purple", "short",
     "dependencies\n| where timestamp > ago(24h)\n| where name startswith \"chat \"\n| extend input_tokens = todouble(customDimensions[\"gen_ai.usage.input_tokens\"])\n| summarize total=sum(input_tokens)"),
    ("C", "Total Output Tokens", "green", "short",
     "dependencies\n| where timestamp > ago(24h)\n| where name startswith \"chat \"\n| extend output_tokens = todouble(customDimensions[\"gen_ai.usage.output_tokens\"])\n| summarize total=sum(output_tokens)"),
    ("D", "Avg Response Time", "orange", "ms",
     "requests\n| where timestamp > ago(24h)\n| where name contains \"invoke_agent\"\n| summarize total=avg(duration)"),
]

CHAT_TILES = [
    ("A", "LLM Calls", "blue", "short",
     "dependencies\n| where timestamp > ago(24h)\n| where name startswith \"chat \"\n| summarize total=count()"),
    ("B", "Chat Sessions", "green", "short",
     "requests\n| where timestamp > ago(24h)\n| where name contains \"invoke_agent\"\n| extend session_id = tostring(customDimensions[\"gen_ai.conversation.id\"])\n| where isnotempty(session_id)\n| summarize total=dcount(session_id)"),
    ("C", "Tool Calls", "purple", "short",
     "dependencies\n| where timestamp > ago(24h)\n| where name startswith \"execute_tool\"\n| summarize total=count()"),
    ("D", "Avg Chat Latency", "orange", "ms",
     "dependencies\n| where timestamp > ago(24h)\n| where name startswith \"chat \"\n| summarize total=avg(duration)"),
]


def main() -> None:
    dash = json.loads(DASH.read_text(encoding="utf-8"))
    panels = [p for p in dash["panels"] if p.get("id") not in OLD_IDS]

    agent_group = build_group(
        1001, "Agent Summary Statistics",
        "Top-level counters for agent invocations across the selected time range.",
        0, AGENT_TILES,
    )
    chat_group = build_group(
        1002, "Chat & Tool Summary",
        "Chat session, LLM call, and tool execution counters.",
        12, CHAT_TILES,
    )

    # Keep the other panels positioned just below the 7-row header band.
    min_y = min((p["gridPos"]["y"] for p in panels if p.get("gridPos")), default=7)
    if min_y != 7:
        delta = 7 - min_y
        for p in panels:
            gp = p.get("gridPos")
            if gp:
                gp["y"] = int(gp.get("y", 0)) + delta

    dash["panels"] = [agent_group, chat_group, *panels]
    DASH.write_text(json.dumps(dash, indent=2), encoding="utf-8")
    print(f"Updated {DASH}")
    print(f"  - Inserted consolidated panels 1001 + 1002 (h=7, w=12)")
    print(f"  - Removed old panels {sorted(OLD_IDS)}")
    print(f"  - Other panels: {len(panels)} (previous min y = {min_y})")


if __name__ == "__main__":
    main()
