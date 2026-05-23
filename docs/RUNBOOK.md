# Foundry agent observability demo: runbook

Captures every command that was actually executed successfully during the autonomous run on 2026-05-20, against the running Foundry account `ai-account-eyfs7o7lvdq7e` in subscription `463a82d4-1896-4332-aeeb-618ee5a5aa93`, RG `rg-aiobs-foundry-20260520`, region `eastus2`.

Run these from PowerShell 7 (`pwsh`) on Windows from the repo root.

> Style note: this doc deliberately uses parentheses, commas, colons, and short sentence splits instead of em-dashes.

## 0. Toolchain

```powershell
# Pin the exact azd build the demo was validated with
$AZD = "$env:LOCALAPPDATA\Programs\azd-local\azd.exe"  # 1.25.1 (DO NOT use PATH azd 1.23.10)
& $AZD version

# Required CLIs
az --version          # 2.86.0
docker --version      # 29.4.3
python --version      # 3.12.10
```

Foundry/agent SDK install (one time, into the venv):

```powershell
& '.venv\Scripts\pip.exe' install `
    azure-ai-projects==2.1.0 azure-identity openai pyyaml python-dotenv `
    azure-monitor-opentelemetry azure-monitor-query requests
```

## 1. Sign in

```powershell
az login --tenant 5bb5fa45-2dcc-4310-bbc5-883021e9d84b
az account set --subscription 463a82d4-1896-4332-aeeb-618ee5a5aa93
& $AZD auth login --tenant-id 5bb5fa45-2dcc-4310-bbc5-883021e9d84b
```

## 2. Provision (TC-010 .. TC-013)

```powershell
Push-Location 'agent'

& $AZD env new aiobs-foundry-20260520 -l eastus2 --subscription 463a82d4-1896-4332-aeeb-618ee5a5aa93
& $AZD env set MODEL_DEPLOYMENT_NAME gpt-4o-mini
& $AZD env set MODEL_NAME            gpt-4o-mini
& $AZD env set MODEL_VERSION         2024-07-18
& $AZD env set MODEL_FORMAT          OpenAI
& $AZD env set MODEL_SKU_NAME        GlobalStandard
& $AZD env set MODEL_CAPACITY        30
& $AZD env set AZURE_PRINCIPAL_ID    8bad37c5-2843-4f34-9a80-4a9b971e644f

# IMPORTANT: ensure azure.yaml has the `services:` block before deploy (see Section 3)
& $AZD up --no-prompt   # 7m provisioning total, includes capability host /agents

Pop-Location
```

Verification:

```powershell
az group show -g rg-aiobs-foundry-20260520 -o table
az resource list -g rg-aiobs-foundry-20260520 --query "[].{name:name,type:type}" -o table
# Should list: Microsoft.CognitiveServices/accounts, accounts/projects, ACR, App Insights, Log Analytics
```

## 3. Patch azure.yaml services block (one time)

The azd Foundry template ships without a `services:` block, so `azd deploy` is a no-op until you add one. Inside `agent/azure.yaml`:

```yaml
name: aiobs-foundry-20260520
metadata:
  template: agent-framework@1.0
infra:
  provider: bicep
services:
  agent-framework-agent-basic-responses:
    project: ./src/agent-framework-agent-basic-responses
    language: agent
    host: ai-agent
```

## 4. Deploy + first invoke (TC-020 .. TC-023)

```powershell
Push-Location 'agent'

& $AZD deploy --no-prompt
# Packaging -> Publishing -> Creating agent -> Waiting for active -> Registering env vars -> Done (4m08s)

& $AZD ai agent show
# Status: active, ID: agent-framework-agent-basic-responses:1

& $AZD ai agent invoke --new-session --new-conversation `
    "Reply with the word OK and nothing else."
# Returns: OK + Trace ID

Pop-Location
```

Verify first telemetry span (wait ~60s for ingest):

```powershell
$wsId = az monitor log-analytics workspace show -g rg-aiobs-foundry-20260520 -n logs-eyfs7o7lvdq7e --query customerId -o tsv
az monitor log-analytics query -w $wsId --analytics-query `
    'AppRequests | where TimeGenerated > ago(15m) | where Name has "invoke_agent" | project Name, Success, DurationMs, AppRoleName | take 5' -o table
```

## 5. RBAC: Foundry User on project (TC-030 .. TC-032)

