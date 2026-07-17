#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "WARNING: This will permanently delete local Argus Postgres and Redis data volumes."
echo "Type DELETE-LOCAL-DATA to confirm."
read -r confirm
if [[ "$confirm" != "DELETE-LOCAL-DATA" ]]; then
  echo "Aborted. No volumes deleted."
  exit 1
fi

docker compose down -v
echo "Containers removed and named volumes deleted."
