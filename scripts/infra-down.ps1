$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Removing Argus containers/networks (named volumes preserved)..."
docker compose down
Write-Host "Named volumes argus_postgres_data and argus_redis_data were not deleted."
