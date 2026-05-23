#Requires -Version 7.0
<#
.SYNOPSIS
  Seed traffic: iterate prompts files and invoke agent for each.

.PARAMETER MaxPrompts
  Maximum total prompts to send across all corpora. Default: 10.
  Use 0 for no limit (sends all prompts from all files, ~48 total).
#>
param(
  [string]$AgentDir = (Join-Path $PSScriptRoot '..' 'agent'),
  [string]$PromptsDir = (Join-Path $PSScriptRoot '..' 'prompts'),
  [int]$SleepSeconds = 2,
  [string]$ArtifactsDir = (Join-Path $PSScriptRoot '..' 'artifacts'),
  [string]$ServiceName = 'agent-framework-agent-basic-responses',
  [int]$MaxPrompts = 10
)
$ErrorActionPreference = 'Stop'
$AZD = if (Test-Path "$env:LOCALAPPDATA\Programs\azd-local\azd.exe") { "$env:LOCALAPPDATA\Programs\azd-local\azd.exe" } else { 'azd' }
New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $ArtifactsDir "seed-$ts.log"
"# Seed traffic $ts (max=$MaxPrompts)" | Out-File $log
$files = @('clean.txt','ambiguous.txt','safety-bait.txt')
$sent = 0
Push-Location $AgentDir
try {
  foreach ($f in $files) {
    $path = Join-Path $PromptsDir $f
    if (-not (Test-Path $path)) { continue }
    Get-Content $path | ForEach-Object {
      if ($MaxPrompts -gt 0 -and $sent -ge $MaxPrompts) { return }
      $line = $_.Trim()
      if ([string]::IsNullOrWhiteSpace($line)) { return }
      "## [$f] $line" | Out-File $log -Append
      $reply = & $AZD ai agent invoke $ServiceName "$line" --no-prompt 2>&1
      $reply | Out-File $log -Append
      $sent++
      Start-Sleep -Seconds $SleepSeconds
    }
  }
} finally { Pop-Location }
Write-Host "Seed complete: $sent prompts sent. Log: $log"
