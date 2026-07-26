# ArgusFounderForceSync
# Founder recovery: keep local checkout on GitHub main even if Sync helper failed.
try {
  $here = Split-Path -Parent $MyInvocation.MyCommand.Path
  $root = Resolve-Path (Join-Path $here "..")
  Push-Location $root
  git fetch origin 2>$null
  git checkout -f -B main origin/main 2>$null
  git reset --hard origin/main 2>$null
  Pop-Location
} catch { }

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
  Write-Error "Missing .env. Copy .env.example to .env and set POSTGRES_PASSWORD before starting."
}

Write-Host "Starting Argus infrastructure (postgres, redis)..."
docker compose up -d
docker compose ps

Write-Host "Waiting for PostgreSQL..."
$deadline = (Get-Date).AddSeconds(90)
$ready = $false
while ((Get-Date) -lt $deadline) {
  docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    $ready = $true
    break
  }
  Start-Sleep -Seconds 2
}
if (-not $ready) {
  throw "PostgreSQL did not become ready. Open Docker Desktop, then run Start Argus again."
}
Write-Host "PostgreSQL is ready."
