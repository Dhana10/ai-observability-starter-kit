#Requires -Version 7.0
<#
.SYNOPSIS
  Grants the Foundry project's managed identity the Foundry User (a.k.a. Azure AI User)
  role at project scope so continuous evaluation can read traces and invoke evaluators.

.DESCRIPTION
  Reads azd env values from the agent directory; derives the Foundry account name,
  project name, and project MI principalId, then idempotently creates the role
  assignment. Falls back to "Azure AI User" if "Foundry User" is not yet renamed.
#>
param(
  [string]$AgentDir = (Join-Path $PSScriptRoot '..' 'agent'),
  [string]$ResourceGroup = $env:AZURE_RESOURCE_GROUP
)

$ErrorActionPreference = 'Stop'
$AZD = if (Test-Path "$env:LOCALAPPDATA\Programs\azd-local\azd.exe") { "$env:LOCALAPPDATA\Programs\azd-local\azd.exe" } else { 'azd' }

Push-Location $AgentDir
try {
  $values = & $AZD env get-values | Out-String
} finally { Pop-Location }

$envHash = @{}
foreach ($line in ($values -split "`n")) {
  if ($line -match '^([A-Z0-9_]+)=(.*)$') {
    $envHash[$matches[1]] = $matches[2].Trim('"')
  }
}

if (-not $ResourceGroup) { $ResourceGroup = $envHash['AZURE_RESOURCE_GROUP'] }
if (-not $ResourceGroup) { throw 'AZURE_RESOURCE_GROUP not found in env.' }
$sub = $envHash['AZURE_SUBSCRIPTION_ID']

$acct = az cognitiveservices account list -g $ResourceGroup --query "[0].name" -o tsv
if (-not $acct) { throw "No Cognitive Services account in $ResourceGroup." }

$miPid = az cognitiveservices account show -g $ResourceGroup -n $acct --query "identity.principalId" -o tsv
if (-not $miPid) { throw "No managed identity on $acct." }

$project = az resource list -g $ResourceGroup `
  --resource-type 'Microsoft.CognitiveServices/accounts/projects' `
  --query "[0].name" -o tsv
if (-not $project) { throw "No Foundry project found in $ResourceGroup." }
$projectShort = ($project -split '/')[-1]
$projectScope = "/subscriptions/$sub/resourceGroups/$ResourceGroup/providers/Microsoft.CognitiveServices/accounts/$acct/projects/$projectShort"

Write-Host "Project MI principalId: $miPid"
Write-Host "Project scope:           $projectScope"

$assigned = $false
foreach ($role in 'Foundry User', 'Azure AI User') {
  try {
    az role assignment create `
      --assignee-object-id $miPid `
      --assignee-principal-type ServicePrincipal `
      --role $role `
      --scope $projectScope 2>&1 | Out-Host
    if ($LASTEXITCODE -eq 0) { $assigned = $true; Write-Host "Assigned $role."; break }
  } catch {
    Write-Host "Role '$role' failed: $_"
  }
}
if (-not $assigned) { throw 'Failed to assign Foundry User or Azure AI User role.' }

[Environment]::SetEnvironmentVariable('PROJECT_MI_PRINCIPAL_ID', $miPid, 'Process')
& $AZD env set PROJECT_MI_PRINCIPAL_ID $miPid --cwd $AgentDir | Out-Null
Write-Host "PROJECT_MI_PRINCIPAL_ID stored in azd env."
