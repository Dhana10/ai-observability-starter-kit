# Scripts

Automation scripts for the AI Observability Starter Kit. All scripts run from the repo root.

## Core Scripts

| Script | What it does |
| --- | --- |
| `run-e2e.ps1` | Single orchestrator: provisions infrastructure, deploys 4 agents, seeds traffic, runs evaluations, red-team, alerts, and validates (13 phases) |
| `validate-deployment.ps1` | Post-deploy validation across 8 categories (24 checks). Use `-SkipInvoke` to skip agent call tests |
| `teardown.ps1` | Deletes resource group, purges Cognitive Services soft-delete. Use `-EnvName <name>`, `-NoPurge` to skip purge |

## Phase Scripts

These are called by `run-e2e.ps1` but can also be run individually.

| Script | Phase | What it does |
| --- | --- | --- |
| `03-grant-foundry-user.ps1` | 2 | Grants Foundry User role to the project managed identity |
| `04-warmup.ps1` | 6 | 3 fast pings to defeat agent scale-to-zero |
| `05-seed-traffic.ps1` | 6 | Sends 48 prompts from clean, ambiguous, and safety-bait corpora |
| `06b-alerts-rest.py` | 11 | Creates 2 scheduled-query alerts (error count sev 2, p95 latency sev 3) via ARM REST |
| `10-continuous-eval.py` | 8 | Registers an evaluation rule with 3 agent evaluators |
| `11-custom-evaluator-register.py` | 8 | Registers the custom compliance phrase evaluator in the Foundry catalog |
| `12-red-team.py` | 10 | Runs adversarial red-team scan (temporary prompt agent, Flip + Base64 strategies, 3 safety evaluators) |
| `13-telemetry-kql.py` | 12 | Exports 4 KQL queries (volume, latency, sessions, tokens) to `artifacts/telemetry.json` |
| `14-verify-continuous-eval.py` | 13 | Verifies that evaluation runs completed successfully |
| `20-agent-batch-eval.py` | 9 | Batch eval: 8 agent evaluators over recent traces in App Insights |

## Debug Scripts

Useful for troubleshooting. Not called by `run-e2e.ps1`.

| Script | What it does |
| --- | --- |
| `15-list-eval-rules.py` | Dumps evaluation rule definitions and their runs |
| `16-list-rules.py` | Lists all evaluation rules (GA API) |
| `17-list-connections.py` | Lists project connections |
| `18-trigger-eval-runs.py` | Store-based eval trigger workaround |
| `style-summary-tiles.py` | Styles Grafana summary tile panels |

## Subfolders

| Folder | Purpose |
| --- | --- |
| `grafana-fix/` | Dashboard JSON fixup utilities (datasource UIDs, query types, variable prefill) |
| `to-delete/` | Legacy scripts from early development, safe to remove |

## Prerequisites

All scripts expect:
- PowerShell 7 (`pwsh`) for `.ps1` scripts
- Python venv activated (`.venv/Scripts/Activate.ps1`) for `.py` scripts
- `az` CLI logged in and subscription set
- `azd` environment initialized under `agent/.azure/`
