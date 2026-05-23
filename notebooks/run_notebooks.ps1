$repoRoot = Split-Path $PSScriptRoot -Parent
$venv = Join-Path $repoRoot '.venv\Scripts'
$nbDir = $PSScriptRoot
Set-Location $nbDir
$results = @{}
$notebooks = @(
    @{name="01-continuous-eval-setup"; timeout=600},
    @{name="02-custom-evaluator-register"; timeout=120},
    @{name="03-red-team-taxonomy"; timeout=120},
    @{name="04-red-team-run"; timeout=600}
)
foreach ($nb in $notebooks) {
    $n = $nb.name
    $t = $nb.timeout
    Write-Host "=== Running $n.ipynb ==="
    & "$venv\jupyter-nbconvert.exe" --to notebook --execute --ExecutePreprocessor.timeout=$t "$n.ipynb" --output "$n-output.ipynb" 2>&1 | Out-String | Write-Host
    $results[$n] = $LASTEXITCODE
    Write-Host "Exit code: $($results[$n])"
}
Write-Host "`n=== SUMMARY ==="
foreach ($nb in $notebooks) { Write-Host "$($nb.name): Exit=$($results[$nb.name])" }
Remove-Item "$nbDir\*-output.ipynb" -ErrorAction SilentlyContinue
Write-Host "Cleaned up output notebooks."
