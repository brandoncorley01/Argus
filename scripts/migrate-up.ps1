$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\apps\api"
Write-Host "Applying database updates (alembic upgrade head)..."
python -m uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) {
  throw "Database migrate failed. Home/Paper Training cannot load until this succeeds."
}

# Repair stamped-but-missing training tables (no embedded Python in this .ps1).
Write-Host "Verifying Paper Training schema..."
python "$Root\scripts\repair_training_schema.py"
if ($LASTEXITCODE -ne 0) {
  throw "Paper Training schema verify/repair failed."
}

Write-Host "Database is up to date."
