#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/apps/api"
echo "Applying database updates (alembic upgrade head)..."
python -m uv run alembic upgrade head
echo "Verifying Paper Training schema..."
if [[ -x "$ROOT/apps/api/.venv/bin/python" ]]; then
  "$ROOT/apps/api/.venv/bin/python" "$ROOT/scripts/repair_training_schema.py"
else
  python -m uv run python "$ROOT/scripts/repair_training_schema.py"
fi
echo "Database is up to date."