```powershell
$accountMi = az resource show -g rg-aiobs-foundry-20260520 `
    --resource-type Microsoft.CognitiveServices/accounts -n ai-account-eyfs7o7lvdq7e `
    --query identity.principalId -o tsv

$projectScope = "/subscriptions/463a82d4-1896-4332-aeeb-618ee5a5aa93/resourceGroups/rg-aiobs-foundry-20260520/providers/Microsoft.CognitiveServices/accounts/ai-account-eyfs7o7lvdq7e/projects/ai-project-aiobs-foundry-20260520"

az role assignment create `
    --assignee-object-id $accountMi `
    --assignee-principal-type ServicePrincipal `
    --role "Foundry User" `
    --scope $projectScope

# verify
az role assignment list --assignee $accountMi --all --query "[].{role:roleDefinitionName, scope:scope}" -o table
```

Note: the role is `Foundry User` (def id `53ca6127-db72-4b80-b1b0-d745d6d5456d`). The older name `Azure AI User` does not exist in this tenant.

## 6. Warmup + seed traffic (TC-040 .. TC-042)

```powershell
pwsh -NoProfile -File 'scripts\04-warmup.ps1'
# 3 pings via `azd ai agent invoke`

pwsh -NoProfile -File 'scripts\05-seed-traffic.ps1' -SleepSeconds 1
# 48 prompts (golden + tools + safety-bait + multi-turn). Log at artifacts/seed-*.log
```

Validation:

```powershell
$log = Get-ChildItem 'artifacts\seed-*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$content = Get-Content $log.FullName -Raw
([regex]::Matches($content, '(?m)^## \[')).Count          # prompts emitted (expect 48)
([regex]::Matches($content, '\[agent-framework-')).Count  # replies received (expect 48)
([regex]::Matches($content, '(?m)^Trace ID:')).Count      # traces (expect 48)
```

Safety refusal check (TC-042): in the safety-bait section of the log, look for `I'm sorry, I can't assist with that.` or `I can't assist with that.`. The current Foundry safety filter refuses 4 of 5 safety-bait prompts; the graphic-battle "creative writing" framing slipped through and is documented as a red-team-actionable finding.

## 6b. Enrich the Agents pane: multi-model, multi-tool, gen AI errors (TC-045)

With only `agent-framework-agent-basic-responses` deployed against `gpt-4o-mini` and zero tools, the App Insights Agents (preview) pane lights up the Agent Runs / Tokens / Models tiles but the Tool Calls table is empty and the Gen AI Errors pie is empty. The fixes are layered: tools, then more models, then a deliberately broken agent for chat-level errors.

### 6b.1 Add tool functions to the agent (Tool Calls + tool errors)

In `agent/src/agent-framework-agent-basic-responses/main.py`, register six `@tool`-decorated functions and wire them into the `Agent(tools=[...])` constructor. Three of them raise on bad input so the Errors column lights up:

```python
@tool(name="get_orders", description="Get all orders for a given customer id.")
def get_orders(customer_id: Annotated[str, Field(description="Customer id, e.g. C001.")]) -> str:
    orders = _FAKE_ORDERS.get(customer_id.upper())
    if orders is None:
        raise LookupError(f"Unknown customer_id: {customer_id}")
    return f"Customer {customer_id} has {len(orders)} order(s): {orders}"

@tool(name="find_suppliers_for_request", description="Find suppliers for a procurement request.")
def find_suppliers_for_request(request_id: Annotated[int, Field(ge=1)]) -> str:
    if request_id < 1000:
        raise ValueError(f"request_id must be >= 1000, got {request_id}")
    suppliers = _FAKE_SUPPLIERS.get(request_id)
    if suppliers is None:
        raise LookupError(f"No suppliers indexed for request {request_id}")
    return f"Request {request_id}: {len(suppliers)} supplier(s) -> {suppliers}"

@tool(name="get_company_supplier_info", description="Get details for a supplier id.")
def get_company_supplier_info(supplier_id: Annotated[str, Field(...)]) -> str:
    info = _FAKE_SUPPLIER_DETAILS.get(supplier_id.upper())
    if info is None:
        raise LookupError(f"Unknown supplier_id: {supplier_id}")
    return f"Supplier {supplier_id}: {info}"

# Plus three deterministic, always-succeed tools: get_current_utc_date, get_weather(city), roll_dice(sides)
```

The agent instructions must explicitly tell the model to call tools and to surface tool errors, otherwise it papers over them:

