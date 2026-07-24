$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Get-DotEnvValue([string]$Key) {
  $line = Get-Content ".env" | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
  if (-not $line) { Write-Error "Missing $Key in .env" }
  return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

$User = Get-DotEnvValue "POSTGRES_USER"
$Db = Get-DotEnvValue "POSTGRES_DB"

$Tables = @(
  "audit_events",
  "users",
  "paper_portfolios",
  "paper_orders",
  "paper_fills",
  "paper_positions",
  "execution_providers"
)

Write-Host "Restore validation against database '$Db' (counts only; no secrets):"
$failed = $false
foreach ($t in $Tables) {
  $sql = "SELECT COUNT(*) FROM ${t};"
  $out = & docker exec argus-postgres psql -U $User -d $Db -t -A -c $sql 2>&1
  if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL  table missing or query error: $t :: $out"
    $failed = $true
    continue
  }
  $count = ("$out").Trim()
  Write-Host ("OK    {0,-22} rows={1}" -f $t, $count)
}

$provSql = "SELECT provider_key FROM execution_providers WHERE is_default IS TRUE LIMIT 1;"
$prov = & docker exec argus-postgres psql -U $User -d $Db -t -A -c $provSql 2>&1
if ($LASTEXITCODE -eq 0) {
  $key = ("$prov").Trim()
  if ($key -eq "internal_paper") {
    Write-Host "OK    default_provider       = internal_paper"
  }
  else {
    Write-Host "WARN  default_provider       = $key (expected internal_paper if migrations seeded)"
  }
}

if ($failed) {
  Write-Error "Restore validation failed: one or more institutional tables are missing."
}
Write-Host "Validation passed: required institutional tables are queryable."
