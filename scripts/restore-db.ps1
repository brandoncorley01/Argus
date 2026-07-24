$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Force = $false
$Backup = $null
foreach ($a in $args) {
  if ($a -eq "-Force") { $Force = $true }
  elseif (-not $Backup) { $Backup = $a }
}

if (-not (Test-Path ".env")) {
  Write-Error "Missing .env. Copy .env.example to .env before restore."
}
if (-not $Backup) {
  Write-Error "Usage: .\scripts\restore-db.ps1 [-Force] <path-to-backup.sql>"
}
if (-not (Test-Path $Backup)) {
  Write-Error "Backup file not found: $Backup"
}

Write-Host "WARNING: This will DROP and recreate the local Argus database, then restore from:"
Write-Host "  $Backup"
if (-not $Force) {
  Write-Host "Type RESTORE-LOCAL-DB to confirm."
  $confirm = Read-Host "Confirmation"
  if ($confirm -ne "RESTORE-LOCAL-DB") {
    Write-Host "Aborted. No changes made."
    exit 1
  }
} else {
  Write-Host "Proceeding with -Force (non-interactive RC/automation mode)."
}

function Get-DotEnvValue([string]$Key) {
  $line = Get-Content ".env" | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
  if (-not $line) { Write-Error "Missing $Key in .env" }
  return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

$User = Get-DotEnvValue "POSTGRES_USER"
$Db = Get-DotEnvValue "POSTGRES_DB"

docker exec argus-postgres pg_isready -U $User -d postgres | Out-Host
if ($LASTEXITCODE -ne 0) {
  Write-Error "Postgres is not ready. Run .\scripts\infra-up.ps1 first."
}

Write-Host "Recreating database '$Db'..."
docker exec argus-postgres psql -U $User -d postgres -v ON_ERROR_STOP=1 `
  -c "DROP DATABASE IF EXISTS `"$Db`" WITH (FORCE);" | Out-Host
docker exec argus-postgres psql -U $User -d postgres -v ON_ERROR_STOP=1 `
  -c "CREATE DATABASE `"$Db`" OWNER `"$User`";" | Out-Host

Write-Host "Restoring..."
Get-Content -Raw $Backup | docker exec -i argus-postgres psql -U $User -d $Db -v ON_ERROR_STOP=1 | Out-Host
if ($LASTEXITCODE -ne 0) {
  Write-Error "Restore failed."
}

Write-Host "Validating institutional tables..."
& "$PSScriptRoot\validate-db-restore.ps1"
Write-Host "Restore complete."