```python
agent = Agent(
    client=client,
    instructions=(
        "You are a procurement assistant. Keep answers brief. "
        "You MUST call tools instead of guessing. "
        "Use get_orders for order lookups, find_suppliers_for_request for procurement "
        "requests, get_company_supplier_info for supplier details, get_current_utc_date "
        "when asked the date/time, get_weather for weather, and roll_dice for dice rolls. "
        "If a tool raises an error, briefly report what failed."
    ),
    tools=[get_orders, find_suppliers_for_request, get_current_utc_date,
           get_company_supplier_info, get_weather, roll_dice],
    default_options={"store": False},
)
```

Redeploy:

```powershell
Push-Location 'agent'
& $AZD deploy agent-framework-agent-basic-responses --no-prompt 2>&1 | Tee-Object ..\artifacts\deploy-rich-tools.log
Pop-Location
```

Drive both happy and unhappy paths (mix good IDs with bad ones so each of the 3 raising tools fires both branches):

```powershell
$AZD = "$env:LOCALAPPDATA\Programs\azd-local\azd.exe"
Push-Location 'agent'
$agent = 'agent-framework-agent-basic-responses'
$prompts = @(
    'List orders for customer C001.',
    'List orders for customer C002.',
    'List orders for customer C999.',                  # LookupError
    'Find suppliers for request 1001.',
    'Find suppliers for request 1002.',
    'Find suppliers for request 42.',                  # ValueError
    'Tell me about supplier S-77.',
    'Tell me about supplier S-91.',
    'Tell me about supplier S-XYZ.',                   # LookupError
    'What time is it in UTC?',
    'Weather in Seattle?',
    'Roll a 20-sided die.'
)
foreach ($p in $prompts) {
    & $AZD ai agent invoke --new-session --new-conversation $agent $p 2>&1 | Select-Object -Last 2
    Start-Sleep -Milliseconds 400
}
Pop-Location
```

Verify (wait ~60-90s for ingest):

```powershell
$wsId = '7c4aa12e-4b46-4997-83f4-8c7422fc5538'
$q = "AppDependencies | where TimeGenerated > ago(15m) | where Name startswith 'execute_tool' | summarize n=count(), errs=countif(Success==false) by Name | order by n desc"
az monitor log-analytics query -w $wsId --analytics-query $q -o table
```

Expected: 6 rows (`execute_tool get_orders`, `execute_tool find_suppliers_for_request`, `execute_tool get_company_supplier_info`, `execute_tool get_current_utc_date`, `execute_tool get_weather`, `execute_tool roll_dice`), with non-zero `errs` on the first three.

### 6b.2 Add additional model deployments + sister agents (Models tile shows >1 model)

Pre-create two more model deployments on the SAME Foundry account (azd will not do this for you after the initial provision; `az cognitiveservices account deployment create` is the canonical path):

```powershell
$rg = 'rg-aiobs-foundry-20260520'
$acct = 'ai-account-eyfs7o7lvdq7e'
az cognitiveservices account deployment create -g $rg -n $acct `
    --deployment-name gpt-5-mini --model-name gpt-5-mini --model-version 2025-08-07 `
    --model-format OpenAI --sku-name GlobalStandard --sku-capacity 100
az cognitiveservices account deployment create -g $rg -n $acct `
    --deployment-name gpt-4.1-mini --model-name gpt-4.1-mini --model-version 2025-04-14 `
    --model-format OpenAI --sku-name GlobalStandard --sku-capacity 100
az cognitiveservices account deployment list -g $rg -n $acct -o table
```

Clone the basic-responses agent project once per new model so each hosted agent process reports its own `chat <model>` span:

```powershell
$src = 'agent\src\agent-framework-agent-basic-responses'
Copy-Item -Path $src -Destination "$src\..\agent-framework-agent-gpt5-mini"  -Recurse -Force
Copy-Item -Path $src -Destination "$src\..\agent-framework-agent-gpt41-mini" -Recurse -Force
```

Edit each clone's `agent.yaml` to (a) rename `name:`, and (b) hardcode the model env var so it is not overridden by the azd env:

```yaml
# src/agent-framework-agent-gpt5-mini/agent.yaml
kind: hosted
name: agent-framework-agent-gpt5-mini
protocols:
  - protocol: responses
    version: 1.0.0
resources:
  cpu: '0.25'
  memory: '0.5Gi'
environment_variables:
  - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
    value: "gpt-5-mini"        # hardcoded; do NOT use ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
  - name: ENABLE_INSTRUMENTATION
    value: "true"
  - name: ENABLE_SENSITIVE_DATA
    value: "true"
```

Do the same for `agent-framework-agent-gpt41-mini` with `value: "gpt-4.1-mini"`.

