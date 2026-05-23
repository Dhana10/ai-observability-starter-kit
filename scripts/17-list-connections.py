"""List connections on the Foundry project."""
from __future__ import annotations

import json
import os
import pathlib
import sys

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
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

    print("=== project.connections.list() ===")
    out = []
    try:
        for c in project.connections.list():
            d = _to_json(c)
            out.append(d)
            kind = d.get("type") or d.get("category") or "?"
            name = d.get("name") or d.get("id") or "?"
            print(f"- {kind:<35} {name}")
    except Exception as exc:  # noqa: BLE001
        print(f"error: {type(exc).__name__}: {exc}")

    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "project-connections.json").write_text(json.dumps(out, indent=2))
    print(f"\n{len(out)} connection(s) written to artifacts/project-connections.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
