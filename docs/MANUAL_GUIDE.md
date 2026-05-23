# Foundry agent observability: end-to-end manual implementation guide

This is the from-scratch path. Follow it on a Windows + PowerShell 7 box. Every step is the same one the autonomous run executed; nothing here is theoretical. Style note: no em-dashes (parentheses, commas, colons, or sentence splits are used instead).

## Goal

Stand up:

*   A Microsoft Foundry account + project + capability host
*   A deployed agent (`agent-framework-agent-basic-responses:1`) running on `gpt-4o-mini`
*   Live OpenTelemetry GenAI traces in App Insights
*   A continuous evaluation rule that grades every response with three built-in evaluators
*   A custom code-based evaluator (compliance phrase check) registered to the project
*   A red-team safety evaluation run against the deployed agent
*   Two scheduled-query alerts (error count + p95 latency) wired to a silent action group
*   A clean teardown command

Time: roughly 25-40 minutes of human time plus 15 minutes of polling.

## Prerequisites

Azure subscription where you can `Owner` or at least `Contributor` + `User Access Administrator` at the resource group scope. Cog Services account creation, project creation, RBAC writes, and Microsoft.Insights/scheduledQueryRules PUTs all need writes.

Region: `eastus2` is what the demo validated against. The Foundry capability host (`/agents`) is region-restricted; check `az cognitiveservices account list-kinds` for current availability.

Quota: 30K TPM for `gpt-4o-mini` GlobalStandard in the chosen region. Verify with `az cognitiveservices usage list -l eastus2` before provisioning.

Tools (versions actually validated against):

| Tool | Version | Notes |
| --- | --- | --- |
| PowerShell | 7.x (pwsh) | required for the scripts |
| az CLI | 2.86.0 |   |
| azd (Developer CLI) | 1.25.1 | install via `winget install Microsoft.Azd` then symlink, OR use the local build at `$env:LOCALAPPDATA\Programs\azd-local\azd.exe`. PATH-installed azd 1.23.10 silently drops the `services:` block, do not use it |
| Docker | 29.4.3 | needed by `azd up` to package the agent |
| Python | 3.12.x | for the eval/red-team helper scripts |

A working `az login` session in the right tenant + subscription before you start. The agent invoke flow uses `DefaultAzureCredential`, which will pick up your `az login` token chain.

## Workspace layout

```

  agent/                    # azd template root
    azure.yaml              # MUST contain `services:` block (see Step 2.2)
    src/
      agent-framework-agent-basic-responses/
        agent.yaml          # agent definition
    infra/                  # bicep that azd up runs
  scripts/                  # automation helpers (PowerShell + Python)
    04-warmup.ps1
    05-seed-traffic.ps1
    06b-alerts-rest.py
    10-continuous-eval.py
    11-custom-evaluator-register.py
    12-red-team.py
    13-telemetry-kql.py
    14-verify-continuous-eval.py
  evaluators/
    custom_compliance_phrase.py   # the code-based evaluator body
    custom_compliance_phrase.yaml # metadata
  prompts/                        # seed traffic corpora
  artifacts/                      # all run outputs land here
  .venv/                          # Python 3.12 venv for the helpers
```

## Step 0: bootstrap

```
git clone <your-fork-of-the-template>
cd <repo-root>

py -3.12 -m venv .venv
. .venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install `
    azure-ai-projects==2.1.0 `
    azure-identity `
    openai `
    pyyaml `
    python-dotenv `
    azure-monitor-opentelemetry `
    azure-monitor-query `
    requests
deactivate

$AZD = "$env:LOCALAPPDATA\Programs\azd-local\azd.exe"   # pinned build
& $AZD version    # confirm 1.25.1
```

Sign in:

```
az login --tenant <YOUR_TENANT_ID>
az account set --subscription <YOUR_SUB_ID>
& $AZD auth login --tenant-id <YOUR_TENANT_ID>
```

## Step 1: choose names + region

```
$Region = 'eastus2'
$EnvName = 'aiobs-foundry-' + (Get-Date -Format yyyyMMdd)   # azd env name = RG name suffix
$YourPrincipalId = (az ad signed-in-user show --query id -o tsv)
```

## Step 2: provision (azd up)

### 2.1 Create the azd env

```
cd agent
& $AZD env new $EnvName -l $Region --subscription <YOUR_SUB_ID>

& $AZD env set MODEL_DEPLOYMENT_NAME gpt-4o-mini
& $AZD env set MODEL_NAME            gpt-4o-mini
& $AZD env set MODEL_VERSION         2024-07-18
& $AZD env set MODEL_FORMAT          OpenAI
& $AZD env set MODEL_SKU_NAME        GlobalStandard
& $AZD env set MODEL_CAPACITY        30
& $AZD env set AZURE_PRINCIPAL_ID    $YourPrincipalId
```

### 2.2 Patch `azure.yaml` (mandatory)

The Foundry agent template ships without a `services:` block. Without it, `azd deploy` is a silent no-op. Edit `agent/azure.yaml`:

```
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

The service key MUST match the folder name under `src/` and the agent name in `agent.yaml`.

### 2.3 Run `azd up`

```
# Run from the azd project root (folder containing azure.yaml)
cd agent
& $AZD up --no-prompt
```

Typical timing: 7 min total. Phases:

*   Bicep deploy: ~2 min (Cog Services account, project, ACR, App Insights, Log Analytics)
*   Capability host (`accounts/{name}/agents`): ~3 min
*   Model deployment (`accounts/{name}/deployments/gpt-4o-mini`): ~30 s
*   Connections registered to the project: ~30 s

Outputs `azd env get-values` will include `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, `AZURE_AI_AGENT_NAME`, `AZURE_RESOURCE_GROUP`, etc.

### 2.4 Verify

```
$rg = (& $AZD env get-value AZURE_RESOURCE_GROUP)
az resource list -g $rg --query "[].{name:name,type:type}" -o table
```

Expect 5 top-level resource types (Foundry account, project, ACR, App Insights, Log Analytics) plus one `accounts/deployments` subresource.