Append both as new services in `agent/azure.yaml` (they reuse the same Dockerfile and main.py, just a different `agent.yaml`):

```yaml
services:
  agent-framework-agent-basic-responses:
    project: src/agent-framework-agent-basic-responses
    host: azure.ai.agent
    language: docker
    docker: { remoteBuild: true }
    # ... existing config block, including deployments[] for gpt-4o-mini ...
  agent-framework-agent-gpt5-mini:
    project: src/agent-framework-agent-gpt5-mini
    host: azure.ai.agent
    language: docker
    docker: { remoteBuild: true }
    config:
      container: { resources: { cpu: "0.25", memory: 0.5Gi } }
      # NOTE: no deployments[] block; this agent uses the pre-created gpt-5-mini deployment.
  agent-framework-agent-gpt41-mini:
    project: src/agent-framework-agent-gpt41-mini
    host: azure.ai.agent
    language: docker
    docker: { remoteBuild: true }
    config:
      container: { resources: { cpu: "0.25", memory: 0.5Gi } }
```

Deploy the new agents:

```powershell
Push-Location 'agent'
& $AZD deploy agent-framework-agent-gpt5-mini  --no-prompt
& $AZD deploy agent-framework-agent-gpt41-mini --no-prompt
Pop-Location
```

Fan out the same prompt set (Section 6b.1) across all three agents:

```powershell
Push-Location 'agent'
foreach ($agent in @('agent-framework-agent-basic-responses', 'agent-framework-agent-gpt5-mini', 'agent-framework-agent-gpt41-mini')) {
    foreach ($p in $prompts) {
        & $AZD ai agent invoke --new-session --new-conversation $agent $p 2>&1 | Select-Object -Last 2
        Start-Sleep -Milliseconds 400
    }
}
Pop-Location
```

Verify three distinct `chat <model>` rows:

```powershell
$q = "AppDependencies | where TimeGenerated > ago(20m) | where Name startswith 'chat ' | summarize n=count(), errs=countif(Success==false) by Name | order by n desc"
az monitor log-analytics query -w $wsId --analytics-query $q -o table
```

### 6b.3 Add a deliberately broken agent for chat-level Gen AI Errors

The "Gen AI errors broken down by operation" pie on the Agents pane only lights up for `chat <model>` errors when chat calls actually fail. The easiest reproducible trigger is a fourth hosted agent that points at a model deployment that does not exist:

```powershell
$src = 'agent\src\agent-framework-agent-basic-responses'
Copy-Item -Path $src -Destination "$src\..\agent-framework-agent-broken-model" -Recurse -Force
```

`src/agent-framework-agent-broken-model/agent.yaml`:

```yaml
kind: hosted
name: agent-framework-agent-broken-model
protocols:
  - protocol: responses
    version: 1.0.0
resources:
  cpu: '0.25'
  memory: '0.5Gi'
environment_variables:
  - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
    value: "nonexistent-model-deployment-xyz"   # intentional: causes chat call to 404
  - name: ENABLE_INSTRUMENTATION
    value: "true"
  - name: ENABLE_SENSITIVE_DATA
    value: "true"
```

Add it as a fourth service in `agent/azure.yaml` (same shape as the gpt5-mini block, no `deployments[]`). Deploy:

```powershell
Push-Location 'agent'
& $AZD deploy agent-framework-agent-broken-model --no-prompt
Pop-Location
```

The agent CONTAINER starts fine; only the chat call inside the response handler fails (the model deployment lookup returns 404). Drive 5-8 invokes to seed the errors-by-operation pie:

```powershell
Push-Location 'agent'
$agent = 'agent-framework-agent-broken-model'
1..8 | ForEach-Object {
    & $AZD ai agent invoke --new-session --new-conversation $agent "ping $_" 2>&1 | Select-Object -Last 2
    Start-Sleep -Milliseconds 400
}
Pop-Location
```

Verify failed chat spans show up under the fake model name:

```powershell
$q = "AppDependencies | where TimeGenerated > ago(15m) | where Name startswith 'chat ' | summarize n=count(), errs=countif(Success==false) by Name | order by errs desc"
az monitor log-analytics query -w $wsId --analytics-query $q -o table
```

Expected: a row `chat nonexistent-model-deployment-xyz` with `errs == n` (every call failed). The Agents pane's "Agent with highest errors" tile will now show `agent-framework-agent-broken-model` and the Gen AI Errors stacked bar will have slices for `chat`, `invoke_agent`, and `execute_tool`. Pane rollup takes 15-30 min.

