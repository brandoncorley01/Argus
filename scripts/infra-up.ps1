$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
  Write-Error "Missing .env. Copy .env.example to .env and set POSTGRES_PASSWORD before starting."
}

Write-Host "Starting Argus infrastructure (postgres, redis)..."
docker compose up -d
docker compose ps
