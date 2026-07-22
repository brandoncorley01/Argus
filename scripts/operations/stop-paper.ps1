$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

Write-Host "=== Argus PAPER stop ==="
Write-Host "Stopping Compose services (volumes preserved by default)."
Write-Host "Live execution remains DISABLED. Provider remains internal_paper when next started."
& "$Root\scripts\infra-stop.ps1"
Write-Host "Stop local uvicorn / pnpm processes manually if still running (Ctrl+C)."
