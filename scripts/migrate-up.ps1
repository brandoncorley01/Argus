$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Wait-ArgusPostgres {
  param([int]$TimeoutSec = 90)
  Write-Host "Waiting for PostgreSQL to accept connections..."
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  $last = ""
  while ((Get-Date) -lt $deadline) {
    try {
      $out = & docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' 2>&1
      $last = ($out | Out-String).Trim()
      if ($LASTEXITCODE -eq 0) {
        Write-Host "PostgreSQL is ready."
        return
      }
    } catch {
      $last = $_.Exception.Message
    }
    Start-Sleep -Seconds 2
  }
  throw (
    "PostgreSQL did not become ready within ${TimeoutSec}s. " +
    "Open Docker Desktop, confirm containers are running (docker compose ps), " +
    "then press Start Argus again. Detail: $last"
  )
}

function Invoke-ArgusAlembicUpgrade {
  Set-Location "$Root\apps\api"
  $ApiPython = Join-Path $Root "apps\api\.venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $ApiPython) {
    # Same interpreter Start Argus uses for uvicorn.
    & $ApiPython -m alembic upgrade head
    if ($LASTEXITCODE -eq 0) { return 0 }
    # Incomplete venv - fall through to uv-managed run.
    Write-Host "API venv alembic failed (exit $LASTEXITCODE); trying uv run..."
  }
  python -m uv run alembic upgrade head
  return $LASTEXITCODE
}

if (-not (Test-Path (Join-Path $Root ".env"))) {
  throw "Missing .env. Copy .env.paper.example to .env and set POSTGRES_PASSWORD before Start Argus."
}

# Compose may still be booting even after infra-up returns.
Wait-ArgusPostgres -TimeoutSec 90

Write-Host "Applying database updates (alembic upgrade head)..."
$attempt = 0
$maxAttempts = 5
$migrateOk = $false
$lastErr = ""
while ($attempt -lt $maxAttempts -and -not $migrateOk) {
  $attempt += 1
  try {
    $code = Invoke-ArgusAlembicUpgrade
    if ($code -eq 0) {
      $migrateOk = $true
      break
    }
    $lastErr = "alembic exit code $code"
  } catch {
    $lastErr = $_.Exception.Message
  }
  if ($attempt -lt $maxAttempts) {
    Write-Host "Database not ready yet (attempt $attempt/$maxAttempts). Retrying in 3s..."
    Start-Sleep -Seconds 3
    Wait-ArgusPostgres -TimeoutSec 30
  }
}
if (-not $migrateOk) {
  throw (
    "Database migrate failed - Argus could not connect to PostgreSQL. " +
    "Check: (1) Docker Desktop is running, (2) .env DATABASE_URL password matches " +
    "POSTGRES_PASSWORD, (3) port 5432 is free. " +
    "Then Start Argus again. Detail: $lastErr"
  )
}

# Use the API venv (same as Start Argus), not system Python.
Write-Host "Verifying Paper Training schema..."
Set-Location $Root
$ApiPython = Join-Path $Root "apps\api\.venv\Scripts\python.exe"
if (Test-Path -LiteralPath $ApiPython) {
  & $ApiPython "$Root\scripts\repair_training_schema.py"
} else {
  Set-Location "$Root\apps\api"
  python -m uv run python "$Root\scripts\repair_training_schema.py"
}
if ($LASTEXITCODE -ne 0) {
  throw (
    "Paper Training schema verify/repair failed. " +
    "PostgreSQL may still be starting or DATABASE_URL in .env may be wrong. " +
    "Start Docker Desktop, then Start Argus again."
  )
}

Write-Host "Database is up to date."
