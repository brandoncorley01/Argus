#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and set POSTGRES_PASSWORD before starting." >&2
  exit 1
fi

echo "Starting Argus infrastructure (postgres, redis)..."
docker compose up -d
docker compose ps

echo "Waiting for PostgreSQL..."
deadline=$((SECONDS + 90))
ready=0
while (( SECONDS < deadline )); do
  if docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "PostgreSQL did not become ready. Start Docker, then retry." >&2
  exit 1
fi
echo "PostgreSQL is ready."
