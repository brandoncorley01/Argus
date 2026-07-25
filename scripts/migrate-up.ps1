$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\apps\api"
Write-Host "Applying database updates (alembic upgrade head)..."
python -m uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) {
  throw "Database migrate failed. Home/Paper Training cannot load until this succeeds."
}

# Use the API venv (same as Start Argus), not system Python.
Write-Host "Verifying Paper Training schema..."
$ApiPython = Join-Path $Root "apps\api\.venv\Scripts\python.exe"
if (Test-Path -LiteralPath $ApiPython) {
  & $ApiPython "$Root\scripts\repair_training_schema.py"
} else {
  python -m uv run python "$Root\scripts\repair_training_schema.py"
}
if ($LASTEXITCODE -ne 0) {
  throw "Paper Training schema verify/repair failed."
}

Write-Host "Database is up to date."
