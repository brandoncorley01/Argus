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
