#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/apps/api"
echo "Applying database updates (alembic upgrade head)..."
python -m uv run alembic upgrade head
echo "Verifying Paper Training schema..."
python "$ROOT/scripts/repair_training_schema.py"
echo "Database is up to date."
