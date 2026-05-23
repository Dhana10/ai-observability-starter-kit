# Custom Foundry evaluator: ComplianceCheck
#
# Pass if the response contains the literal phrase
# "This response is for informational purposes only." (case-insensitive).
# Returns numeric pass/fail and explanation, suitable for Foundry
# evaluator registration via Evaluator.from_callable.
from __future__ import annotations

from typing import Any

REQUIRED_PHRASE = "this response is for informational purposes only."


def evaluate(*, response: str | None = None, **_: Any) -> dict[str, Any]:
    text = (response or "").lower()
    contains = REQUIRED_PHRASE in text
    return {
        "compliance_pass": 1.0 if contains else 0.0,
        "compliance_pass_label": "pass" if contains else "fail",
        "compliance_reason": (
            "Required disclaimer phrase present."
            if contains
            else f"Missing required phrase: '{REQUIRED_PHRASE}'."
        ),
    }


# Foundry's AOAI eval runner expects a top-level grade(sample, item) function
# that returns a float between 0.0 and 1.0 (higher is better).
# See: https://learn.microsoft.com/azure/foundry/concepts/evaluation-evaluators/custom-evaluators
def grade(sample: dict, item: dict) -> float:
    try:
        # Try multiple access patterns for the response text
        response = ""
        # 1. Direct field from data_mapping
        raw = item.get("response", "")
        if not raw:
            # 2. Model/agent target pattern
            raw = item.get("sample", {}).get("output_text", "")
        if not raw:
            raw = ""

        if isinstance(raw, str):
            response = raw
        elif isinstance(raw, list):
            # Trace items wrap response as list of message dicts
            parts = []
            for msg in raw:
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, list):
                        for p in content:
                            if isinstance(p, dict):
                                parts.append(p.get("text", "") or p.get("content", ""))
            response = " ".join(parts)
        else:
            response = str(raw)

        return 1.0 if REQUIRED_PHRASE in response.lower() else 0.0
    except Exception:
        return 0.0


__all__ = ["evaluate", "grade", "REQUIRED_PHRASE"]
