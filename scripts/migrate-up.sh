#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/apps/api"
echo "Applying database updates (alembic upgrade head)..."
python -m uv run alembic upgrade head

# Repair: alembic_version can be stamped at head while training tables are missing.
missing="$(
  PYTHONPATH=. python - <<'PY'
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
PY
)"
if [[ "${missing}" == "1" ]]; then
  echo "paper_training_settings missing while alembic at head — repairing..."
  python -m uv run alembic stamp d6e7f8a9b0c1
  python -m uv run alembic upgrade head
fi

echo "Database is up to date."
