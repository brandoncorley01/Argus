$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

docker compose ps
Write-Host ""
Write-Host "PostgreSQL readiness:"
docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
Write-Host "Redis PING:"
docker compose exec -T redis redis-cli ping
