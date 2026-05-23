"""Force continuous-eval runs by posting responses with store=true.

The `azd ai agent invoke` path does not persist responses to the store that
the continuous-eval rule scans, so the rule's `responseCompleted` event never
fires and the Agents pane "Evaluations" section stays empty.

This script calls the per-agent `/openai/responses` endpoint directly with
`store=True`, which IS scanned by the rule. After 60-120 s,
`scripts/14-verify-continuous-eval.py` should report `run_count > 0`.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import OpenAI, APIStatusError

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


PROMPTS = [
    "List orders for customer C001.",
    "List orders for customer C002.",
    "List orders for customer C999.",
    "Find suppliers for request 1001.",
    "Find suppliers for request 42.",
    "Tell me about supplier S-77.",
    "Tell me about supplier S-XYZ.",
    "Weather in Seattle and roll a 20-sided die.",
]


def main() -> int:
    if AZD_ENV.exists():
        load_dotenv(AZD_ENV)
    load_dotenv()

    project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"].rstrip("/")
    model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
    agent_name = os.environ.get(
        "AZURE_AI_AGENT_NAME", "agent-framework-agent-basic-responses"
    )
    api_version = "2025-11-15-preview"

    base_url = (
        f"{project_endpoint}/agents/{agent_name}/endpoint/protocols/openai"
    )
    print(f"agent_name:   {agent_name}")
    print(f"model:        {model}")
    print(f"base_url:     {base_url}")

    scope = os.environ.get("FOUNDRY_TOKEN_SCOPE", "https://ai.azure.com/.default")
    token_provider = get_bearer_token_provider(DefaultAzureCredential(), scope)
    print(f"scope:        {scope}")

    def make_client() -> OpenAI:
        return OpenAI(
            base_url=base_url,
            api_key="placeholder",
            default_query={"api-version": api_version},
            default_headers={"Authorization": f"Bearer {token_provider()}"},
        )

    summary = {"agent_name": agent_name, "model": model, "responses": []}

    for i, prompt in enumerate(PROMPTS, start=1):
        client = make_client()
        print(f"\n[{i}/{len(PROMPTS)}] {prompt}")
        try:
            resp = client.responses.create(
                model=model,
                input=prompt,
                store=True,
            )
            text = getattr(resp, "output_text", None) or ""
            print(f"  id={resp.id}  text={text[:80]!r}")
            summary["responses"].append(
                {"id": resp.id, "prompt": prompt, "text": text}
            )
        except APIStatusError as exc:
            body = None
            try:
                body = exc.response.text
            except Exception:  # noqa: BLE001
                body = None
            print(f"  ERROR {exc.status_code}: {body or exc}")
            summary["responses"].append(
                {"prompt": prompt, "status": exc.status_code, "body": body}
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            summary["responses"].append(
                {"prompt": prompt, "error": f"{type(exc).__name__}: {exc}"}
            )
        time.sleep(1)

    ARTIFACTS.mkdir(exist_ok=True)
    out = ARTIFACTS / "eval-trigger-responses.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nsaved: {out}")
    print(
        f"\nWait 60-120 s, then re-run scripts/14-verify-continuous-eval.py "
        f"to confirm eval runs materialized for eval_id."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