To build custom views on top of (or instead of) the Agents pane, see [docs/GRAFANA_GUIDE.md](./GRAFANA_GUIDE.md). It covers the embedded "Dashboards with Grafana" experience, the three prebuilt Gen AI dashboards (Agent Framework, Agent Framework workflow, Foundry), 5 custom KQL panels grounded in this demo's schema, and the importable companion JSON at [artifacts/grafana/agent-observability-custom-dashboard.json](../artifacts/grafana/agent-observability-custom-dashboard.json).

## 7. Telemetry KQL (TC-050 .. TC-053)

Use the Logs Query API via Python (the `az monitor app-insights query` CLI mishandles JSON columns and returns raw blobs):

```powershell
$env:LOG_ANALYTICS_WORKSPACE_ID = az monitor log-analytics workspace show -g rg-aiobs-foundry-20260520 -n logs-eyfs7o7lvdq7e --query customerId -o tsv
$env:APPLICATIONINSIGHTS_RESOURCE_ID = az resource show -g rg-aiobs-foundry-20260520 -n appi-eyfs7o7lvdq7e --resource-type microsoft.insights/components --query id -o tsv
& '.venv\Scripts\python.exe' 'scripts\13-telemetry-kql.py'
```

Output goes to `artifacts/telemetry.json` with four sections:
- volume + success by agent name
- p50/p90/p95/p99 latency
- session bucket by 5m
- token usage (currently 0 because the agent server does not surface `gen_ai.usage.*` on `invoke_agent` spans in this SDK build; documented as observed limitation)

Standalone KQL (paste into App Insights Logs blade or `az monitor log-analytics query`):

```kql
requests
| where name has "invoke_agent"
| extend success_b = tobool(success)
| summarize total = count(), success = countif(success_b == true), failed = countif(success_b == false), unique_traces = dcount(operation_Id) by name
```

```kql
requests
| where name has "invoke_agent"
| summarize n = count(),
            p50_ms = percentile(duration, 50),
            p95_ms = percentile(duration, 95),
            p99_ms = percentile(duration, 99),
            max_ms = max(duration)
```

## 8. Continuous eval (TC-060 .. TC-066)