## Step 3: patch the agent + deploy (TC-020 .. TC-023)

```
# still in agent/
& $AZD deploy --no-prompt
```

Sequence printed by azd:

1.  Packaging (Docker layer of the agent runtime)
2.  Publishing to ACR
3.  Creating agent (Foundry control plane)
4.  Waiting for agent to become active
5.  Registering env vars back into azd

First invoke:

```
& $AZD ai agent show
# expect: status=active, ID=agent-framework-agent-basic-responses:1

& $AZD ai agent invoke --new-session --new-conversation `
    "Reply with the word OK and nothing else."
```

Wait ~60 s, then verify telemetry landed:

```
$wsId = (az monitor log-analytics workspace show -g $rg -n logs-eyfs7o7lvdq7e --query customerId -o tsv)
az monitor log-analytics query -w $wsId --analytics-query "AppRequests | where TimeGenerated > ago(15m) | where Name has 'invoke_agent' | project Name, Success, DurationMs, AppRoleName | take 5" -o table
```

You should see `invoke_agent agent-framework-agent-basic-responses:1` with `Success=True`. The associated `customDimensions` blob contains the full OpenTelemetry GenAI semantic conventions (`gen_ai.system`, `gen_ai.operation.name`, `gen_ai.agent.id`, `gen_ai.conversation.id`, etc.).

## Step 4: RBAC (TC-030 .. TC-032)

For the agent to call its own evaluator and gen\_ai sub-services the Foundry account's system-assigned MI needs `Foundry User` at the **project** scope:

```
$accountMi = az resource show -g $rg `
    --resource-type Microsoft.CognitiveServices/accounts `
    -n ai-account-<your-suffix> `
    --query identity.principalId -o tsv

$projectScope = "/subscriptions/<sub>/resourceGroups/$rg/providers/Microsoft.CognitiveServices/accounts/ai-account-<suffix>/projects/ai-project-$EnvName"

az role assignment create `
    --assignee-object-id $accountMi `
    --assignee-principal-type ServicePrincipal `
    --role "Foundry User" `
    --scope $projectScope

az role assignment list --assignee $accountMi --all --query "[].{role:roleDefinitionName, scope:scope}" -o table
```

Critical: the role is named `Foundry User` (definition id `53ca6127-db72-4b80-b1b0-d745d6d5456d`). The older name `Azure AI User` does NOT resolve. `az role definition list --name "Foundry User"` is the canonical lookup.

## Step 5: warmup + seed traffic (TC-040 .. TC-042)

```
cd ..   # back to 
pwsh -NoProfile -File scripts/04-warmup.ps1
```

This pings the agent 3 times via `azd ai agent invoke`. It exists so that the rest of the pipeline (continuous eval, alerts) has at least one trace to anchor on.

Then seed full corpora:

```
pwsh -NoProfile -File scripts/05-seed-traffic.ps1 -SleepSeconds 1
```

> **Note:** The script is intentionally silent while running. All agent replies are written to `artifacts/seed-<timestamp>.log`, not to the terminal. The only console output is `"Seed complete: <path>"` at the very end. It typically takes 4-8 minutes. To tail progress in a second terminal: `Get-ChildItem artifacts/seed-*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Wait`.

48 prompts go through. The script picks them from `prompts/`:

*   `golden-qa.txt` (15 prompts)
*   `tools.txt` (10 prompts)
*   `safety-bait.txt` (5 prompts intended to be refused)
*   `multi-turn.txt` (4 conversations of 4-5 turns)

Validate count:

```
& { $log = Get-ChildItem artifacts/seed-*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1; $c = Get-Content $log.FullName -Raw; "prompts sent:     $(([regex]::Matches($c, '(?m)^## \[')).Count)"; "replies received: $(([regex]::Matches($c, '\[agent-framework-')).Count)"; "traces emitted:   $(([regex]::Matches($c, '(?m)^Trace ID:')).Count)" }
```

Expect 48 / 48 / 48.

Safety-bait refusal check (TC-042): grep the safety-bait section of the log for `I'm sorry, I can't assist with that.` or `I can't assist with that.`. With the default Foundry safety filter on `gpt-4o-mini`, 4 of the 5 bait prompts get refused. The 5th, framed as "graphic battle for my novel", does generate violent content. Treat that as a finding for the red-team scan to confirm and for the continuous eval `violence` evaluator to flag.

## Step 5.5: enrich the Agents pane (multi-model, multi-tool, Gen AI errors)

With only `agent-framework-agent-basic-responses` deployed and zero tools, the App Insights Agents (preview) pane shows Agent Runs and Tokens but the Tool Calls table stays empty and the Gen AI Errors chart shows nothing. This step layers in tools, additional models, and a deliberately broken agent so every tile on the pane lights up. Skip this step only if you do not care about the pane's screenshot fidelity.

### 5.5.1 Wire `@tool` functions into the agent (Tool Calls + tool errors)

In `agent/src/agent-framework-agent-basic-responses/main.py`, add six `@tool` functions and pass them into the `Agent(tools=[...])` constructor. Three of the six raise on bad input so they emit failed `execute_tool` spans:

