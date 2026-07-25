$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\apps\api"
Write-Host "Applying database updates (alembic upgrade head)..."
python -m uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) {
  throw "Database migrate failed. Home/Paper Training cannot load until this succeeds."
}

# Repair: alembic_version can be stamped at head while training tables are missing
# (e.g. interrupted migrate / prior stamp). Re-run the Paper Training Lab revision.
$probe = @'
from sqlalchemy import text
from app.core.settings import clear_settings_cache, get_settings
from app.db.session import get_session_factory, reset_engine
clear_settings_cache()
reset_engine()
get_settings()
db = get_session_factory()()
missing = db.execute(text("""
  SELECT NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'paper_training_settings'
  )
""")).scalar()
print("1" if missing else "0")
'@
$missing = python -c $probe
if ($LASTEXITCODE -ne 0) {
  throw "Could not verify paper_training_settings after migrate."
}
if ($missing.Trim() -eq "1") {
  Write-Host "paper_training_settings missing while alembic at head — repairing..."
  python -m uv run alembic stamp d6e7f8a9b0c1
  if ($LASTEXITCODE -ne 0) { throw "Repair stamp failed." }
  python -m uv run alembic upgrade head
  if ($LASTEXITCODE -ne 0) { throw "Repair upgrade failed." }
}

Write-Host "Database is up to date."
