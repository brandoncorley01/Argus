#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FORCE=0
BACKUP=""
for arg in "$@"; do
  if [[ "$arg" == "--force" ]]; then
    FORCE=1
  elif [[ -z "$BACKUP" ]]; then
    BACKUP="$arg"
  fi
done

if [[ ! -f .env ]]; then
  echo "ERROR: Missing .env." >&2
  exit 1
fi
if [[ -z "$BACKUP" || ! -f "$BACKUP" ]]; then
  echo "Usage: ./scripts/restore-db.sh [--force] <path-to-backup.sql>" >&2
  exit 1
fi

echo "WARNING: This will DROP and recreate the local Argus database, then restore from:"
echo "  $BACKUP"
if [[ "$FORCE" -ne 1 ]]; then
  echo "Type RESTORE-LOCAL-DB to confirm."
  read -r confirm
  if [[ "$confirm" != "RESTORE-LOCAL-DB" ]]; then
    echo "Aborted. No changes made."
    exit 1
  fi
else
  echo "Proceeding with --force (non-interactive RC/automation mode)."
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

docker exec argus-postgres pg_isready -U "$USER_NAME" -d postgres

echo "Recreating database '${DB_NAME}'..."
docker exec argus-postgres psql -U "$USER_NAME" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"${DB_NAME}\" WITH (FORCE);"
docker exec argus-postgres psql -U "$USER_NAME" -d postgres -v ON_ERROR_STOP=1 \
  -c "CREATE DATABASE \"${DB_NAME}\" OWNER \"${USER_NAME}\";"

echo "Restoring..."
docker exec -i argus-postgres psql -U "$USER_NAME" -d "$DB_NAME" -v ON_ERROR_STOP=1 < "$BACKUP"

echo "Validating institutional tables..."
"$ROOT/scripts/validate-db-restore.sh"
echo "Restore complete."
