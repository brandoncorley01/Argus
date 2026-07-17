$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "WARNING: This will permanently delete local Argus Postgres and Redis data volumes."
Write-Host "Type DELETE-LOCAL-DATA to confirm."
$confirm = Read-Host "Confirmation"
if ($confirm -ne "DELETE-LOCAL-DATA") {
  Write-Host "Aborted. No volumes deleted."
  exit 1
}

docker compose down -v
Write-Host "Containers removed and named volumes deleted."
