$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Stopping Argus infrastructure containers..."
docker compose stop
docker compose ps