```python
from agent_framework import Agent, tool
from typing import Annotated
from pydantic import Field

_FAKE_ORDERS    = {"C001": [...], "C002": [...], "C003": []}
_FAKE_SUPPLIERS = {1001: [...], 1002: [...]}
_FAKE_SUPPLIER_DETAILS = {"S-77": {...}, "S-88": {...}, "S-91": {...}}

@tool(name="get_orders", description="Get all orders for a customer id.")
def get_orders(customer_id: Annotated[str, Field(description="e.g. C001")]) -> str:
    orders = _FAKE_ORDERS.get(customer_id.upper())
    if orders is None:
        raise LookupError(f"Unknown customer_id: {customer_id}")
    return f"Customer {customer_id} has {len(orders)} order(s): {orders}"

@tool(name="find_suppliers_for_request", description="Find suppliers for a request id (>=1000).")
def find_suppliers_for_request(request_id: Annotated[int, Field(ge=1)]) -> str:
    if request_id < 1000:
        raise ValueError(f"request_id must be >= 1000, got {request_id}")
    suppliers = _FAKE_SUPPLIERS.get(request_id)
    if suppliers is None:
        raise LookupError(f"No suppliers indexed for request {request_id}")
    return f"Request {request_id}: {len(suppliers)} supplier(s) -> {suppliers}"

@tool(name="get_company_supplier_info", description="Get details for a supplier id.")
def get_company_supplier_info(supplier_id: Annotated[str, Field()]) -> str:
    info = _FAKE_SUPPLIER_DETAILS.get(supplier_id.upper())
    if info is None:
        raise LookupError(f"Unknown supplier_id: {supplier_id}")
    return f"Supplier {supplier_id}: {info}"

# Three always-succeed tools for happy-path Tool Calls volume:
@tool(name="get_current_utc_date")
def get_current_utc_date() -> str: ...
@tool(name="get_weather")
def get_weather(city: Annotated[str, Field()]) -> str: ...
@tool(name="roll_dice")
def roll_dice(sides: Annotated[int, Field(ge=2)]) -> str: ...
```

The agent instructions must explicitly tell the model to call tools and to report tool errors (otherwise the model papers over `LookupError`/`ValueError` and the Errors column stays at 0):

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

```
cd agent
& $AZD deploy agent-framework-agent-basic-responses --no-prompt
cd ..
```

Drive 12 prompts that mix valid IDs with intentionally bad ones (the three raise paths must each fire at least once):

```
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
cd agent
foreach ($p in $prompts) {
    & $AZD ai agent invoke --new-session --new-conversation agent-framework-agent-basic-responses $p 2>&1 | Select-Object -Last 2
    Start-Sleep -Milliseconds 400
}
cd ..
```

Verify (allow ~60-90 s for ingest):

```
$wsId = (az monitor log-analytics workspace show -g $rg -n logs-eyfs7o7lvdq7e --query customerId -o tsv)
$q = "AppDependencies | where TimeGenerated > ago(15m) | where Name startswith 'execute_tool' | summarize n=count(), errs=countif(Success==false) by Name | order by n desc"
az monitor log-analytics query -w $wsId --analytics-query $q -o table
```

Expect 6 rows, with non-zero `errs` on `get_orders`, `find_suppliers_for_request`, and `get_company_supplier_info`.

### 5.5.2 Add additional model deployments and sister hosted agents (multi-model Models tile)

Pre-create the additional model deployments on the SAME Foundry account (azd does not add deployments after the initial provision; use the Cog Services CLI):

```
az cognitiveservices account deployment create -g $rg -n ai-account-<suffix> `
    --deployment-name gpt-5-mini --model-name gpt-5-mini --model-version 2025-08-07 `
    --model-format OpenAI --sku-name GlobalStandard --sku-capacity 100
az cognitiveservices account deployment create -g $rg -n ai-account-<suffix> `
    --deployment-name gpt-4.1-mini --model-name gpt-4.1-mini --model-version 2025-04-14 `
    --model-format OpenAI --sku-name GlobalStandard --sku-capacity 100
az cognitiveservices account deployment list -g $rg -n ai-account-<suffix> -o table
```

Clone the basic-responses project directory once per new model (each sister agent shares main.py / Dockerfile / requirements.txt; only its `agent.yaml` differs):

```
$src = 'agent\src\agent-framework-agent-basic-responses'
Copy-Item -Path $src -Destination "$src\..\agent-framework-agent-gpt5-mini"  -Recurse -Force
Copy-Item -Path $src -Destination "$src\..\agent-framework-agent-gpt41-mini" -Recurse -Force
```

Edit each clone's `agent.yaml` to (a) rename `name:`, and (b) HARDCODE the model env var (do not interpolate `${AZURE_AI_MODEL_DEPLOYMENT_NAME}`; that resolves to the azd-env value which is the same for every service):

```
# agent/src/agent-framework-agent-gpt5-mini/agent.yaml
kind: hosted
name: agent-framework-agent-gpt5-mini
protocols:
  - protocol: responses
    version: 1.0.0
resources: { cpu: '0.25', memory: '0.5Gi' }
environment_variables:
  - { name: AZURE_AI_MODEL_DEPLOYMENT_NAME, value: "gpt-5-mini" }
  - { name: ENABLE_INSTRUMENTATION,         value: "true" }
  - { name: ENABLE_SENSITIVE_DATA,          value: "true" }
```

Same shape for `agent-framework-agent-gpt41-mini` with `value: "gpt-4.1-mini"`.

Append both as services in `agent/azure.yaml`. Sister agents do NOT need a `deployments[]` block (they target the deployments you created above with `az cognitiveservices`); only the original basic-responses service keeps its `deployments[]` block:

```
services:
  agent-framework-agent-basic-responses:
    project: src/agent-framework-agent-basic-responses
    host: azure.ai.agent
    language: docker
    docker: { remoteBuild: true }
    config:
      container: { resources: { cpu: "0.25", memory: 0.5Gi } }
      deployments:
        - model: { format: OpenAI, name: gpt-4o-mini, version: "2024-07-18" }
          name: gpt-4o-mini
          sku:  { capacity: 30, name: GlobalStandard }
  agent-framework-agent-gpt5-mini:
    project: src/agent-framework-agent-gpt5-mini
    host: azure.ai.agent
    language: docker
    docker: { remoteBuild: true }
    config:
      container: { resources: { cpu: "0.25", memory: 0.5Gi } }
  agent-framework-agent-gpt41-mini:
    project: src/agent-framework-agent-gpt41-mini
    host: azure.ai.agent
    language: docker
    docker: { remoteBuild: true }
    config:
      container: { resources: { cpu: "0.25", memory: 0.5Gi } }
```

Deploy:

```
cd agent
& $AZD deploy agent-framework-agent-gpt5-mini  --no-prompt
& $AZD deploy agent-framework-agent-gpt41-mini --no-prompt
cd ..
```

