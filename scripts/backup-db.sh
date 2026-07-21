#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "ERROR: Missing .env. Copy .env.example to .env before backup." >&2
  exit 1
fi

get_env() {
  local key="$1"
  local line
  line="$(grep -E "^[[:space:]]*${key}=" .env | head -n1 || true)"
  if [[ -z "$line" ]]; then
    echo "ERROR: Missing ${key} in .env" >&2
    exit 1
  fi
  echo "${line#*=}" | tr -d '"' | tr -d "'"
}

USER_NAME="$(get_env POSTGRES_USER)"
DB_NAME="$(get_env POSTGRES_DB)"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="$ROOT/backups"
mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/argus_postgres_${STAMP}.sql"

echo "Backing up database '${DB_NAME}' via docker exec (password not printed)..."
docker exec argus-postgres pg_isready -U "$USER_NAME" -d "$DB_NAME"
docker exec argus-postgres pg_dump -U "$USER_NAME" -d "$DB_NAME" --no-owner --no-acl > "$OUT_FILE"

if [[ ! -s "$OUT_FILE" ]]; then
  echo "ERROR: Backup failed or empty: $OUT_FILE" >&2
  exit 1
fi

echo "Backup written: $OUT_FILE"
echo "Size bytes: $(wc -c < "$OUT_FILE")"
echo "$OUT_FILE"
