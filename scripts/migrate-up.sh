#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.paper.example to .env and set POSTGRES_PASSWORD before Start Argus." >&2
  exit 1
fi

wait_postgres() {
  local timeout="${1:-90}"
  echo "Waiting for PostgreSQL to accept connections..."
  local deadline=$((SECONDS + timeout))
  local last=""
  while (( SECONDS < deadline )); do
    if last="$(docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' 2>&1)"; then
      echo "PostgreSQL is ready."
      return 0
    fi
    sleep 2
  done
  echo "PostgreSQL did not become ready within ${timeout}s. Start Docker, then retry. Detail: ${last}" >&2
  return 1
}

run_alembic() {
  cd "$ROOT/apps/api"
  if [[ -x "$ROOT/apps/api/.venv/bin/python" ]]; then
    "$ROOT/apps/api/.venv/bin/python" -m alembic upgrade head
  else
    python -m uv run alembic upgrade head
  fi
}

wait_postgres 90

echo "Applying database updates (alembic upgrade head)..."
attempt=0
until run_alembic; do
  attempt=$((attempt + 1))
  if (( attempt >= 5 )); then
    echo "Database migrate failed — could not connect to PostgreSQL. Check Docker Desktop and .env DATABASE_URL." >&2
    exit 1
  fi
  echo "Database not ready yet (attempt ${attempt}/5). Retrying in 3s..."
  sleep 3
  wait_postgres 30
done

echo "Verifying Paper Training schema..."
cd "$ROOT"
if [[ -x "$ROOT/apps/api/.venv/bin/python" ]]; then
  "$ROOT/apps/api/.venv/bin/python" "$ROOT/scripts/repair_training_schema.py"
else
  cd "$ROOT/apps/api"
  python -m uv run python "$ROOT/scripts/repair_training_schema.py"
fi
echo "Database is up to date."
