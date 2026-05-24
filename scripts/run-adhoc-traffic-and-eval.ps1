#Requires -Version 7.0
<#
.SYNOPSIS
  Ad-hoc refresh of telemetry + evaluations against an already-deployed
  aiobs-foundry environment. Generates a fresh batch of traces, runs the
  agent batch eval over the new traces, and refreshes the telemetry export.

  Use this after the full run-e2e.ps1 has already provisioned and deployed
  the environment, when you want a new set of traces + eval results for the
  current time window (e.g. for a fresh dashboard screenshot or a re-eval
  after a model/prompt change).

  Phases run:
    6  - Warmup (3 pings) + seed prompts
    7  - Fan-out: 12 tool prompts x 3 working agents + 8 broken-model
    9  - Batch eval (8 agent evaluators) over App Insights traces (2h lookback)
   10  - Red-team scan (only when -RunRedTeam is set; ~8 min)
   12  - Export telemetry to artifacts/telemetry.json
   13  - Smoke invoke + verify batch eval artifact

  Phases skipped (already done by run-e2e.ps1):
    1  - azd provision
    2  - Foundry User role assignment
    3  - basic-responses agent deploy
    4  - additional model deployments
    5  - sister agent deploys
    8  - custom evaluator registration
   11  - alerts and action group

.PARAMETER EnvName
  azd env name to refresh. Defaults to the currently selected azd env.

.PARAMETER MaxPrompts
  Number of seed prompts in Phase 6. Default: 10. Use 0 for the full ~48.

.PARAMETER RunRedTeam
  Include the red-team scan (Phase 10). Adds ~8 min. Off by default.

.PARAMETER LogFile
  Path to capture all output. Default: scripts/e2e-adhoc-run.log. Every line
  the script and run-e2e.ps1 produce is streamed to both the console and this
  file, so you can monitor live AND review the full transcript afterwards.

.EXAMPLE
  pwsh -NoProfile -File scripts\run-adhoc-traffic-and-eval.ps1 -EnvName aiobs3-foundry

.EXAMPLE
  pwsh -NoProfile -File scripts\run-adhoc-traffic-and-eval.ps1 -EnvName aiobs3-foundry -RunRedTeam

.EXAMPLE
  azd env select aiobs3-foundry
  pwsh -NoProfile -File scripts\run-adhoc-traffic-and-eval.ps1 -MaxPrompts 20

.EXAMPLE
  # Tail the log from another terminal to monitor progress:
  Get-Content -Wait scripts\e2e-adhoc-run.log
#>
[CmdletBinding()]
param(
    [string]$EnvName,
    [int]$MaxPrompts = 10,
    [switch]$RunRedTeam,
    [string]$LogFile
)

$ErrorActionPreference = 'Stop'

$ScriptsDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $ScriptsDir '..')).Path
$AgentDir = Join-Path $RepoRoot 'agent'
$E2E = Join-Path $ScriptsDir 'run-e2e.ps1'

if (-not (Test-Path $E2E)) {
    throw "run-e2e.ps1 not found at $E2E"
}

# Default log location: scripts/e2e-adhoc-run.log (matches e2e-run.log naming).
if (-not $LogFile) {
    $LogFile = Join-Path $ScriptsDir 'e2e-adhoc-run.log'
}

$AZD = if (Test-Path "$env:LOCALAPPDATA\Programs\azd-local\azd.exe") {
    "$env:LOCALAPPDATA\Programs\azd-local\azd.exe"
} else { 'azd' }

# Resolve EnvName: explicit -> currently selected azd env.
if (-not $EnvName) {
    Push-Location $AgentDir
    try {
        $envs = & $AZD env list --output json 2>$null | ConvertFrom-Json
        $current = $envs | Where-Object { $_.IsDefault -eq $true } | Select-Object -First 1
        if (-not $current) {
            throw "No -EnvName provided and no default azd env selected. Run 'azd env select <name>' or pass -EnvName."
        }
        $EnvName = $current.Name
    } finally { Pop-Location }
}

# Phases run-e2e.ps1 should skip on this ad-hoc pass.
# Always skip 1-5 (infra and deploys), 8 (evaluator registration), 11 (alerts).
# Optionally skip 10 (red team) when -RunRedTeam is not set.
$skip = @(1,2,3,4,5,8,11)
if (-not $RunRedTeam) { $skip += 10 }
$SkipPhases = ($skip | Sort-Object) -join ','

# Reset log file with a header describing this run.
$cmdLine = "pwsh -NoProfile -File scripts\run-adhoc-traffic-and-eval.ps1 -EnvName $EnvName -MaxPrompts $MaxPrompts" + $(if ($RunRedTeam) { ' -RunRedTeam' } else { '' })
$header = @(
    "# Ad-hoc traffic + eval refresh",
    "",
    "Command used to kick off this run:",
    "",
    '```powershell',
    $cmdLine,
    '```',
    "",
    "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
    "",
    "---",
    ""
)
$header | Out-File -FilePath $LogFile -Encoding utf8

Write-Host ''
Write-Host ('=' * 70) -ForegroundColor Cyan
Write-Host "AD-HOC TRAFFIC + EVAL REFRESH" -ForegroundColor Cyan
Write-Host ('=' * 70) -ForegroundColor Cyan
Write-Host "  EnvName:      $EnvName"
Write-Host "  MaxPrompts:   $MaxPrompts"
Write-Host "  RedTeam:      $($RunRedTeam.IsPresent)"
Write-Host "  SkipPhases:   $SkipPhases"
Write-Host "  Log:          $LogFile"
Write-Host ''

# Stream child output line-by-line so the user sees live progress AND the log
# captures everything (no buffering, no Tee-Object spinner-blocking issues).
& pwsh -NoProfile -File $E2E `
    -EnvName $EnvName `
    -SkipPhases $SkipPhases `
    -MaxPrompts $MaxPrompts 2>&1 | ForEach-Object {
        $line = $_ | Out-String -Stream
        $line | Out-File -Append -FilePath $LogFile -Encoding utf8
        Write-Host $line
    }

$childExit = $LASTEXITCODE
"" | Out-File -Append -FilePath $LogFile -Encoding utf8
"Finished: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz') (exit $childExit)" | Out-File -Append -FilePath $LogFile -Encoding utf8

Write-Host ''
Write-Host "Log saved: $LogFile" -ForegroundColor Green

if ($childExit -ne 0) {
    throw "run-e2e.ps1 exited with code $childExit."
}
