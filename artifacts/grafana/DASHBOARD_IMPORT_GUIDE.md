# Agent Observability Dashboard Import Guide

The `agent-observability-dashboard.json` dashboard replicates the complete agent observability monitoring experience shown in the demo screenshot. It includes all KPI metrics, time-series charts, and model performance analytics.

## Dashboard Contents

The dashboard includes 13 panels organized across three sections:

### Agent Summary Statistics (Top Row - 8 Stat Tiles)
- **Total Operations**: Count of all `invoke_agent` requests (80 in the demo)
- **Total Input Tokens**: Aggregated input tokens in millions (25.0 Mil)
- **Total Output Tokens**: Aggregated output tokens in thousands (202 k)
- **Avg Response Time**: Average response latency (1.46 mins)
- **LLM Calls**: Count of `chat <model>` dependencies (1.00 k)
- **Chat Sessions**: Distinct `gen_ai.conversation_id` values (69)
- **Tool Calls**: Count of `execute_tool` dependencies (647)
- **Avg TTFT**: Average time-to-first-token in milliseconds (3.32 s)

### Usage Over Time (Middle Row - 2 Charts)
- **Operations Over Time**: Stacked bar chart showing `chat`, `execute_tool`, and `invoke_agent` volume by hour
- **Token Consumption Over Time by Model**: Stacked bar chart showing token spend per model by hour

### Model Performance (Bottom Row - 3 Charts)
- **Model Usage Distribution**: Pie chart of operations by model name
- **Response Duration by Model (Avg / P90)**: Horizontal bar chart comparing average vs P90 latencies
- **Time First Token by Model (P50 / P90)**: Horizontal bar chart comparing P50 vs P90 TTFT

## Import Steps

### Option 1: Import into Embedded Grafana (Recommended for this demo)

1. Open your App Insights resource in Azure Portal
2. Navigate to **Dashboards with Grafana** (Left menu > Monitoring)
3. Click **New** > **Import**
4. Upload or paste the contents of `agent-observability-dashboard.json`
5. Click **Load**
6. Respond to the template variable prompts:
   - **Subscription**: Select your Azure subscription
   - **Resource Group**: Select `rg-aiobs-foundry-*` (your deployment)
   - **Resource**: Select `appi-*` (your Application Insights instance)
7. Click **Import**
8. (Optional) Click **Save As** to tag it with `GrafanaDashboardResourceType=microsoft.insights/components` so it appears in the App Insights Grafana gallery

### Option 2: Import into Azure Managed Grafana

If you have a separate Azure Managed Grafana instance:

1. Navigate to your Grafana instance URL
2. Go to **Dashboards** > **New** > **Import**
3. Upload or paste `agent-observability-dashboard.json`
4. Configure data source to point to your Application Insights
5. Click **Import**

### Option 3: Deploy as Infrastructure (Bicep/ARM)

For automated deployment, wrap the dashboard JSON in a Bicep resource:

```bicep
resource grafanaDashboard 'Microsoft.Dashboard/grafanaDashboards@2024-10-01' = {
  name: 'agent-observability-custom-dashboard'
  location: location
  tags: {
    'GrafanaDashboardResourceType': 'microsoft.insights/components'
  }
  properties: {
    definition: json(loadTextContent('../artifacts/grafana/agent-observability-dashboard.json'))
  }
}
```

## Template Variables

The dashboard uses three template variables that are automatically populated on import:

- `$subscription`: Your Azure subscription ID
- `$resourceGroup`: The resource group containing your App Insights instance
- `$resource`: Your Application Insights resource

These variables make the dashboard portable across environments.

## Data Source Requirements

The dashboard queries run against the **Azure Monitor** data source and execute KQL (Kusto Query Language) against your Application Insights workspace. Ensure:

1. The Azure Monitor data source is configured in Grafana
2. Your App Insights instance has data from at least one completed traffic-seeding run (see `scripts/05-seed-traffic.ps1`)
3. You have `Monitoring Reader` role on the App Insights resource

## KQL Queries Behind Each Panel

All queries follow the OpenTelemetry GenAI semantic conventions:

- **Request-level metrics** filter on `AppRequests | where name contains "invoke_agent"`
- **Model-level metrics** filter on `AppDependencies | where name startswith "chat "`
- **Tool metrics** filter on `AppDependencies | where name startswith "execute_tool"`
- **Tokens** aggregate from `customDimensions.gen_ai_usage_input_tokens` / `gen_ai_usage_output_tokens`
- **TTFT** sourced from `customDimensions.gen_ai_operation_time_to_first_token_ms`

To customize any panel, click **Edit** on the panel to review or modify the underlying KQL query.

## Troubleshooting

### No data appears on the dashboard

- **Check timing**: Telemetry lands 1-2 minutes after traces are emitted. Refresh after 2 minutes.
- **Check time range**: Use the time picker (top right) to extend to "Last 4 hours" or "Last 24 hours".
- **Verify traffic**: Confirm you've run `scripts/05-seed-traffic.ps1` to populate Log Analytics.

### Template variable dropdowns are empty

- Verify the Azure Monitor data source is properly configured and connected to your subscription.
- Ensure your user account has read permissions on the subscription and resource group.
- Try manually selecting values instead of using the dropdowns.

### Queries return "access denied"

- Confirm you have `Monitoring Reader` role on the Application Insights resource (or the parent resource group).
- Verify the App Insights data source credentials in Grafana are correct.

## Next Steps

- Modify panel queries in **Edit** mode to customize for your use case
- Add additional panels for custom metrics
- Set up Grafana alerts on critical thresholds (e.g., error rate, high latency)
- Export the dashboard as Bicep to version control and automate deployment

For more details on Grafana customization in the context of this demo, see `docs/GRAFANA_GUIDE.md`.
