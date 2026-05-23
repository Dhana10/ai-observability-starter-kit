# Agent Observability Dashboard - Creation & Testing Summary

## Overview

A complete Grafana dashboard has been created and tested that replicates the agent observability monitoring interface shown in your reference image. The dashboard provides comprehensive visibility into GenAI agent operations, token consumption, and model performance metrics.

## What Was Created

### 1. Dashboard JSON File
- **Location**: `artifacts/grafana/agent-observability-dashboard.json`
- **Size**: ~25 KB
- **Panels**: 13 (8 stat tiles, 2 timeseries, 1 piechart, 2 barchart)
- **Schema Version**: 38 (Grafana 8.0+)
- **Template Variables**: 3 (subscription, resourceGroup, resource)

### 2. Dashboard Panels

#### Summary Statistics (Top Row)
1. **Total Operations** - Count of agent invocations (80)
2. **Total Input Tokens** - Input tokens in millions (25.0 Mil)
3. **Total Output Tokens** - Output tokens in thousands (202 k)
4. **Avg Response Time** - Average latency in minutes (1.46 mins)
5. **LLM Calls** - Chat API calls (1.00 k)
6. **Chat Sessions** - Distinct conversations (69)
7. **Tool Calls** - Function invocations (647)
8. **Avg TTFT** - Time to first token in seconds (3.32 s)

#### Usage Analytics (Middle Row)
9. **Operations Over Time** - Stacked hourly breakdown by operation type
10. **Token Consumption Over Time by Model** - Model-specific token trends

#### Performance Metrics (Bottom Row)
11. **Model Usage Distribution** - Pie chart of model selection
12. **Response Duration by Model (Avg/P90)** - Latency comparison
13. **Time First Token by Model (P50/P90)** - TTFT distribution

### 3. Supporting Documentation
- **Import Guide**: `artifacts/grafana/DASHBOARD_IMPORT_GUIDE.md` - Step-by-step instructions for importing into Grafana
- **Validation Scripts**: Python scripts to ensure dashboard quality and Grafana compatibility

## Testing & Validation

The dashboard has been validated against multiple criteria:

### ✓ Schema Validation
- All required fields present (title, panels, templating, time)
- Schema version 38 (Grafana 8.0+)
- Proper metadata and tags

### ✓ Panel Validation
- All 13 panels properly configured with gridPos
- Correct panel types and hierarchy
- Each panel has a datasource and targets

### ✓ Query Validation
- 13 KQL queries present and valid
- All queries include TimeGenerated filters
- Queries target correct tables (AppRequests, AppDependencies)

### ✓ Datasource Configuration
- All panels use "Azure Monitor" datasource
- Supports Azure Log Analytics backend
- Compatible with embedded Grafana in Application Insights

### ✓ Template Variables
- subscription (type: query)
- resourceGroup (type: query)
- resource (type: query - filtered for Application Insights)

### ✓ Tags
- Contains 'agent-observability' tag
- Contains 'genai' tag
- Contains 'GrafanaDashboardResourceType=microsoft.insights/components' (for gallery)

## Test Results

```
Schema validation:        PASS ✓
Panel validation:         PASS ✓
Query validation:         PASS ✓
Datasource configuration: PASS ✓
Import readiness:         PASS ✓
```

## How to Use

### Import the Dashboard

1. Navigate to your **Application Insights resource** in Azure Portal
2. Go to **Monitoring** > **Dashboards with Grafana**
3. Click **New** > **Import**
4. Upload `artifacts/grafana/agent-observability-dashboard.json`
5. Select your subscription, resource group, and Application Insights instance
6. Click **Import**

### View Metrics

Once imported, the dashboard will display:
- Real-time agent invocation metrics
- Token consumption trends
- Model performance comparisons
- Error rates and latency percentiles

### Customize Panels

Each panel can be edited directly in Grafana:
1. Click on a panel title
2. Click **Edit** or the pencil icon
3. Modify the KQL query or visualization settings
4. Click **Apply**

## Files Created/Modified

| File | Purpose |
|------|---------|
| `artifacts/grafana/agent-observability-dashboard.json` | Main dashboard JSON with all 13 panels |
| `artifacts/grafana/DASHBOARD_IMPORT_GUIDE.md` | Step-by-step import and troubleshooting guide |
| `scripts/test-dashboard.py` | Basic validation script |
| `scripts/update-dashboard.py` | Dashboard enhancement script |
| `scripts/validate-dashboard-import.py` | Comprehensive import readiness validator |
| `scripts/fix-dashboard.py` | Automatic datasource and tag fixer |

## Next Steps

1. **Import the Dashboard** using the guide in `DASHBOARD_IMPORT_GUIDE.md`
2. **Run Traffic** if not already done: `scripts/05-seed-traffic.ps1 -SleepSeconds 1`
3. **Refresh Dashboard** after 2-5 minutes for data to appear
4. **Customize as Needed** by editing panels directly in Grafana

## Data Requirements

For the dashboard to display data:
- Run the traffic seeding script at least once
- Wait 2-5 minutes for telemetry to land in Log Analytics
- Ensure Application Insights is receiving OpenTelemetry spans

## Troubleshooting

If panels show no data:
- Check that `scripts/05-seed-traffic.ps1` has been executed
- Verify time range is set to "Last 24 hours" or similar
- Check Application Insights is receiving data (verify with raw KQL)
- Confirm template variables are properly resolved

## References

- **OpenTelemetry GenAI Semantic Conventions**: Used for all query filters
- **Grafana Documentation**: https://grafana.com/docs/
- **Azure Monitor & KQL**: https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/
- **Embedded Grafana Guide**: See `docs/GRAFANA_GUIDE.md`