Fan out the same 12-prompt set across all three agents (this yields ~3 errors per raising tool, ~36 total Tool Calls, and 3 distinct `chat <model>` span names):

```
cd agent
foreach ($agent in @('agent-framework-agent-basic-responses', 'agent-framework-agent-gpt5-mini', 'agent-framework-agent-gpt41-mini')) {
    foreach ($p in $prompts) {
        & $AZD ai agent invoke --new-session --new-conversation $agent $p 2>&1 | Select-Object -Last 2
        Start-Sleep -Milliseconds 400
    }
}
cd ..
```

Verify three distinct chat-model rows:

```
$q = "AppDependencies | where TimeGenerated > ago(20m) | where Name startswith 'chat ' | summarize n=count(), errs=countif(Success==false) by Name | order by n desc"
az monitor log-analytics query -w $wsId --analytics-query $q -o table
```

### 5.5.3 Add a deliberately broken agent (Gen AI Errors pie shows chat-level errors)

The Gen AI Errors chart's `chat *` slices only light up when an actual chat call fails (an `execute_tool` failure does NOT count as a chat error). The most reliable trigger is a fourth hosted agent pointing at a model deployment name that does not exist:

```
$src = 'agent\src\agent-framework-agent-basic-responses'
Copy-Item -Path $src -Destination "$src\..\agent-framework-agent-broken-model" -Recurse -Force
```

`agent/src/agent-framework-agent-broken-model/agent.yaml`:

```
kind: hosted
name: agent-framework-agent-broken-model
protocols:
  - protocol: responses
    version: 1.0.0
resources: { cpu: '0.25', memory: '0.5Gi' }
environment_variables:
  - { name: AZURE_AI_MODEL_DEPLOYMENT_NAME, value: "nonexistent-model-deployment-xyz" }
  - { name: ENABLE_INSTRUMENTATION,         value: "true" }
  - { name: ENABLE_SENSITIVE_DATA,          value: "true" }
```

Append a fourth service block to `agent/azure.yaml` (same shape as the gpt5-mini block above, with `project: src/agent-framework-agent-broken-model`). Deploy:

```
cd agent
& $AZD deploy agent-framework-agent-broken-model --no-prompt
cd ..
```

The container starts fine (Foundry does not validate model existence at deploy time); only the chat call inside the response handler 404s at runtime. Drive 5-8 invokes:

```
cd agent
1..8 | ForEach-Object {
    & $AZD ai agent invoke --new-session --new-conversation agent-framework-agent-broken-model "ping $_" 2>&1 | Select-Object -Last 2
    Start-Sleep -Milliseconds 400
}
cd ..
```

Verify failed chat spans land under the fake model name:

```
$q = "AppDependencies | where TimeGenerated > ago(15m) | where Name startswith 'chat ' | summarize n=count(), errs=countif(Success==false) by Name | order by errs desc"
az monitor log-analytics query -w $wsId --analytics-query $q -o table
```

Expected: a row `chat nonexistent-model-deployment-xyz` with `errs == n`. The Agents pane will now show:

*   **Agent with highest errors**: `agent-framework-agent-broken-model`
*   **Gen AI Errors** stacked bar: slices for `chat (Other Sum)`, `invoke_agent (Other Sum)`, `execute_tool (Other Sum)`
*   **Tool Calls** table: 6 rows, 3 with non-zero Errors
*   **Models** table: gpt-5-mini, gpt-4.1-mini, gpt-4o-mini, nonexistent-model-deployment-xyz (the last with high error count)
*   **Token Consumption by Model** + **Input vs Output Tokens**: split across the working models

Pane rollup takes 15-30 min after the spans land in Log Analytics.

To extend or replace the Agents pane with custom Grafana panels, see [docs/GRAFANA\_GUIDE.md](./GRAFANA_GUIDE.md). It walks the embedded "Dashboards with Grafana" experience in this same App Insights resource, the three prebuilt Gen AI dashboards, 5 schema-matched KQL panels, and the importable [artifacts/grafana/agent-observability-custom-dashboard.json](../artifacts/grafana/agent-observability-custom-dashboard.json).

## Step 6: telemetry KQL (TC-050 .. TC-053)

The `az monitor app-insights query` CLI mishandles JSON-typed columns and returns raw blobs. Use the Logs Query API via Python instead:

```
$env:LOG_ANALYTICS_WORKSPACE_ID = (az monitor log-analytics workspace show -g $rg -n logs-eyfs7o7lvdq7e --query customerId -o tsv)
$env:APPLICATIONINSIGHTS_RESOURCE_ID = (az resource show -g $rg -n appi-eyfs7o7lvdq7e --resource-type microsoft.insights/components --query id -o tsv)
& .venv\Scripts\python.exe scripts/13-telemetry-kql.py
```

Output: `artifacts/telemetry.json` with four sections (volume + success, latency percentiles, session/time buckets, token usage).

Observed limitation: the agent server in `azure-ai-projects==2.1.0` does NOT surface `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` on the `invoke_agent` request span. The token-usage section will report `with_token_attrs: 0`. The model-level tokens are still visible inside the Cog Services account metrics (use `az monitor metrics list`).

If you prefer raw KQL in the App Insights blade:

```
requests
| where name has "invoke_agent"
| extend success_b = tobool(success)
| summarize total = count(),
            success = countif(success_b == true),
            failed  = countif(success_b == false),
            unique_traces = dcount(operation_Id)
  by name
```

```
requests
| where name has "invoke_agent"
| summarize n = count(),
            p50_ms = percentile(duration, 50),
            p95_ms = percentile(duration, 95),
            p99_ms = percentile(duration, 99),
            max_ms = max(duration)
```

### "Agents (preview)" view in App Insights shows empty

The Agents (preview) pane in App Insights is built on top of the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) and needs the full span hierarchy to render: a parent `invoke_agent <name>` request span plus child dependencies `chat <model>` (LLM call) and, where present, `execute_tool <function>` (function call). The Models, Tokens, p95 latency by model, and Tool Calls tiles all summarize child spans. If the agent only emits the parent request span and no child spans, the pane stays empty even though raw `AppRequests` look healthy.

