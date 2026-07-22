$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

Write-Host "=== Generate daily paper trading report ==="
Write-Host "Requires API running and Founder/Operator session."
Write-Host "Use EOC System Health (when Phase 15 is merged) or:"
Write-Host '  POST /api/v1/operations/daily-reports/generate  (Phase 15)'
Write-Host "Until Phase 15 is verified/merged, use portfolio reports:"
Write-Host '  POST /api/v1/paper/portfolios/{id}/reports'
Write-Host "Live execution remains DISABLED."
exit 0
