"""Create scheduled query alerts via ARM REST (CLI extension is broken)."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

from dotenv import load_dotenv

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
ARTIFACTS = ROOT / "artifacts"

# Discover the active azd env directory dynamically.
_azd_base = ROOT / "agent" / ".azure"
_env_name = os.environ.get("AZURE_ENV_NAME", "")
if not _env_name:
    # Fall back to azd's tracked default env from config.json
    _config = _azd_base / "config.json"
    if _config.exists():
        try:
            import json as _json
            _env_name = _json.loads(_config.read_text()).get("defaultEnvironment", "")
        except Exception:
            _env_name = ""
if _env_name and (_azd_base / _env_name / ".env").exists():
    AZD_ENV = _azd_base / _env_name / ".env"
else:
    # Fall back to the first env directory that contains a .env file.
    AZD_ENV = next(
        (p for p in sorted(_azd_base.iterdir()) if p.is_dir() and (p / ".env").exists()),
        _azd_base / "default" / ".env",
    )

API = "2023-03-15-preview"


def _az(*args, capture=True):
    res = subprocess.run(["az", *args], capture_output=capture, text=True, shell=True)
    if res.returncode != 0:
        raise RuntimeError(f"az {args} failed: {res.stderr}")
    return res.stdout.strip()


def _rest(method, url, body=None):
    cmd = ["az", "rest", "--method", method, "--url", url]
    if body is not None:
        body_path = ARTIFACTS / "_rest_body.json"
        body_path.write_text(json.dumps(body))
        cmd += ["--body", f"@{body_path}"]
    res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if res.returncode != 0:
        raise RuntimeError(f"rest {method} {url} failed: {res.stderr}\nbody={json.dumps(body, indent=2)}")
    return json.loads(res.stdout) if res.stdout.strip() else {}


def alert(name, query, severity, sub, rg, loc, scope, ag_id, description):
    url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Insights/scheduledQueryRules/{name}?api-version={API}"
    )
    body = {
        "location": loc,
        "properties": {
            "displayName": name,
            "description": description,
            "severity": severity,
            "enabled": True,
            "evaluationFrequency": "PT5M",
            "windowSize": "PT15M",
            "scopes": [scope],
            "targetResourceTypes": ["Microsoft.Insights/components"],
            "criteria": {
                "allOf": [
                    {
                        "query": query,
                        "timeAggregation": "Count",
                        "operator": "GreaterThan",
                        "threshold": 0,
                        "failingPeriods": {
                            "numberOfEvaluationPeriods": 1,
                            "minFailingPeriodsToAlert": 1,
                        },
                    }
                ]
            },
            "actions": {
                "actionGroups": [ag_id],
                "customProperties": {},
            },
            "autoMitigate": True,
        },
    }
    return _rest("PUT", url, body)


def main() -> int:
    if AZD_ENV.exists():
        load_dotenv(AZD_ENV)
    load_dotenv()

    sub = os.environ["AZURE_SUBSCRIPTION_ID"]
    rg = os.environ["AZURE_RESOURCE_GROUP"]
    loc = os.environ.get("AZURE_LOCATION", "eastus2")

    # Discover the App Insights resource dynamically (works on any deployment).
    appi_id = _az(
        "resource", "list", "-g", rg, "--resource-type",
        "Microsoft.Insights/components", "--query", "[0].id", "-o", "tsv",
    )

    # Create the action group if it does not exist (silent: no receivers).
    try:
        ag_id = _az(
            "monitor", "action-group", "show", "-g", rg, "-n", "ag-aiobs-silent",
            "--query", "id", "-o", "tsv",
        )
    except RuntimeError:
        print("Action group not found, creating ag-aiobs-silent...")
        _az(
            "monitor", "action-group", "create", "-g", rg, "-n", "ag-aiobs-silent",
            "--short-name", "aiobs-sil", "--location", "global",
        )
        ag_id = _az(
            "monitor", "action-group", "show", "-g", rg, "-n", "ag-aiobs-silent",
            "--query", "id", "-o", "tsv",
        )
    print(f"appi_id: {appi_id}")
    print(f"ag_id:   {ag_id}")

    err_kql = (
        'requests | where timestamp > ago(15m) '
        '| where name has "invoke_agent" | where success == false '
        '| summarize n = count() | where n > 0'
    )
    lat_kql = (
        'requests | where timestamp > ago(15m) '
        '| where name has "invoke_agent" '
        '| summarize p95 = percentile(duration, 95) | where p95 > 30000'
    )

    rules = {
        "alert-gen-ai-errors-15m": (err_kql, 2, "invoke_agent failure count > 0 in last 15m"),
        "alert-gen-ai-p95-latency-15m": (lat_kql, 3, "invoke_agent p95 latency > 30s in last 15m"),
    }
    created = {}
    for name, (kql, sev, desc) in rules.items():
        print(f"\ncreating {name} (sev={sev})")
        res = alert(name, kql, sev, sub, rg, loc, appi_id, ag_id, desc)
        created[name] = {"id": res.get("id"), "provisioningState": res.get("properties", {}).get("provisioningState")}
        print(f"  -> {created[name]}")

    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "alerts.json").write_text(json.dumps(created, indent=2))

    # Verify list
    list_url = (
        f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.Insights/scheduledQueryRules?api-version={API}"
    )
    listing = _rest("GET", list_url)
    print(f"\ntotal rules in RG: {len(listing.get('value', []))}")
    for r in listing.get("value", []):
        p = r.get("properties", {})
        print(f"  - {r['name']} sev={p.get('severity')} enabled={p.get('enabled')} actions={[ag.split('/')[-1] for ag in p.get('actions', {}).get('actionGroups', [])]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