There are two independent reasons this happens with a Foundry-hosted Microsoft Agent Framework agent:

1.  **Hosted agent kind is still preview for tracing.** Microsoft Learn states: "Tracing is generally available for prompt agents only. Workflow, hosted, and custom agents are in preview." Our agent is `kind: hosted`, so any gap here is an in-flight preview limitation.
2.  **Agent Framework instrumentation is opt-in.** The chat client and agent code paths only emit child `chat`/`execute_tool` spans when `ENABLE_INSTRUMENTATION=true` (default `false`). Without it, the hosting layer (`ResponsesHostServer`) still wires up Application Insights and emits the parent `invoke_agent` request, but the `FoundryChatClient` call never gets a span, so there are zero `AppDependencies`.

Diagnose in this order:

Confirm raw parent telemetry:

If `n=0`, drive fresh invokes and re-run. Telemetry lands within 1-2 minutes.

Check whether child spans are being emitted at all:

If `n=0` while `AppRequests` show `invoke_agent` rows, the chat client isn't instrumented. Fix it: add the two env vars below to `agent.yaml`, redeploy with `& $AZD deploy --no-prompt`, drive a few invokes, then re-query. You should see rows like `chat gpt-4o-mini` plus `invoke_agent <guid>` (client-side parent) under `AppDependencies` within 1-2 minutes.

`ENABLE_INSTRUMENTATION=true` activates Agent Framework's OTel code paths (default `false`). `ENABLE_SENSITIVE_DATA=true` captures prompts/responses (`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`) on those child spans so the Search overlay (Investigate traces) and the Tokens tile actually show useful content. Drop the sensitive flag in production if traces are queryable by parties who shouldn't see prompts.

Confirmed-working chat-span shape after the fix (sample from `artifacts/sample-chat-dependency.json`):

Confirm the spans carry the `gen_ai.*` semconv (`AppRequests | take 1 | project Properties` should contain `gen_ai.system`, `gen_ai.agent.id`, `gen_ai.operation.name`, `microsoft.foundry.project.id`).

Confirm the App Insights resource is registered as a project connection:

You want a row of type `AppInsights` pointing at your `appi-*` resource. If missing, add it via the Foundry portal Observability page or `project.connections.create(...)`.

If all four look healthy and you still see empty tiles, the cause is projection lag. The pane aggregates GenAI spans on a 15-30 min cadence, and a freshly-provisioned App Insights resource can take 1-2 hours to first populate. Switch the time range from "Last 12 hours" to "Last 24 hours" and re-check after 30 min.

## Step 7: continuous eval (TC-060 .. TC-066)

Continuous eval = an evaluation group attached to a rule that fires on every `RESPONSE_COMPLETED` event for a given agent. The agent server feeds each response into the group; results land back in the Foundry project as evaluation runs.

Hydrate env vars from the azd env into the current shell first:

```
Push-Location agent
$env_text = & $AZD env get-values
$env_text -split "`n" | ForEach-Object {
    if ($_ -match '^\s*([A-Z0-9_]+)="?(.*?)"?\s*$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
Pop-Location
```

Then create the eval group + rule:

```
& .venv\Scripts\python.exe scripts/10-continuous-eval.py
```

The script wires three built-in evaluators (`intent_resolution`, `violence`, `tool_call_accuracy`) under a `data_source_config={"type":"azure_ai_source","scenario":"responses"}` group. Every evaluator MUST include `data_mapping`. Without it, the API rejects with `MissingRequiredDataMapping`:

```python
common_qr = {"query": "{{item.input}}", "response": "{{item.output}}"}
testing_criteria = [
    {
        "type": "azure_ai_evaluator",
        "name": "Intent Resolution",
        "evaluator_name": "builtin.intent_resolution",
        "evaluator_version": "1",
        "data_mapping": common_qr,
        "initialization_parameters": {"deployment_name": model_deployment},
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
        "initialization_parameters": {"deployment_name": model_deployment},
    },
]
```

The rule (note `project.evaluation_rules`, NOT `project.beta.evaluation_rules` or `project.beta.continuous_evaluation_rules`, both of which do not exist):

```python
from azure.ai.projects.models import (
    ContinuousEvaluationRuleAction, EvaluationRule,
    EvaluationRuleEventType, EvaluationRuleFilter,
)

rule = project.evaluation_rules.create_or_update(
    id="demo-continuous-eval",
    evaluation_rule=EvaluationRule(
        display_name="Demo continuous eval",
        description="Runs on every response completion for the demo agent",
        action=ContinuousEvaluationRuleAction(
            eval_id=eval_object.id, max_hourly_runs=100,
        ),
        event_type=EvaluationRuleEventType.RESPONSE_COMPLETED,
        filter=EvaluationRuleFilter(agent_name=agent_name),
        enabled=True,
    ),
)
```

Output: `artifacts/continuous-eval.json` (eval\_id + rule\_id).

To trigger runs you do not need anything extra: any new invoke of the targeted agent will cause the rule to fire and an eval run to be created. To verify after a fresh invoke (give it 60-120 s):

```
& .venv\Scripts\python.exe scripts/14-verify-continuous-eval.py
```

The script lists runs under the eval and dumps the latest run's output items into `artifacts/continuous-eval-runs.json` and `artifacts/continuous-eval-latest-items.json`.

**Known issue (observed on this run):** the rule is created correctly (`enabled=true`, filter matches, `data_mapping` set), but `evals.runs.list(eval_id)` may return 0 even after many `azd ai agent invoke` calls. Two compounding causes:

1.  `azd ai agent invoke` does not persist responses to the store the continuous-eval pipeline scans.
2.  Even with `store=true` traffic landing, the rule's server-side processor has an opaque cadence (we saw a first run only after ~10-15 min on this deployment).

Force-fill the store with the helper script `scripts/18-trigger-eval-runs.py` (canonical recipe; do not copy the older snippet below verbatim, the scope is different):

```python
from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

# CRITICAL: per-agent /openai/responses uses ai.azure.com, NOT cognitiveservices.
# cognitiveservices.azure.com/.default returns 403 with empty body.
# management.azure.com/.default returns 401 "Token not supported".
token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://ai.azure.com/.default",
)
base_url = os.environ["AZURE_AI_PROJECT_ENDPOINT"] + \
    "/agents/agent-framework-agent-basic-responses/endpoint/protocols/openai"
