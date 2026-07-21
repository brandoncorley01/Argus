$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
  Write-Error "Missing .env. Copy .env.example to .env before backup."
}

function Get-DotEnvValue([string]$Key) {
  $line = Get-Content ".env" | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
  if (-not $line) { Write-Error "Missing $Key in .env" }
  return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

$User = Get-DotEnvValue "POSTGRES_USER"
$Db = Get-DotEnvValue "POSTGRES_DB"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutDir = Join-Path $Root "backups"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutFile = Join-Path $OutDir "argus_postgres_$Stamp.sql"

Write-Host "Backing up database '$Db' via docker exec (password not printed)..."
docker exec argus-postgres pg_isready -U $User -d $Db | Out-Host
if ($LASTEXITCODE -ne 0) {
  Write-Error "Postgres is not ready. Run .\scripts\infra-up.ps1 first."
}

# Stream dump to host file; do not echo PGPASSWORD.
docker exec argus-postgres pg_dump -U $User -d $Db --no-owner --no-acl | Set-Content -Path $OutFile -Encoding utf8
if (-not (Test-Path $OutFile) -or (Get-Item $OutFile).Length -lt 100) {
  Write-Error "Backup failed or file too small: $OutFile"
}

Write-Host "Backup written: $OutFile"
Write-Host "Size bytes: $((Get-Item $OutFile).Length)"
Write-Output $OutFile
