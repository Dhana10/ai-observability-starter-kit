# Notebooks

Interactive Jupyter versions of the evaluation and red-team scripts for live demos and step-by-step exploration.

## Prerequisites

1. **Deploy the starter kit first.** Run `scripts/run-e2e.ps1` (or at minimum phases 1-7) so agents are deployed and traces exist in App Insights.
2. **Python venv.** Create and activate the venv at the repo root:
   ```powershell
   python -m venv .venv
   . .venv/Scripts/Activate.ps1
   pip install azure-ai-projects azure-identity openai pyyaml python-dotenv azure-monitor-opentelemetry azure-monitor-query requests
   pip install nbconvert ipykernel
   ```
3. **azd environment.** The notebooks auto-discover the active azd environment from `agent/.azure/config.json`. If you have multiple environments, set the default:
   ```powershell
   cd agent ; azd env select <env-name> ; cd ..
   ```

## Notebooks

| Notebook | What it does | Typical runtime |
| --- | --- | --- |
| `01-continuous-eval-setup.ipynb` | Creates eval group, eval rule, and runs batch eval (8 agent evaluators over traces) | ~10 min |
| `02-custom-evaluator-register.ipynb` | Registers the custom compliance phrase evaluator in the Foundry catalog | ~30 s |
| `03-red-team-taxonomy.ipynb` | Pre-stages the red-team taxonomy (risk categories + target agent) | ~30 s |
| `04-red-team-run.ipynb` | Launches the red-team attack run and collects results | ~8 min |

## Running all notebooks

To run all four in sequence without opening them:

```powershell
pwsh -NoProfile -File notebooks/run_notebooks.ps1
```

## Environment discovery

Each notebook's first cell auto-discovers configuration from the azd environment:

- Reads `agent/.azure/config.json` to find the default environment name
- Loads the `.env` file from `agent/.azure/<env-name>/.env`
- Falls back to `AZURE_ENV_NAME` environment variable if set

No hardcoded paths or manual edits are required.