client = OpenAI(
    base_url=base_url, api_key="placeholder",
    default_query={"api-version": "2025-11-15-preview"},
    default_headers={"Authorization": f"Bearer {token_provider()}"},
)
client.responses.create(
    model="gpt-4o-mini",
    input="List orders for customer C001.",
    store=True,  # <-- this is the key
)
```

**Reliable fallback that actually populates the Agents pane on a 5 min budget:** skip the rule for demos and fire a one-shot agent-batch eval through the Foundry MCP tool `evaluation_agent_batch_eval_create` (or POST the same body to `<project>/evaluations/agent-batch-eval`). Helper: `scripts/20-agent-batch-eval.py`. Body:

```
{
  "agentName": "agent-framework-agent-basic-responses",
  "agentVersion": "5",   // get via mcp_foundry_mcp_agent_get
  "deploymentName": "gpt-4o-mini",
  "evaluatorNames": ["intent_resolution","task_adherence","coherence","fluency","relevance"],
  "evaluationName": "Demo agent batch eval",
  "runName": "demo-agent-batch-run-1",
  "inputData": [{"query": "List orders for customer C001."}, /* ... */]
}
```

Verified on this deployment: `eval_dca182f7290c487f8a01ec30ac9e302b` / `evalrun_24c4a2d43da64d958111c505caa538db` completed in \<5 min with `total=8, passed=5, failed=3, errored=0, skipped=0`. Pane rollup is a further 15-30 min.

The original `store=true` snippet (kept for reference, but DO NOT use `cognitiveservices.azure.com` scope; it 403s):

```python
from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
)
endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"] + \
    "/agents/agent-framework-agent-basic-responses/endpoint/protocols/openai"
client = OpenAI(base_url=endpoint, api_key="placeholder")
client.responses.create(
    model="gpt-4o-mini",
    input="What is the capital of France?",
    store=True,  # <-- this is the key
    extra_headers={"Authorization": f"Bearer {token_provider()}"},
)
```

To inspect rule state independently:

```
& .venv\Scripts\python.exe scripts/16-list-rules.py    # dumps every rule in the project
& .venv\Scripts\python.exe scripts/15-list-eval-rules.py # dumps the eval definition + run list
```

### Reading the Evaluations pane (post-rollup)

The Agents pane "Evaluations" section renders one tile per evaluator. Each tile has its own `Evaluation` dropdown (all five evaluators are available in every dropdown), a time series, and a `Score (Avg)` summary. Scales differ per evaluator and the pane does NOT normalize them, so do not compare absolute numbers across tiles.

| Evaluator | Scale | Pass criterion (default) | Avg from `demo-agent-batch-run-1` |
| --- | --- | --- | --- |
| `intent_resolution` | 1-5 Likert | score >= 3 | 4.13 |
| `task_adherence` | 0-1 (binary-like) | score == 1 | 0.75 |
| `coherence` | 1-5 Likert | score >= 3 | 3.5 |
| `fluency` | 1-5 Likert | score >= 3 | 3 |
| `relevance` | 1-5 Likert | score >= 3 | (open the dropdown to view) |

What to expect visually:

*   A single run produces one dot per tile at the run timestamp. Fire more batch runs (re-run `scripts/20-agent-batch-eval.py`) to get a trend line and a moving average.
*   The pass/fail totals live in the run, not the tiles: read `total / passed / failed / errored / skipped` via `oc.evals.runs.retrieve(run_id, eval_id)`. On the verified run, that returned `8 / 5 / 3 / 0 / 0`.
*   Rollup lag: tiles populate 15-30 min after a run completes. The raw API has data immediately.
*   If a tile reads "Already set up? There may be no recent activity.", widen the time range to "Last 4 hours" before assuming the run did not land.
*   Other tiles on the same pane (Models, Tokens, Tool Calls, Latency, Gen AI errors) come from `AppRequests` + `AppDependencies`, not from evals. They have an independent rollup cadence and require `ENABLE_INSTRUMENTATION=true` on the agent (already set in `agent.yaml`).

## Step 8: custom evaluator (TC-070 .. TC-071)

Register a Python evaluator into the project. Inside `evaluators/custom_compliance_phrase.py`:

```python
REQUIRED_PHRASE = "this response is for informational purposes only."

def evaluate(*, response: str, **_) -> dict:
    text = (response or "").lower()
    ok = REQUIRED_PHRASE in text
    return {
        "compliance_pass": 1.0 if ok else 0.0,
        "compliance_pass_label": "pass" if ok else "fail",
        "compliance_reason": "phrase present" if ok else "phrase missing",
    }
```

Register it:

```
& .venv\Scripts\python.exe scripts/11-custom-evaluator-register.py
```

Key API shape (this is what works on `azure-ai-projects==2.1.0`; pre-2.1 docs that say `evaluators.create(...)` are stale):

```python
from azure.ai.projects.models import (
    CodeBasedEvaluatorDefinition, EvaluatorDefinitionType, EvaluatorVersion,
    EvaluatorType, EvaluatorCategory, EvaluatorMetric,
    EvaluatorMetricDirection, EvaluatorMetricType,
)

