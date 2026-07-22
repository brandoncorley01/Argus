$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

Write-Host "=== Argus PAPER start ==="
Write-Host "Provider expectation: internal_paper (default)"
Write-Host "Live execution: DISABLED"
if (-not (Test-Path ".env")) {
  Write-Host "No .env found. Copy .env.paper.example to .env (or .env.example) before start."
  Write-Error "Missing .env"
}

& "$Root\scripts\infra-up.ps1"
& "$Root\scripts\migrate-up.ps1"

Write-Host ""
Write-Host "Infra + migrations complete."
Write-Host "Start API (separate terminal):"
Write-Host "  cd apps\api; python -m uv run uvicorn app.main:app --host 127.0.0.1 --port 8000"
Write-Host "Start EOC (separate terminal):"
Write-Host "  pnpm eoc:dev"
Write-Host "Optional worker:"
Write-Host "  docker compose --profile workers up -d health_supervisor"
Write-Host "Status: .\scripts\operations\status-paper.ps1"
