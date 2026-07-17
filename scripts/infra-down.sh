#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "Removing Argus containers/networks (named volumes preserved)..."
docker compose down
echo "Named volumes argus_postgres_data and argus_redis_data were not deleted."