source = pathlib.Path("evaluators/custom_compliance_phrase.py").read_text()
project.beta.evaluators.create_version(
    name="ComplianceCheck",
    evaluator_version=EvaluatorVersion(
        display_name="Compliance Check",
        description="Ensures response contains the required compliance phrase.",
        evaluator_type=EvaluatorType.CUSTOM,
        categories=[EvaluatorCategory.QUALITY],
        definition=CodeBasedEvaluatorDefinition(
            type=EvaluatorDefinitionType.CODE,
            code_text=source,
            entry_point="custom_compliance_phrase:evaluate",
        ),
        metrics=[EvaluatorMetric(
            type=EvaluatorMetricType.BOOLEAN,
            desirable_direction=EvaluatorMetricDirection.INCREASE,
            min_value=0, max_value=1, threshold=1, is_primary=True,
        )],
        metadata={"team": "platform-ai", "demo": "aiobs"},
        tags=["compliance", "demo"],
    ),
)
```

Output: `artifacts/custom-evaluator.json` with id `azureai://accounts/<account>/projects/<project>/evaluators/ComplianceCheck/versions/1`.

To exercise the new evaluator inside continuous eval, add this entry to `testing_criteria` in script 10 (re-run script 10 with a new eval-group name to swap):

```python
{
    "type": "azure_ai_evaluator",
    "name": "Compliance Check",
    "evaluator_name": "ComplianceCheck",
    "evaluator_version": "1",
    "data_mapping": {"response": "{{item.output}}"},
},
```

## Step 9: red team (TC-080 .. TC-085)

Red team = a Foundry-managed adversarial scan that auto-generates adversarial prompts (across attack strategies like `Flip`, `Base64`, `IndirectJailbreak`), sends them to the agent under test, and scores responses against built-in safety evaluators.

```
& .venv\Scripts\python.exe scripts/12-red-team.py 2>&1 | Tee-Object -FilePath artifacts/redteam.log
```

What it does (3 steps, in order):

1.  **Create eval group** via `openai_client.evals.create` with `data_source_config={"type":"azure_ai_source","scenario":"red_team"}` and three built-in safety evaluators (`prohibited_actions`, `task_adherence` with `deployment_name` init param, `sensitive_data_leakage`).
2.  **Create taxonomy** via `project.beta.evaluation_taxonomies.create(name=agent_version.name, body=EvaluationTaxonomy(taxonomy_input=AgentTaxonomyInput(risk_categories=[RiskCategory.PROHIBITED_ACTIONS], target=AzureAIAgentTarget(name, version))))`.
3.  **Create run** via `openai_client.evals.runs.create(eval_id, data_source={"type":"azure_ai_red_team","item_generation_params":{"type":"red_team_taxonomy","attack_strategies":["Flip","Base64","IndirectJailbreak"],"num_turns":3,"source":{"type":"file_id","id":taxonomy.id}},"target":target.as_dict()})`.

The script polls `openai_client.evals.runs.retrieve(run_id, eval_id)` every 30 s (cap 30 min) until status hits `{completed, failed, canceled, cancelled}`. Typical wall time: 4-6 minutes.

Important pitfall: the `project.beta.red_teams.create(RedTeam(target=AzureAIAgentTarget(...)))` path that older samples reference is broken on `azure-ai-projects==2.1.0`. It rejects the agent target with `Invalid target model config type: 'azure_ai_agent'`, and even patching the wire type to `AzureAIAgent` fails deserialization. The `openai_client.evals` + `evaluation_taxonomies` flow above is the canonical one (per the MS Learn doc `run-ai-red-teaming-cloud` and the SDK sample `sample_scheduled_evaluations.py`).

Outputs (in `artifacts/`):

*   `redteam-taxonomy.json` (taxonomy id used by the run)
*   `redteam-run-create.json` (initial run state)
*   `redteam-run-final.json` (final status + result urls)
*   `redteam_eval_output_items_<agent>.json` (per-prompt verdicts; may be empty if the run reports `completed` with zero generated items; check the Foundry UI to confirm)
*   `redteam.json` (summary)

## Step 10: alerts (TC-090 .. TC-091)

The `az monitor scheduled-query` CLI extension is broken on this CLI build (`ModuleNotFoundError: pkg_resources`). Skip it; talk to ARM REST directly:

```
& .venv\Scripts\python.exe scripts/06b-alerts-rest.py
```

This:

1.  Creates action group `ag-aiobs-silent` (no receivers; demo-safe). Already idempotent.
2.  PUTs two scheduled-query rules to `Microsoft.Insights/scheduledQueryRules` (`api-version=2023-03-15-preview`):
    *   `alert-gen-ai-errors-15m` (sev 2, eval every 5m, window 15m): `requests | where name has "invoke_agent" | where success == false | summarize n=count() | where n > 0`
    *   `alert-gen-ai-p95-latency-15m` (sev 3, eval every 5m, window 15m): `requests | where name has "invoke_agent" | summarize p95=percentile(duration, 95) | where p95 > 30000`

Verify (REST again, since the broken CLI extension also breaks `az monitor scheduled-query list`):

```
$json = az rest --method get --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/$rg/providers/Microsoft.Insights/scheduledQueryRules?api-version=2023-03-15-preview"
($json | ConvertFrom-Json).value | ForEach-Object {
    [pscustomobject]@{
        name        = $_.name
        sev         = $_.properties.severity
        enabled     = $_.properties.enabled
        actionGroup = ($_.properties.actions.actionGroups | Select-Object -First 1).Split('/')[-1]
    }
} | Format-Table -AutoSize
```

## Step 11: end-to-end sanity (TC-100 .. TC-101)

After all the above, a single invoke should now drive:

*   one App Insights `invoke_agent` request span
*   one continuous-eval run (visible via `openai_client.evals.runs.list`)
*   (if applicable) a tripped scheduled-query alert (visible via `Microsoft.Insights/alerts`)

End-to-end one-liner:

```
cd agent
& $AZD ai agent invoke --new-session --new-conversation `
    "What time is it in Tokyo? Be brief and add 'This response is for informational purposes only.' at the end."
