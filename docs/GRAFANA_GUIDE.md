# Grafana guide: customize the Agents pane in Application Insights

This guide implements the "Customize monitoring views with Grafana" step from the [official Agents view documentation](https://learn.microsoft.com/en-us/azure/azure-monitor/app/agents-view#customize-monitoring-views-with-grafana) against the AI observability demo deployed in this repo.

It targets the **embedded** "Dashboards with Grafana" experience built into Application Insights (no separate Azure Managed Grafana instance, no extra cost beyond Azure Monitor query charges).

Companion artifact: [artifacts/grafana/agent-observability-custom-dashboard.json](../artifacts/grafana/agent-observability-custom-dashboard.json) (importable Grafana dashboard with 5 custom panels matching the queries in section 5).

## Contents

1. [When to use embedded vs Managed Grafana](#1-when-to-use-embedded-vs-managed-grafana)
2. [Open the Grafana experience](#2-open-the-grafana-experience)
3. [Walk the three prebuilt Gen AI dashboards](#3-walk-the-three-prebuilt-gen-ai-dashboards)
4. [Save As and tag so the dashboard shows up in the App Insights gallery](#4-save-as-and-tag-so-the-dashboard-shows-up-in-the-app-insights-gallery)
5. [Custom KQL panels (drop-in, schema-matched)](#5-custom-kql-panels-drop-in-schema-matched)
6. [Import the companion dashboard JSON](#6-import-the-companion-dashboard-json)
7. [RBAC: viewers, editors, data access](#7-rbac-viewers-editors-data-access)
8. [Export ARM or JSON for automation](#8-export-arm-or-json-for-automation)
9. [Pitfalls](#9-pitfalls)
10. [References](#10-references)

## 1. When to use embedded vs Managed Grafana

| Capability | Embedded "Dashboards with Grafana" (this guide) | Azure Managed Grafana (separate resource) |
|---|---|---|
| Cost | No additional cost; pay only for Azure Monitor queries | Standard SKU about $11 / instance / month plus query costs |
| Where you find it | Application Insights blade > Dashboards with Grafana | `Microsoft.Dashboard/grafana` resource, own URL |
| Data sources | Azure Monitor, Azure Monitor managed Prometheus, Azure Data Explorer | All of the above plus 100+ community plugins |
| Sharing | Link via Azure portal (RBAC scoped) | Public/private endpoint, Entra SSO, anonymous viewers |
| Grafana alerting | Not surfaced | Full Grafana unified alerting |
| Pick this when | You only need Azure data, the audience already has portal access, and you want zero new resources | You need plugins, non-Azure data, sharable public URLs, or Grafana alerting |

For this demo, the embedded experience is enough. The same dashboard JSON in `artifacts/grafana/agent-observability-custom-dashboard.json` imports cleanly into a Managed Grafana instance later if you outgrow the portal.

## 2. Open the Grafana experience

Two entry points, both land in the same Grafana UI scoped to your App Insights resource.

### From the App Insights resource

1. Azure portal > resource group `rg-aiobs-foundry-20260520` > `appi-eyfs7o7lvdq7e`.
2. Left menu > Monitoring > **Dashboards with Grafana**.
3. The gallery auto-filters to Application Insights dashboards (tag `GrafanaDashboardResourceType=microsoft.insights/components`).

### From the Agents pane (one-click jump from the demo)

1. App Insights > **Agents (Preview)** in the left menu.
2. Pick the agent (for this demo: `agent-framework-agent-basic-responses`).
3. In the top action bar, select **Explore in Grafana**. This opens the same Grafana experience pre-scoped to your App Insights resource.

The "Explore in Grafana" button is the link the official Learn page is pointing at when it says "for more advanced customization and visualization needs".

## 3. Walk the three prebuilt Gen AI dashboards

Azure ships three Azure-managed dashboards aimed at Gen AI workloads. They appear at the top of the gallery (look for the `Azure-managed` tag). For each one below, the "What lights up in this demo" column tells you which panels will populate immediately from data this repo emits, and which will stay empty until you broaden your test traffic.

| Dashboard | Built for | What lights up in this demo |
|---|---|---|
| **Agent Framework** | Generic per-agent KPIs: run count, latency, token spend, tool usage | All tiles populate. Per-tool tiles show `list_customer_orders`, `find_suppliers_for_request`, `lookup_supplier` plus warmup tools. Model tiles show `gpt-4o-mini` and the intentionally broken `nonexistent-deployment-model` from `agent-framework-agent-broken-model` |
| **Agent Framework workflow** | Multi-step workflows and orchestration patterns | Partially populates. The orchestrator agent (`agent-framework-agent-orchestrator`) and child-agent dependencies show; classic LangGraph-style "step" tiles stay empty (we don't emit workflow step spans) |
| **Foundry** | Foundry-hosted-agent specifics: project, deployment, version, agent identity | Lights up because the basic-responses agent is Foundry-hosted (`agent-framework-agent-basic-responses:5`). Project filter resolves to `ai-project-aiobs-foundry-20260520` |

Click any dashboard, then change the time range to "Last 4 hours" to clear past the 15-30 min pane rollup lag.

### Tile to KQL map (so you can recognize what each panel is querying)

The prebuilt panels run against the same `requests` / `dependencies` / `traces` tables we already use in `scripts/13-telemetry-kql.py`. The mapping in the demo:

| Prebuilt tile | Underlying table | Filter |
|---|---|---|
| Agent runs | `requests` | `name has "invoke_agent"` |
| Model usage | `requests` | `customDimensions.gen_ai.request.model` grouped |
| Token in/out | `requests` | `customDimensions.gen_ai.usage.input_tokens` / `.output_tokens` |
| Tool calls | `dependencies` | `name startswith "execute_tool"` or `name startswith "gen_ai"` |
| Errors | `requests` | `success == false` |
| Latency p95 | `requests` or `dependencies` | `percentile(duration, 95)` |

Use this map when you click "Edit panel" on a prebuilt tile and want to understand the auto-generated query before customizing.

## 4. Save As and tag so the dashboard shows up in the App Insights gallery

A prebuilt dashboard is read-only until you save a copy.

1. Open any prebuilt dashboard, e.g. **Agent Framework**.
2. Top right > **Save As**.
3. Fill in:
   - Title: `AI Agent Observability (demo)`
   - Subscription: `463a82d4-1896-4332-aeeb-618ee5a5aa93`
   - Resource group: `rg-aiobs-foundry-20260520`
   - Region: `East US 2`
4. Click **Save**.

Saved dashboards land as a separate Azure resource (`Microsoft.Dashboard/grafanaDashboards`). They are NOT visible in the App Insights Grafana gallery yet, because the gallery filters on a specific tag.

### Add the gallery tag

```bash
# Replace {dashboard-name} with the resource name you saved (usually a GUID)
az tag create \
  --resource-id "/subscriptions/463a82d4-1896-4332-aeeb-618ee5a5aa93/resourceGroups/rg-aiobs-foundry-20260520/providers/Microsoft.Dashboard/grafanaDashboards/{dashboard-name}" \
  --tags GrafanaDashboardResourceType=microsoft.insights/components
```

Or via the portal: open the dashboard resource > Tags > add `GrafanaDashboardResourceType` = `microsoft.insights/components` > Save. Refresh the App Insights gallery. The saved dashboard now appears under "Saved dashboards".

Dashboards you save while *inside* the App Insights "Dashboards with Grafana" gallery get this tag automatically. You only need to add it manually if you saved from a different entry point or imported via JSON.

## 5. Custom KQL panels (drop-in, schema-matched)

These panels target the schema this repo actually emits (verified by `scripts/13-telemetry-kql.py`). Paste each query into a new panel: **Edit dashboard > Add visualization > pick "Azure Monitor" data source > Service: "Logs" > Resource: your App Insights > paste KQL**.

### 5.1 Token usage trend by model

Stacked line, one series per model.

```kusto
requests
| where name has "invoke_agent"
| extend cd = parse_json(customDimensions)
| extend model   = tostring(cd["gen_ai.request.model"])
| extend in_tok  = toint(cd["gen_ai.usage.input_tokens"])
| extend out_tok = toint(cd["gen_ai.usage.output_tokens"])
| where isnotnull(in_tok) or isnotnull(out_tok)
| summarize input_tokens = sum(in_tok), output_tokens = sum(out_tok)
  by bin(timestamp, 5m), model
| order by timestamp asc
```

Expected output on this deployment: `gpt-4o-mini` dominates; `nonexistent-deployment-model` shows up with input tokens only (no completion).

### 5.2 Per-tool p95 latency

Bar chart, x = tool, y = ms.

```kusto
dependencies
| where name startswith "execute_tool" or name startswith "gen_ai"
| extend cd   = parse_json(customDimensions)
| extend tool = coalesce(tostring(cd["gen_ai.tool.name"]), name)
| summarize p95_ms = round(percentile(duration, 95), 1) by tool
| order by p95_ms desc
```

Expected on this deployment: `list_customer_orders`, `find_suppliers_for_request`, `lookup_supplier`, plus warmup-only tools.

### 5.3 Gen AI error rate (stat panel)

```kusto
requests
| where name has "invoke_agent"
| extend success_b = tobool(success)
| summarize total = count(), failed = countif(success_b == false)
| extend error_rate = round(100.0 * failed / total, 2)
| project error_rate
```

Suggested thresholds: green < 5, yellow 5-20, red > 20. The broken-model agent intentionally pushes this above 0.

### 5.4 Agent run rate, stacked by agent and outcome

```kusto
requests
| where name has "invoke_agent"
| extend cd    = parse_json(customDimensions)
| extend agent = coalesce(tostring(cd["gen_ai.agent.name"]), "unknown-agent")
| extend ok    = iff(tobool(success) == true, "success", "error")
| summarize n = count() by bin(timestamp, 5m), agent, ok
| order by timestamp asc
```

Stack normal. One series per agent + outcome.

### 5.5 Per-session conversation count (top 50)

Table panel, surfaces hot sessions.

```kusto
requests
| where name has "invoke_agent"
| extend cd      = parse_json(customDimensions)
| extend session = tostring(cd["microsoft.session.id"])
| extend conv    = tostring(cd["gen_ai.conversation.id"])
| extend agent   = coalesce(tostring(cd["gen_ai.agent.name"]), "unknown-agent")
| where isnotempty(session)
| summarize turns = count(), conversations = dcount(conv), last_seen = max(timestamp) by session, agent
| order by turns desc
| take 50
```

Apply a gauge cell on `turns` with max=20 to spot session sprawl.

## 6. Import the companion dashboard JSON

The five panels above are already wired up in [artifacts/grafana/agent-observability-custom-dashboard.json](../artifacts/grafana/agent-observability-custom-dashboard.json).

1. App Insights > Dashboards with Grafana > **New** > **Import**.
2. Upload `agent-observability-custom-dashboard.json` (or paste its contents).
3. Click **Load**. You will be prompted for two constant variables:
   - `subscription`: `463a82d4-1896-4332-aeeb-618ee5a5aa93`
   - `appi_resource`: `/subscriptions/463a82d4-1896-4332-aeeb-618ee5a5aa93/resourceGroups/rg-aiobs-foundry-20260520/providers/Microsoft.Insights/components/appi-eyfs7o7lvdq7e`
4. Pick subscription, resource group `rg-aiobs-foundry-20260520`, region East US 2, click **Import**.
5. Tag the saved dashboard with `GrafanaDashboardResourceType=microsoft.insights/components` (see [section 4](#4-save-as-and-tag-so-the-dashboard-shows-up-in-the-app-insights-gallery)).

The dashboard uses templated variables so the JSON stays portable. Reuse the same file for additional environments by re-importing and re-pointing the two constants.

## 7. RBAC: viewers, editors, data access

The Grafana resource itself and the data behind it are governed independently.

| Role | Scope | Who needs it |
|---|---|---|
| `Reader` on the dashboard resource | Resource or RG | Anyone who needs to open the saved dashboard URL |
| `Contributor` on the dashboard resource | Resource or RG | Anyone editing panels |
| `Monitoring Reader` | The App Insights resource (or RG) | Required for the Azure Monitor data source to return rows |
| `Microsoft.Dashboard/dashboard/read` and `/write` | Fine-grained alternative to Reader/Contributor | When you do not want to grant full Reader |

Assign at the RG scope to keep it simple in this demo:

```bash
RG_ID="/subscriptions/463a82d4-1896-4332-aeeb-618ee5a5aa93/resourceGroups/rg-aiobs-foundry-20260520"
USER="alice@contoso.com"

az role assignment create --assignee $USER --role "Reader"            --scope $RG_ID
az role assignment create --assignee $USER --role "Monitoring Reader" --scope $RG_ID
```

For non-Microsoft-tenant viewers, use Azure Managed Grafana with Entra B2B or a service-principal-bound data source; the embedded experience requires Azure portal access.

## 8. Export ARM or JSON for automation

Saved dashboards are first-class Azure resources, so both ARM and JSON exports are supported.

```bash
# JSON (Grafana-portable, re-importable anywhere)
# In the dashboard UI: Export > JSON

# ARM template (Azure-portable, deployable via Bicep/ARM)
# In the dashboard UI: Export > Export as ARM template

# Or pull existing dashboard JSON directly via REST:
az resource show \
  --ids "/subscriptions/.../providers/Microsoft.Dashboard/grafanaDashboards/{name}" \
  --query properties.definition \
  -o json > my-dashboard.json
```

To deploy the companion dashboard as IaC, wrap [artifacts/grafana/agent-observability-custom-dashboard.json](../artifacts/grafana/agent-observability-custom-dashboard.json) in a `Microsoft.Dashboard/grafanaDashboards@2024-10-01` resource and set the `GrafanaDashboardResourceType` tag in the resource definition. The demo does not commit a Bicep wrapper today; add one to `agent/infra/` if you want one-click redeploy.

## 9. Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Saved dashboard not visible in the App Insights gallery | Missing tag | Add tag `GrafanaDashboardResourceType=microsoft.insights/components` to the dashboard resource, refresh the gallery |
| Imported community dashboard says "no data" on every panel | Different data source UID, or a Log Analytics resource the user has no access to | Edit each panel, set the data source variable, and confirm `Monitoring Reader` on the target Application Insights resource |
| Prebuilt "Agent Framework" tiles are empty for the broken-model agent | Errored runs still emit `requests` rows but with `success=false`; the prebuilt tiles default to a success-only filter | Drop into Edit panel and remove the `success == true` clause, or use the panels in section 5 which already split by outcome |
| `Save As` button is greyed out | Missing `Microsoft.Dashboard/dashboard/write` on the target RG | Grant Contributor at the RG scope |
| KQL preview shows results but the panel is empty | Panel "Format as" set to `time_series` for a query that returns no time column | Switch to "Table" or add `bin(timestamp, $__interval)` to the query |
| Token / latency tiles flat-line at 0 | Agent deployed without `ENABLE_INSTRUMENTATION=true` | Confirm in `agent/agent.yaml`, re-run `azd deploy`, wait 15-30 min for the rollup |

## 10. References

- [Customize monitoring views with Grafana (Agents view)](https://learn.microsoft.com/en-us/azure/azure-monitor/app/agents-view#customize-monitoring-views-with-grafana)
- [Dashboards with Grafana in Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/grafana-dashboards)
- [Use Azure Monitor dashboards with Grafana](https://learn.microsoft.com/en-us/azure/azure-monitor/visualize/visualize-use-grafana-dashboards)
- [Azure Managed Grafana overview](https://learn.microsoft.com/en-us/azure/managed-grafana/overview) (only needed if you go beyond the embedded experience)
- Companion artifact in this repo: [artifacts/grafana/agent-observability-custom-dashboard.json](../artifacts/grafana/agent-observability-custom-dashboard.json)
- Sibling docs: [RUNBOOK.md](./RUNBOOK.md), [MANUAL_GUIDE.md](./MANUAL_GUIDE.md)
