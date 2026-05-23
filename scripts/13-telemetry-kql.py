"""Query App Insights via the Azure Monitor Logs API and write tidy reports.

Avoids the az CLI table-format issues with JSON columns by talking directly
to the Logs Query API with azure-monitor-query.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
from datetime import timedelta

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from dotenv import load_dotenv

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
# Discover active azd env dynamically.
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
    AZD_ENV = next(
        (p / ".env" for p in sorted(_azd_base.iterdir()) if p.is_dir() and (p / ".env").exists()),
        _azd_base / "default" / ".env",
    )
ARTIFACTS = ROOT / "artifacts"

QUERIES = {
    "tc-050-volume-success": """
        requests
        | where name has "invoke_agent"
        | extend success_b = tobool(success)
        | summarize
            total = count(),
            success = countif(success_b == true),
            failed = countif(success_b == false),
            unique_traces = dcount(operation_Id)
        by name
        | order by total desc
    """,
    "tc-051-latency-percentiles-ms": """
        requests
        | where name has "invoke_agent"
        | summarize
            n = count(),
            p50_ms = round(percentile(duration, 50), 1),
            p90_ms = round(percentile(duration, 90), 1),
            p95_ms = round(percentile(duration, 95), 1),
            p99_ms = round(percentile(duration, 99), 1),
            avg_ms = round(avg(duration), 1),
            max_ms = round(max(duration), 1)
    """,
    "tc-052-by-prompt-category": """
        requests
        | where name has "invoke_agent"
        | extend session_id = tostring(parse_json(customDimensions)["microsoft.session.id"])
        | extend conv_id = tostring(parse_json(customDimensions)["gen_ai.conversation.id"])
        | summarize n = count(), p95_ms = percentile(duration, 95) by session_id, bin(timestamp, 5m)
        | order by timestamp asc
    """,
    "tc-053-token-usage": """
        requests
        | where name has "invoke_agent"
        | extend cd = parse_json(customDimensions)
        | extend input_tokens = toint(cd["gen_ai.usage.input_tokens"])
        | extend output_tokens = toint(cd["gen_ai.usage.output_tokens"])
        | summarize
            n = count(),
            with_token_attrs = countif(isnotnull(input_tokens)),
            sum_input = sum(input_tokens),
            sum_output = sum(output_tokens),
            avg_input = round(avg(input_tokens), 1),
            avg_output = round(avg(output_tokens), 1)
    """,
}


def main() -> int:
    if AZD_ENV.exists():
        load_dotenv(AZD_ENV)
    load_dotenv()

    workspace_id = os.environ.get("LOG_ANALYTICS_WORKSPACE_ID")
    appi_resource_id = os.environ.get("APPLICATIONINSIGHTS_RESOURCE_ID")
    print(f"workspace_id:  {workspace_id}")
    print(f"appi_resource_id: {appi_resource_id}")

    client = LogsQueryClient(DefaultAzureCredential())

    ARTIFACTS.mkdir(exist_ok=True)
    summary = {}
    timespan = timedelta(hours=2)
    for name, kql in QUERIES.items():
        print(f"\n=== {name} ===")
        try:
            if appi_resource_id:
                resp = client.query_resource(
                    resource_id=appi_resource_id, query=kql, timespan=timespan
                )
            else:
                resp = client.query_workspace(
                    workspace_id=workspace_id, query=kql, timespan=timespan
                )
        except Exception as exc:  # noqa: BLE001
            print(f"query error: {type(exc).__name__}: {exc}")
            summary[name] = {"error": str(exc)}
            continue
        if resp.status == LogsQueryStatus.FAILURE:
            print(f"failed: {resp.partial_error}")
            summary[name] = {"error": str(resp.partial_error)}
            continue
        tables = resp.tables if resp.status == LogsQueryStatus.SUCCESS else resp.partial_data
        rows_out = []
        for tbl in tables:
            cols = [c for c in tbl.columns]
            for row in tbl.rows:
                rows_out.append(dict(zip(cols, [_serialize(v) for v in row])))
        summary[name] = {"rows": rows_out}
        print(json.dumps(rows_out, indent=2, default=str))

    out = ARTIFACTS / "telemetry.json"
    out.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nsaved:  {out}")
    return 0


def _serialize(v):
    try:
        json.dumps(v)
        return v
    except TypeError:
        return str(v)


if __name__ == "__main__":
    sys.exit(main())
