# Agent

This is the `azd` project root. It contains the infrastructure definitions (Bicep), the four hosted agent source projects, and the azd environment configuration.

## Structure

| Path | Purpose |
| --- | --- |
| `azure.yaml` | azd service definitions for all 4 hosted agents, model deployment specs |
| `infra/` | Bicep modules: Foundry account, AI project, ACR, App Insights, Log Analytics |
| `src/` | Four agent source projects (see below) |
| `.azure/` | azd environment configs (`.env` files with endpoints, resource names) |

## Agent Source Projects

All four agents share identical Python code (`main.py`), tools, and system instructions. They differ only by the model deployment each one targets.

| Agent | Model | Purpose |
| --- | --- | --- |
| `agent-framework-agent-basic-responses` | gpt-4o-mini (via `${MODEL_DEPLOYMENT_NAME}`) | Primary agent with 6 @tool functions |
| `agent-framework-agent-gpt5-mini` | gpt-5-mini (hardcoded) | Cross-model latency and token comparison |
| `agent-framework-agent-gpt41-mini` | gpt-4.1-mini (hardcoded) | Cross-model comparison |
| `agent-framework-agent-broken-model` | `nonexistent-model-deployment-xyz` | Deliberately broken to populate error telemetry |

Each agent project contains:

| File | Purpose |
| --- | --- |
| `main.py` | Agent code: `FoundryChatClient`, `Agent` with procurement-assistant prompt, 6 tool functions |
| `agent.yaml` | Foundry manifest: kind, name, protocol, resources, environment variables |
| `Dockerfile` | Container build definition |
| `requirements.txt` | Dependencies (`agent-framework`, `agent-framework-foundry-hosting`) |

## Key Environment Variables

Set in `agent.yaml` for each agent:

| Variable | Effect |
| --- | --- |
| `ENABLE_INSTRUMENTATION=true` | Activates OpenTelemetry child spans for every `chat` model call and `execute_tool` invocation |
| `ENABLE_SENSITIVE_DATA=true` | Captures full prompt and response text on spans (required for evaluators) |

## Deploying

Agents are deployed via `azd`:

```powershell
cd agent
azd up                           # provisions infra + deploys all agents
azd deploy <agent-name>          # redeploys a single agent
```

The `run-e2e.ps1` orchestrator handles this automatically in phases 1, 3, and 5.

## Infrastructure

The `infra/` folder contains Bicep modules provisioned by `azd up`:

- Foundry account and AI project
- Azure Container Registry (Basic SKU)
- Application Insights (Standard)
- Log Analytics workspace (PerGB2018)
- Model deployment (gpt-4o-mini, GlobalStandard, 30K TPM)
