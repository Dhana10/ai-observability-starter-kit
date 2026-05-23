#Requires -Version 7.0
<#
.SYNOPSIS
  Warmup: 3 fast invokes to defeat scale-to-zero before stage time.
#>
param(
  [string]$AgentDir = (Join-Path $PSScriptRoot '..' 'agent'),
  [int]$Count = 3,
  [string]$ServiceName = 'agent-framework-agent-basic-responses'
)
$ErrorActionPreference = 'Stop'
$AZD = if (Test-Path "$env:LOCALAPPDATA\Programs\azd-local\azd.exe") { "$env:LOCALAPPDATA\Programs\azd-local\azd.exe" } else { 'azd' }
Push-Location $AgentDir
try {
  for ($i = 1; $i -le $Count; $i++) {
    Write-Host "Warmup ping $i/$Count"
    & $AZD ai agent invoke $ServiceName "ping" --no-prompt 2>&1 | Out-Null
  }
} finally { Pop-Location }
Write-Host "Agent warm."
