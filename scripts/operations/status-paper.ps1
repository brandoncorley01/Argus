$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

Write-Host "=== Argus PAPER status ==="
Write-Host "Expected provider: internal_paper"
Write-Host "Live execution: DISABLED / not certified"
& "$Root\scripts\infra-status.ps1"

try {
  $health = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 3
  Write-Host "API /health: $($health.StatusCode)"
} catch {
  Write-Host "API /health: unavailable (start uvicorn if needed)"
}
try {
  $ready = Invoke-WebRequest -Uri "http://127.0.0.1:8000/ready" -UseBasicParsing -TimeoutSec 3
  Write-Host "API /ready: $($ready.StatusCode)"
} catch {
  Write-Host "API /ready: unavailable"
}
