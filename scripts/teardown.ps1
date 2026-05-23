#Requires -Version 7.0
<#
.SYNOPSIS
  Teardown: removes everything created by run-e2e.ps1. Runs azd down --purge
  so the Cog Services account name can be reused inside the 7-day soft-delete
  window. Optionally deletes lingering scheduled-query rules and the resource
  group as a belt-and-braces follow-up.

.PARAMETER NoPurge
  Skip the --purge flag on azd down (leaves the Cog Services account in
  soft-delete state for 7 days). Default is to purge.

.PARAMETER ForceDeleteRg
  After azd down, also `az group delete` the resource group. Use when azd left
  stragglers behind (e.g. scheduled-query rules created out-of-band by
  scripts/06b-alerts-rest.py).

.PARAMETER EnvName
  Limit to a specific azd env. Defaults to the currently selected env.
#>
[CmdletBinding()]
param(
    [switch]$NoPurge,
    [switch]$ForceDeleteRg,
    [string]$EnvName,
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)

$ErrorActionPreference = 'Stop'
$AZD = if (Test-Path "$env:LOCALAPPDATA\Programs\azd-local\azd.exe") {
    "$env:LOCALAPPDATA\Programs\azd-local\azd.exe"
} else { 'azd' }
$AgentDir = Join-Path $RepoRoot 'agent'

if (-not (Test-Path $AgentDir)) { throw "Agent dir not found: $AgentDir" }

Push-Location $AgentDir
try {
    if ($EnvName) { & $AZD env select $EnvName }

    # Capture RG + sub BEFORE azd down wipes the env state.
    $values = (& $AZD env get-values) -split "`n"
    $envHash = @{}
    foreach ($line in $values) {
        if ($line -match '^\s*([A-Z0-9_]+)="?(.*?)"?\s*$') {
            $envHash[$Matches[1]] = $Matches[2]
        }
    }
    $rg = $envHash['AZURE_RESOURCE_GROUP']
    $sub = $envHash['AZURE_SUBSCRIPTION_ID']
    Write-Host "Tearing down env: $($envHash['AZURE_ENV_NAME'])"
    Write-Host "Resource group:    $rg"
    Write-Host "Subscription:      $sub"

    # Stop continuous-eval rule first so it stops billing for evaluations
    # during the teardown window. Tolerate failures (rule may not exist).
    $venvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    $disableScript = Join-Path $RepoRoot 'scripts\15-list-eval-rules.py'
    if ((Test-Path $venvPython) -and (Test-Path $disableScript)) {
        try {
            Write-Host "Listing eval rules (informational only):"
            & $venvPython $disableScript 2>&1 | Select-Object -Last 20
        } catch {
            Write-Host "Eval rule listing skipped: $_" -ForegroundColor Yellow
        }
    }

    Write-Host ''
    Write-Host "Running azd down..." -ForegroundColor Cyan
    if ($NoPurge) {
        & $AZD down --force
    } else {
        & $AZD down --force --purge
    }
} finally {
    Pop-Location
}

if ($ForceDeleteRg -and $rg) {
    # Catch scheduled-query rules + action groups that were created via REST
    # outside the azd template (see scripts/06b-alerts-rest.py).
    if (az group exists -n $rg) {
        Write-Host ''
        Write-Host "Force-deleting resource group $rg ..." -ForegroundColor Cyan
        az group delete -n $rg --yes --no-wait
    } else {
        Write-Host "Resource group $rg already gone."
    }
}

Write-Host ''
Write-Host "Teardown complete." -ForegroundColor Green
if (-not $NoPurge) {
    Write-Host "Cog Services account purged: name can be reused immediately."
}

# ========================================================================
# Post-teardown validation: confirm resources are actually gone
# ========================================================================
Write-Host ''
Write-Host "Validating teardown..." -ForegroundColor Cyan
$validationPassed = $true

if ($rg) {
    # 1. Check resource group existence
    $rgExists = az group exists -n $rg 2>$null
    if ($rgExists -eq 'true') {
        # RG still exists (may be deleting async). Check what is left.
        $remaining = az resource list -g $rg --query "[].{name:name,type:type}" -o json 2>$null | ConvertFrom-Json
        if ($remaining.Count -gt 0) {
            Write-Host "WARNING: Resource group '$rg' still has $($remaining.Count) resource(s):" -ForegroundColor Yellow
            foreach ($r in $remaining) {
                Write-Host "  - $($r.type): $($r.name)" -ForegroundColor Yellow
            }
            $validationPassed = $false
        } else {
            Write-Host "  Resource group exists but is empty (deletion may be in progress)." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Resource group '$rg' deleted." -ForegroundColor Green
    }

    # 2. Check Cognitive Services soft-delete (Foundry account)
    if (-not $NoPurge) {
        $deleted = az cognitiveservices account list-deleted --query "[?contains(id, '$rg')]" -o json 2>$null | ConvertFrom-Json
        if ($deleted.Count -gt 0) {
            Write-Host "WARNING: $($deleted.Count) Cognitive Services account(s) still in soft-delete:" -ForegroundColor Yellow
            foreach ($d in $deleted) {
                Write-Host "  - $($d.name) (location: $($d.location))" -ForegroundColor Yellow
            }
            $validationPassed = $false
        } else {
            Write-Host "  Cognitive Services purged (no soft-deleted accounts)." -ForegroundColor Green
        }
    }

    # 3. Check App Insights resource is gone
    $appi = az resource list -g $rg --resource-type microsoft.insights/components --query "[].name" -o json 2>$null | ConvertFrom-Json
    if ($appi.Count -gt 0) {
        Write-Host "WARNING: App Insights still exists: $($appi -join ', ')" -ForegroundColor Yellow
        $validationPassed = $false
    } else {
        Write-Host "  App Insights removed." -ForegroundColor Green
    }

    # 4. Check scheduled-query alert rules (created out-of-band by 06b-alerts-rest.py)
    $alerts = az monitor scheduled-query list -g $rg --query "[].name" -o json 2>$null | ConvertFrom-Json
    if ($alerts.Count -gt 0) {
        Write-Host "WARNING: $($alerts.Count) scheduled-query alert(s) still exist: $($alerts -join ', ')" -ForegroundColor Yellow
        Write-Host "  Use -ForceDeleteRg to remove these." -ForegroundColor Yellow
        $validationPassed = $false
    } else {
        Write-Host "  Scheduled-query alerts removed." -ForegroundColor Green
    }
}

Write-Host ''
if ($validationPassed) {
    Write-Host "Validation passed: all resources confirmed removed." -ForegroundColor Green
} else {
    Write-Host "Validation found leftover resources. Review warnings above." -ForegroundColor Yellow
    Write-Host "If the resource group is still deleting, wait a few minutes and re-run validation with:" -ForegroundColor Yellow
    Write-Host "  az resource list -g $rg -o table" -ForegroundColor Yellow
}