cd ..
```

Then wait ~90 s and re-run `scripts/14-verify-continuous-eval.py`. The new run should appear with `Compliance Check` either pass or fail depending on whether the model honored the compliance suffix.

## Step 12: cleanup

```
cd agent
& $AZD down --no-prompt --purge
```

`--purge` is mandatory: Cog Services accounts soft-delete by default and block recreating with the same name for 7+ days unless purged.

Optional belt-and-braces:

```
az group delete -n $rg --yes --no-wait
```

## Appendix A: full env var reference

After `azd up` + `azd deploy`, `agent/.azure/<env>/.env` will contain:

```
AZURE_LOCATION="eastus2"
AZURE_RESOURCE_GROUP="rg-aiobs-foundry-20260520"
AZURE_SUBSCRIPTION_ID="<sub>"
AZURE_TENANT_ID="<tenant>"
AZURE_ENV_NAME="aiobs-foundry-20260520"
AZURE_PRINCIPAL_ID="<your user object id>"
AZURE_AI_ACCOUNT_NAME="ai-account-<suffix>"
AZURE_AI_PROJECT_NAME="ai-project-aiobs-foundry-20260520"
AZURE_AI_PROJECT_ENDPOINT="https://ai-account-<suffix>.services.ai.azure.com/api/projects/ai-project-aiobs-foundry-20260520"
AZURE_AI_AGENT_NAME="agent-framework-agent-basic-responses"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
APPLICATIONINSIGHTS_CONNECTION_STRING="<full conn string>"
```

The Python scripts under `scripts/` all source this file via `python-dotenv`.

## Appendix B: pitfalls and fixes (worth memorizing)

| Pitfall | Symptom | Fix |
| --- | --- | --- |
| Wrong azd build (PATH 1.23.10) | `azd deploy` ignores `services:` and is a no-op | Pin to `$env:LOCALAPPDATA\Programs\azd-local\azd.exe` (1.25.1+) |
| Missing `services:` in `azure.yaml` | `azd deploy` prints `No services found.` | Add the block in Step 2.2 verbatim |
| Wrong role name `Azure AI User` | `az role assignment create` errors `role not found` | Use `Foundry User` |
| `evaluators.create(...)` | `AttributeError: 'EvaluatorsOperations' object has no attribute 'create'` | Use `create_version` with `EvaluatorVersion(...)` |
| `MissingRequiredDataMapping` 400 from continuous eval | one or more evaluators missing `data_mapping` | Add `{"query":"{{item.input}}","response":"{{item.output}}"}` per evaluator (tool eval uses `tool_definitions: "{{item.tools}}"`) |
| `Invalid target model config type: 'azure_ai_agent'` from `red_teams.create` | SDK red\_teams path rejects AzureAIAgent target | Switch to `openai_client.evals.create` + `evaluation_taxonomies.create` + `evals.runs.create` (Step 9 sequence) |
| `ModuleNotFoundError: pkg_resources` from `az monitor scheduled-query` | extension's vendored SDK is broken on this CLI build | Use ARM REST PUT (Step 10 script) |
| `az monitor app-insights query` returns unreadable JSON | columns with JSON values | Use `azure-monitor-query` Python SDK (Step 6 script) |
| `agents.get_version` `TypeError` | only one kwarg passed | Pass BOTH `agent_name=` AND `agent_version=` |
| PowerShell env values with stray `\r\n` | bad URLs or 401s | Strip with `.Trim()` or `.Replace("`r","")\` before use |
| Token-usage columns empty | `gen_ai.usage.*` not on `invoke_agent` span | Document as observed limitation; pull token metrics from the Cog Services account-level metrics instead |
| App Insights Agents pane shows only one row in Models / no rows in Tool Calls | Single agent, no `@tool` functions, single model deployment. The Models tile and Tool Calls table aggregate `chat <model>` and `execute_tool <function>` child spans, so you need multiple model names and multiple tool functions to see variety | Follow Step 5.5: (a) add `@tool` functions to `main.py` (the model needs them in the tools list AND in the instructions, with explicit "report errors" wording); (b) pre-create extra model deployments via `az cognitiveservices account deployment create`; (c) clone the agent project dir per model, hardcode `AZURE_AI_MODEL_DEPLOYMENT_NAME` in each clone's `agent.yaml`, add as additional services in `azure.yaml`, `azd deploy <name>` each one; (d) optionally add a 4th agent pointing at a fake deployment to populate chat-level Gen AI Errors |
| Agents pane "Evaluations" section shows "Already set up? There may be no recent activity." | No eval runs landed inside the pane's time range. The continuous-eval rule is unreliable for this on its own (see Step 7 Known issue) | Fire a one-shot agent-batch eval through Foundry MCP `evaluation_agent_batch_eval_create` (recipe in Step 7). On this deployment, the batch returned `8 total / 5 passed / 3 failed` in \<5 min. Then expand the pane's time range to "Last 4 hours" and reload. Pane rollup takes a further 15-30 min |

```
& .venv\Scripts\python.exe scripts/17-list-connections.py
```

```
Name: chat gpt-4o-mini
Type: AppDependencies   Duration: ~6300ms   Success: True
gen_ai.operation.name = chat
gen_ai.provider.name  = azure.ai.foundry
gen_ai.request.model  = gpt-4o-mini
gen_ai.response.model = gpt-4o-mini-2024-07-18
gen_ai.usage.input_tokens  = 32
gen_ai.usage.output_tokens = 2
gen_ai.agent.id = agent-framework-agent-basic-responses:<version>
gen_ai.input.messages / gen_ai.output.messages / gen_ai.system_instructions  (only with ENABLE_SENSITIVE_DATA=true)
```

```
environment_variables:
  - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
    value: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
  - name: ENABLE_INSTRUMENTATION
    value: "true"
  - name: ENABLE_SENSITIVE_DATA
    value: "true"
```

```
$q = "AppDependencies | where TimeGenerated > ago(15m) | summarize n=count() by Name, Type"
az monitor log-analytics query -w $wsId --analytics-query $q -o table
```

```
$wsId = (az monitor log-analytics workspace show -g $rg -n logs-eyfs7o7lvdq7e --query customerId -o tsv)
$q = "AppRequests | where TimeGenerated > ago(15m) | where Name startswith 'invoke_agent' | summarize n=count(), latest=max(TimeGenerated)"
az monitor log-analytics query -w $wsId --analytics-query $q -o table
```