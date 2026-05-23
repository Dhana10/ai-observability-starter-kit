"""Verify continuous evaluation runs materialized after seed traffic."""
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
    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    openai_client = project.get_openai_client()

    cont = json.loads((ARTIFACTS / "continuous-eval.json").read_text())
    eval_id = cont["eval_id"]
    rule_id = cont["rule_id"]
    print(f"eval_id: {eval_id}")
    print(f"rule_id: {rule_id}")

    runs_list_path = ARTIFACTS / "continuous-eval-runs.json"
    deadline = time.time() + 5 * 60  # wait up to 5min for runs to materialize
    last_count = -1
    while time.time() < deadline:
        runs = list(openai_client.evals.runs.list(eval_id=eval_id))
        if len(runs) != last_count:
            print(f"runs found: {len(runs)}")
            last_count = len(runs)
        if runs:
            break
        time.sleep(20)

    runs = list(openai_client.evals.runs.list(eval_id=eval_id))
    summary = {
        "eval_id": eval_id,
        "rule_id": rule_id,
        "run_count": len(runs),
        "runs": [
            {
                "id": r.id,
                "status": getattr(r, "status", None),
                "created_at": getattr(r, "created_at", None),
                "name": getattr(r, "name", None),
            }
            for r in runs
        ],
    }

    runs_list_path.write_text(json.dumps(_to_json(summary), indent=2))
    print(f"\nfinal run count: {summary['run_count']}")
    for r in summary["runs"][:10]:
        print(f"  - {r['id']} status={r['status']}")

    # If runs exist, fetch the latest run's output items
    if runs:
        latest = runs[0]
        try:
            items = list(
                openai_client.evals.runs.output_items.list(
                    run_id=latest.id, eval_id=eval_id
                )
            )
            (ARTIFACTS / "continuous-eval-latest-items.json").write_text(
                json.dumps(_to_json(items), indent=2)
            )
            print(f"latest run output items: {len(items)}")
        except Exception as exc:  # noqa: BLE001
            print(f"output items error: {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
