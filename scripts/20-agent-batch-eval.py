"""Create a one-shot batch eval run against agent traces in App Insights.

This is the canonical, reliable way to populate the Foundry portal
"Evaluations" pane for AI Agents. It creates an eval group with 5 built-in
evaluators and runs them against the agent's traces (filtered by agent_name)
using the ``azure_ai_traces_preview`` data source.

The continuous-eval rule that 10-continuous-eval.py creates is intended for
automatic evaluation of new responses but its async processor is unreliable
in the current preview. A one-shot batch over traces completes in ~1-3 min
and the run is immediately visible in the Evaluations pane.

Run:
    python scripts/20-agent-batch-eval.py

Requires AZURE_AI_PROJECT_ENDPOINT, AZURE_AI_MODEL_DEPLOYMENT_NAME, and
traces already flowing into App Insights (i.e. seed traffic has run).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
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
    AZD_ENV = next(
        (p / ".env" for p in sorted(_azd_base.iterdir()) if p.is_dir() and (p / ".env").exists()),
        _azd_base / "default" / ".env",
    )


EVALUATORS = [
    "intent_resolution",
    "task_adherence",
    "coherence",
    "fluency",
    "relevance",
]
MAX_TRACES = 20
LOOKBACK_HOURS = 2
POLL_TIMEOUT_SECONDS = 8 * 60
POLL_INTERVAL_SECONDS = 15


def _to_json(obj):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_json(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_json(v) for k, v in obj.items()}
    for m in ("model_dump", "to_dict", "as_dict", "dict"):
        if hasattr(obj, m):
            try:
                return _to_json(getattr(obj, m)())
            except Exception:  # noqa: BLE001
                pass
    return str(obj)


def main() -> int:
    if AZD_ENV.exists():
        load_dotenv(AZD_ENV)
    load_dotenv()

    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
    agent_name = os.environ.get(
        "AZURE_AI_AGENT_NAME", "agent-framework-agent-basic-responses"
    )

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    openai_client = project.get_openai_client()

    print(f"agent:        {agent_name}")
    print(f"deployment:   {deployment}")
    print(f"evaluators:   {', '.join(EVALUATORS)}")
    print(f"data source:  azure_ai_traces_preview (lookback {LOOKBACK_HOURS}h, max {MAX_TRACES} traces)")

    # Source fields match what the azure_ai_traces_preview data source emits per
    # trace item: query, response, tool_calls, tool_definitions. Using item.input
    # or item.output here will silently produce empty rows and every evaluator
    # will error with "Missing inputs for line N: 'data.input, data.output'".
    common_qr = {"query": "{{item.query}}", "response": "{{item.response}}"}
    tool_mapping = {
        "query": "{{item.query}}",
        "response": "{{item.response}}",
        "tool_definitions": "{{item.tool_definitions}}",
        "tool_calls": "{{item.tool_calls}}",
    }
    testing_criteria = []
    for name in EVALUATORS:
        crit = {
            "type": "azure_ai_evaluator",
            "name": name,
            "evaluator_name": f"builtin.{name}",
            "data_mapping": tool_mapping if name == "tool_call_accuracy" else common_qr,
            "initialization_parameters": {"deployment_name": deployment},
        }
        testing_criteria.append(crit)

    eval_object = openai_client.evals.create(
        name=f"Demo agent batch eval {int(time.time())}",
        data_source_config={"type": "azure_ai_source", "scenario": "responses"},
        testing_criteria=testing_criteria,
    )
    print(f"\neval id: {eval_object.id}")

    data_source = {
        "type": "azure_ai_traces_preview",
        "agent_name": agent_name,
        "lookback_hours": LOOKBACK_HOURS,
        "max_traces": MAX_TRACES,
    }
    eval_run = openai_client.evals.runs.create(
        eval_id=eval_object.id,
        name=f"demo-agent-batch-run-{int(time.time())}",
        data_source=data_source,
    )
    print(f"run id: {eval_run.id}, status: {eval_run.status}")

    # Poll to completion so the pane shows results by the end of this phase.
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    last_status = eval_run.status
    while time.time() < deadline:
        eval_run = openai_client.evals.runs.retrieve(run_id=eval_run.id, eval_id=eval_object.id)
        if eval_run.status != last_status:
            print(f"  status: {eval_run.status}")
            last_status = eval_run.status
        if eval_run.status in ("completed", "failed", "canceled"):
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    rc = eval_run.result_counts
    print(
        f"\nfinal: status={eval_run.status} total={rc.total} "
        f"passed={rc.passed} failed={rc.failed} errored={rc.errored}"
    )
    if eval_run.report_url:
        print(f"report:    {eval_run.report_url}")

    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "agent-batch-eval-run.json").write_text(
        json.dumps(
            _to_json(
                {
                    "eval_id": eval_object.id,
                    "run_id": eval_run.id,
                    "status": eval_run.status,
                    "result_counts": rc,
                    "per_testing_criteria_results": eval_run.per_testing_criteria_results,
                    "report_url": eval_run.report_url,
                }
            ),
            indent=2,
        )
    )
    print("\nSaved artifacts/agent-batch-eval-run.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
