$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

Write-Host "=== Argus paper backup ==="
Write-Host "Provider context: internal_paper operating data in Postgres"
& "$Root\scripts\backup-db.ps1"
& "$Root\scripts\validate-db-restore.ps1"
Write-Host "Backup + table validation complete."