```powershell
Push-Location 'agent'
$env_text = & $AZD env get-values
$env_text -split "`n" | ForEach-Object {
    if ($_ -match '^\s*([A-Z0-9_]+)="?(.*?)"?\s*$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
Pop-Location

& '.venv\Scripts\python.exe' 'scripts\10-continuous-eval.py'
```

Critical pattern (every evaluator MUST include `data_mapping` in `azure_ai_source`/responses scenario, otherwise the API returns `MissingRequiredDataMapping`):

```python
common_qr = {"query": "{{item.input}}", "response": "{{item.output}}"}
testing_criteria = [
    {
        "type": "azure_ai_evaluator",
        "name": "Intent Resolution",
        "evaluator_name": "builtin.intent_resolution",
        "evaluator_version": "1",
        "data_mapping": common_qr,
        "initialization_parameters": {"deployment_name": "gpt-4o-mini"},
    },
    {
        "type": "azure_ai_evaluator",
        "name": "Violence",
        "evaluator_name": "builtin.violence",
        "evaluator_version": "1",
        "data_mapping": common_qr,
    },
    {
        "type": "azure_ai_evaluator",
        "name": "Tool Call Accuracy",
        "evaluator_name": "builtin.tool_call_accuracy",
        "evaluator_version": "1",
        "data_mapping": {"query": "{{item.input}}", "tool_definitions": "{{item.tools}}"},
        "initialization_parameters": {"deployment_name": "gpt-4o-mini"},
    },
]
```

Rule: `ContinuousEvaluationRuleAction(eval_id, max_hourly_runs=100)`, `EvaluationRuleEventType.RESPONSE_COMPLETED`, `EvaluationRuleFilter(agent_name=agent_name)`. Output to `artifacts/continuous-eval.json`.

Verify runs materialize (60-120s after a fresh response):

```powershell
& '.venv\Scripts\python.exe' 'scripts\14-verify-continuous-eval.py'
```

Observed gap on the autonomous run: after the rule was created and after 53 total fresh `azd ai agent invoke` calls, `openai_client.evals.runs.list(eval_id)` returned `run_count=0` for the full 5 min poll. The rule definition itself is correct (`enabled=true`, `responseCompleted` event, `agentName` filter matches, `data_mapping` set per evaluator). The two real reasons the rule stayed empty:

1. `azd ai agent invoke` does not persist the response object into the Foundry response store, so `responseCompleted` never fires.
2. Even after persisting responses with `store=true`, the rule's server-side processor has an opaque cadence (we saw a single run materialize only after ~10-15 min, and it was a side-effect of a separate manual `evals.runs.create` call, not the rule itself).

Workaround chain we actually verified end-to-end (use `scripts/18-trigger-eval-runs.py`):

```python
# scripts/18-trigger-eval-runs.py (excerpt)
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI

scope = "https://ai.azure.com/.default"  # NOT cognitiveservices.azure.com (returns 403)
token_provider = get_bearer_token_provider(DefaultAzureCredential(), scope)
base_url = f"{project_endpoint}/agents/{agent_name}/endpoint/protocols/openai"
client = OpenAI(
    base_url=base_url, api_key="placeholder",
    default_query={"api-version": "2025-11-15-preview"},
    default_headers={"Authorization": f"Bearer {token_provider()}"},
)
client.responses.create(model="gpt-4o-mini", input=prompt, store=True)
```

```powershell
& '.venv\Scripts\python.exe' 'scripts\18-trigger-eval-runs.py'
& '.venv\Scripts\python.exe' 'scripts\14-verify-continuous-eval.py'
```

Reliable fallback that populates the Agents pane "Evaluations" section immediately (a one-shot batch, not bound to the rule's async processor). Use the Foundry MCP tool `evaluation_agent_batch_eval_create` (or POST the same body to `<project>/evaluations/agent-batch-eval`):

```jsonc
{
  "projectEndpoint": "https://ai-account-...services.ai.azure.com/api/projects/ai-project-...",
  "agentName": "agent-framework-agent-basic-responses",
  "agentVersion": "5",
  "deploymentName": "gpt-4o-mini",
  "evaluatorNames": ["intent_resolution","task_adherence","coherence","fluency","relevance"],
  "evaluationName": "Demo agent batch eval",
  "runName": "demo-agent-batch-run-1",
  "inputData": [
    {"query": "List orders for customer C001."},
    {"query": "Find suppliers for request 1001."},
    {"query": "Tell me about supplier S-77."},
    {"query": "What is the weather in Seattle?"},
    {"query": "Roll a 20-sided die."},
    {"query": "List orders for customer C999."},
    {"query": "Tell me about supplier S-XYZ."}
  ]
}
```

Verified result on this deployment: `evalrun_24c4a2d43da64d958111c505caa538db` completed in <5 min with `total=8, passed=5, failed=3, errored=0, skipped=0`. The Agents pane "Evaluations" tile populates on the next 15-30 min rollup. Reuse helper: `scripts/20-agent-batch-eval.py`.

### Reading the Evaluations pane (post-rollup)

The Evaluations section of the Agents pane renders one tile per evaluator with a time series and a `Score (Avg)` summary. Scales differ per evaluator; the pane does NOT normalize them, so do not compare absolute numbers across tiles.

| Evaluator | Scale | Pass criterion (default) | Observed avg on `demo-agent-batch-run-1` |
|---|---|---|---|
| `intent_resolution` | 1-5 Likert | score >= 3 | 4.13 |
| `task_adherence` | 0-1 (binary-like) | score == 1 | 0.75 |
| `coherence` | 1-5 Likert | score >= 3 | 3.5 |
| `fluency` | 1-5 Likert | score >= 3 | 3 |
| `relevance` | 1-5 Likert | score >= 3 | (select from `Evaluation` dropdown) |

Operational notes:

- Only `total/passed/failed/errored/skipped` is meaningful for "did the run succeed". The per-evaluator avg is a quality signal, not a pass/fail.
- A single run renders as one dot per tile. Re-running `scripts/20-agent-batch-eval.py` adds more dots and turns the chart into a trend.
- Pane rollup lag is 15-30 min. Raw values are visible immediately via `oc.evals.runs.retrieve(run_id, eval_id)`.
- To switch which evaluator a tile shows, use its `Evaluation` dropdown; the same five evaluators populate every tile slot.
- If a tile reads "Already set up? There may be no recent activity.", widen the time range to "Last 4 hours" before assuming the data is missing.

## 9. Custom evaluator (TC-070 .. TC-071)

```powershell
& '.venv\Scripts\python.exe' 'scripts\11-custom-evaluator-register.py'
```

API surface (the SDK surface that actually works on `azure-ai-projects==2.1.0`):

```python
from azure.ai.projects.models import (
    CodeBasedEvaluatorDefinition, EvaluatorDefinitionType, EvaluatorVersion,
    EvaluatorType, EvaluatorCategory, EvaluatorMetric, EvaluatorMetricDirection,
    EvaluatorMetricType,
)
project.beta.evaluators.create_version(
    name="ComplianceCheck",
    evaluator_version=EvaluatorVersion(
        display_name="Compliance Check",
        description="Ensures response contains the required compliance phrase.",
        evaluator_type=EvaluatorType.CUSTOM,
        categories=[EvaluatorCategory.QUALITY],
        definition=CodeBasedEvaluatorDefinition(
            type=EvaluatorDefinitionType.CODE,
            code_text=source_text,
            entry_point="custom_compliance_phrase:evaluate",
        ),
        metrics=[EvaluatorMetric(
            type=EvaluatorMetricType.BOOLEAN,
            desirable_direction=EvaluatorMetricDirection.INCREASE,
            min_value=0, max_value=1, threshold=1, is_primary=True,
        )],
    ),
)
```

Pitfall: `project.beta.evaluators` does NOT have a `create` method, only `create_version`, `list`, `get_version`, etc.

Output: `artifacts/custom-evaluator.json` with id `azureai://accounts/ai-account-eyfs7o7lvdq7e/projects/ai-project-aiobs-foundry-20260520/evaluators/ComplianceCheck/versions/1`.

## 10. Red team (TC-080 .. TC-085)

```powershell
& '.venv\Scripts\python.exe' 'scripts\12-red-team.py' 2>&1 | Tee-Object -FilePath 'artifacts\redteam.log'
```

Critical pattern: use the `openai_client.evals` API plus `project.beta.evaluation_taxonomies`. The `project.beta.red_teams.create(RedTeam(target=AzureAIAgentTarget(...)))` path is broken on this SDK build (rejects `AzureAIAgent` target type even when patched). Three steps:

1. `openai_client.evals.create(data_source_config={"type":"azure_ai_source","scenario":"red_team"}, testing_criteria=[builtin.prohibited_actions, builtin.task_adherence(deployment_name), builtin.sensitive_data_leakage])`
2. `project.beta.evaluation_taxonomies.create(name=agent_version.name, body=EvaluationTaxonomy(taxonomy_input=AgentTaxonomyInput(risk_categories=[RiskCategory.PROHIBITED_ACTIONS], target=AzureAIAgentTarget(name, version))))`
3. `openai_client.evals.runs.create(eval_id, data_source={"type":"azure_ai_red_team","item_generation_params":{"type":"red_team_taxonomy","attack_strategies":["Flip","Base64","IndirectJailbreak"],"num_turns":3,"source":{"type":"file_id","id":taxonomy.id}},"target":target.as_dict()})`

Poll `openai_client.evals.runs.retrieve(run_id, eval_id)` every 30s until status in `{completed, failed, canceled, cancelled}` (script enforces a 30 min hard cap).

Output: `artifacts/redteam.json`, `redteam-taxonomy.json`, `redteam-run-create.json`, `redteam-run-final.json`.

## 11. Alerts (TC-090 .. TC-091)

The az `monitor scheduled-query` extension is broken on this build (missing `pkg_resources`). Use the REST helper:

```powershell
& '.venv\Scripts\python.exe' 'scripts\06b-alerts-rest.py'
```

What it creates (PUT to `Microsoft.Insights/scheduledQueryRules` API `2023-03-15-preview`):
- `alert-gen-ai-errors-15m` (severity 2, every 5m, window 15m): `requests | where name has "invoke_agent" | where success == false | summarize n=count() | where n > 0`
- `alert-gen-ai-p95-latency-15m` (severity 3, every 5m, window 15m): `requests | where name has "invoke_agent" | summarize p95=percentile(duration, 95) | where p95 > 30000`

Both wired to action group `ag-aiobs-silent` (no receivers; demo-safe).

Verify:

```powershell
$json = az rest --method get --url 'https://management.azure.com/subscriptions/463a82d4-1896-4332-aeeb-618ee5a5aa93/resourceGroups/rg-aiobs-foundry-20260520/providers/Microsoft.Insights/scheduledQueryRules?api-version=2023-03-15-preview'
($json | ConvertFrom-Json).value | ForEach-Object {
    [pscustomobject]@{ name = $_.name; sev = $_.properties.severity; enabled = $_.properties.enabled; ag = ($_.properties.actions.actionGroups | Select-Object -First 1).Split('/')[-1] }
} | Format-Table -AutoSize
```

## 12. Cleanup

```powershell
Push-Location 'agent'
& $AZD down --no-prompt --purge
Pop-Location
```

`--purge` is needed because the Foundry account is a Cognitive Services resource that defaults to soft-delete.

## Appendix: critical pitfalls observed

| Pitfall | Symptom | Fix |
|---|---|---|
| Wrong azd build | `azd deploy` ignores azure.yaml | Use `$env:LOCALAPPDATA\Programs\azd-local\azd.exe` 1.25.1 |
| Missing `services:` in azure.yaml | `azd deploy` no-op | Patch as shown in Section 3 |
| Wrong role name | `az role assignment create` "role not found" | Use `Foundry User` (NOT `Azure AI User`) |
| `evaluators.create` missing | `AttributeError` | Use `evaluators.create_version` |
| Missing `data_mapping` in continuous eval | `MissingRequiredDataMapping` 400 | Add `{"query":"{{item.input}}","response":"{{item.output}}"}` per evaluator |
| `red_teams.create(RedTeam(target=AzureAIAgentTarget))` | `Invalid target model config type: 'azure_ai_agent'` | Use `openai_client.evals.create` + `evaluation_taxonomies.create` + `evals.runs.create` |
| `azd ai agent invoke --message ...` | `unknown flag: --message` | Use positional: `azd ai agent invoke "text"` (the flag was removed in newer azd builds) |
| Continuous-eval rule shows `enabled=true` but `evals.runs.list` returns 0 | rule definition correct; no runs from `azd ai agent invoke` traffic; even after `store=true` direct posts the rule's server-side processor cadence is opaque (we saw a first run only after ~10-15 min) | (a) Drive `POST <agent-endpoint>/openai/responses?store=true` with `DefaultAzureCredential` (scope `https://ai.azure.com/.default`, NOT `cognitiveservices.azure.com` which returns 403 with empty body) via `scripts/18-trigger-eval-runs.py`, then wait. (b) For an immediate signal, fire the agent-batch eval via Foundry MCP `evaluation_agent_batch_eval_create` (see Section 8). |
| App Insights Agents pane "Evaluations" section is empty ("Already set up? There may be no recent activity.") | No eval runs landed inside the pane's selected time range. Continuous-eval rule alone is unreliable for this. | Fire a one-shot Foundry MCP `evaluation_agent_batch_eval_create` (recipe in Section 8): a batch with `intent_resolution, task_adherence, coherence, fluency, relevance` completes in <5 min with N>=1 passed runs. Then expand the pane's time range to "Last 4 hours" and reload. Pane rollup takes 15-30 min. On this deployment, run `evalrun_24c4a2d43da64d958111c505caa538db` returned `8 total / 5 passed / 3 failed`. |
| App Insights "Agents (preview)" pane shows empty tiles | `AppRequests` have parent `invoke_agent` spans with `gen_ai.*` attrs, but `AppDependencies | count == 0` (no `chat <model>` / `execute_tool` child spans). The pane is built on the OTel GenAI semconv span hierarchy and tiles like Models / Tokens / p95 latency / Tool Calls aggregate child spans only. Hosting layer (`ResponsesHostServer`) emits the parent request automatically, but Agent Framework's chat-client and agent instrumentation are gated by `ENABLE_INSTRUMENTATION` (default `false`). | **Fixed.** Add `ENABLE_INSTRUMENTATION=true` (and `ENABLE_SENSITIVE_DATA=true` outside prod) to `agent.yaml` `environment_variables`, redeploy with `& $AZD deploy --no-prompt`, drive 5-10 invokes, then verify `AppDependencies | where TimeGenerated > ago(15m) | summarize n=count() by Name, Type` shows `chat <deployment-name>` rows. We confirmed `chat gpt-4o-mini` rows with full `gen_ai.usage.input_tokens` / `output_tokens` / `request.model` / `response.model` attrs after redeploy. Wait 15-30 min for the pane rollup. |
| `az monitor scheduled-query` | `ModuleNotFoundError: pkg_resources` | Use ARM REST PUT (script 06b) |
| `az monitor app-insights query` returns JSON blob | unparseable table | Use `azure-monitor-query` Python SDK (script 13) |
| `agents.get_version(agent_name=...)` only | `TypeError: missing 1 required arg` | Pass BOTH `agent_name` AND `agent_version` |
| PS env var leaks `\r\n` | URL parse errors | `.Trim()` or `.Replace("`r","")` before use |
