# Prompts

Test prompt corpora used by `scripts/05-seed-traffic.ps1` to generate realistic agent traffic. Each file contains one prompt per line.

| File | Count | Purpose |
| --- | --- | --- |
| `clean.txt` | 33 | Normal traffic: questions about Foundry, agents, evaluators, observability, and tool usage |
| `ambiguous.txt` | 10 | Edge-case prompts with vague or context-dependent phrasing (e.g. "Do the usual thing", "Fix it like before") |
| `safety-bait.txt` | 5 | Adversarial prompts designed to elicit violent or harmful content, used to test safety filters |

## How they are used

The `05-seed-traffic.ps1` script sends all 48 prompts to each working agent during phase 6 of the e2e pipeline. The responses and their telemetry spans flow into App Insights, where they are scored by agent evaluators and surfaced in dashboards.

The safety-bait prompts are separate from the automated red-team scan (phase 10), which generates its own adversarial prompts via Foundry's cloud red-team service.

## Customizing

Add or modify prompts in any file (one per line). The seed traffic script reads all lines and sends them sequentially.
