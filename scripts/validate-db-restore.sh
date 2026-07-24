#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

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
FAILED=0

echo "Restore validation against database '${DB_NAME}' (counts only; no secrets):"
for t in audit_events users paper_portfolios paper_orders paper_fills paper_positions execution_providers; do
  if ! count="$(docker exec argus-postgres psql -U "$USER_NAME" -d "$DB_NAME" -t -A -c "SELECT COUNT(*) FROM ${t};" 2>&1)"; then
    echo "FAIL  table missing or query error: ${t} — ${count}"
    FAILED=1
    continue
  fi
  echo "OK    $(printf '%-22s' "$t") rows=${count}"
done

key="$(docker exec argus-postgres psql -U "$USER_NAME" -d "$DB_NAME" -t -A -c \
  "SELECT provider_key FROM execution_providers WHERE is_default IS TRUE LIMIT 1;" || true)"
key="$(echo "$key" | tr -d '[:space:]')"
if [[ "$key" == "internal_paper" ]]; then
  echo "OK    default_provider       = internal_paper"
else
  echo "WARN  default_provider       = '${key}' (expected internal_paper if migrations seeded)"
fi

if [[ "$FAILED" -ne 0 ]]; then
  echo "ERROR: Restore validation failed." >&2
  exit 1
fi
echo "Validation passed: required institutional tables are queryable."
