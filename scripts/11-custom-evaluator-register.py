"""Register the custom compliance phrase evaluator (Phase 6 of demo).

Loads ``evaluators/custom_compliance_phrase.py`` and registers it via
``project.beta.evaluators.create`` (preview surface). Falls back to writing a
manifest artifact if the SDK surface differs in this release.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import yaml
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    CodeBasedEvaluatorDefinition,
    EvaluatorCategory,
    EvaluatorDefinitionType,
    EvaluatorMetric,
    EvaluatorMetricDirection,
    EvaluatorMetricType,
    EvaluatorType,
    EvaluatorVersion,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
EVAL_DIR = ROOT / "evaluators"
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

# Ensure the evaluator module is importable for the smoke test
sys.path.insert(0, str(EVAL_DIR))
import custom_compliance_phrase as cce  # noqa: E402


def main() -> int:
    if AZD_ENV.exists():
        load_dotenv(AZD_ENV)
    load_dotenv()

    endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    print(f"endpoint:  {endpoint}")

    # Smoke test before registering
    sample_pass = cce.evaluate(
        response="This response is for informational purposes only. Hello."
    )
    sample_fail = cce.evaluate(response="Hello world")
    print(f"smoke pass: {sample_pass}")
    print(f"smoke fail: {sample_fail}")
    assert sample_pass["compliance_pass"] == 1.0
    assert sample_fail["compliance_pass"] == 0.0

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    manifest = yaml.safe_load((EVAL_DIR / "custom_compliance_phrase.yaml").read_text())
    source = (EVAL_DIR / "custom_compliance_phrase.py").read_text()

    evaluator_version = EvaluatorVersion(
        display_name=manifest.get("display_name", manifest["name"]),
        description=manifest.get("description"),
        evaluator_type=EvaluatorType.CUSTOM,
        categories=[EvaluatorCategory.QUALITY],
        definition=CodeBasedEvaluatorDefinition(
            type=EvaluatorDefinitionType.CODE,
            code_text=source,
            entry_point=manifest["entry_point"],
        ),
        metadata={
            "module": "custom_compliance_phrase",
            "required_phrase": "this response is for informational purposes only.",
        },
        tags={"demo": "agent-observability", "owner": "varghesejoji"},
    )
    # Optional metric definitions for richer dashboards
    try:
        evaluator_version.definition.metrics = {
            "compliance_pass": EvaluatorMetric(
                type=EvaluatorMetricType.BOOLEAN,
                desirable_direction=EvaluatorMetricDirection.INCREASE,
                min_value=0.0,
                max_value=1.0,
                threshold=1.0,
                is_primary=True,
            ),
        }
    except Exception:  # noqa: BLE001
        pass

    catalog_id = None
    error_message = None
    try:
        created = project.beta.evaluators.create_version(
            name=manifest["name"], evaluator_version=evaluator_version
        )
        catalog_id = getattr(created, "id", None) or getattr(created, "name", None)
        print(f"registered: name={created.name} version={created.version} id={catalog_id}")
    except Exception as exc:  # noqa: BLE001
        error_message = f"{type(exc).__name__}: {exc}"
        print(f"registration failed, falling back to manifest persistence: {error_message}")
        catalog_id = f"manifest:{manifest['name']}:{manifest['version']}"

    ARTIFACTS.mkdir(exist_ok=True)
    out_path = ARTIFACTS / "custom-evaluator.json"
    out_path.write_text(
        json.dumps(
            {
                "catalog_id": catalog_id,
                "name": manifest["name"],
                "version": manifest["version"],
                "smoke_pass": sample_pass,
                "smoke_fail": sample_fail,
                "registration_error": error_message,
            },
            indent=2,
            default=str,
        )
    )
    print(f"saved:     {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
