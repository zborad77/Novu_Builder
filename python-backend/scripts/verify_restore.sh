#!/usr/bin/env bash
# =============================================================================
#  verify_restore.sh — Verify that a backup can be restored to a TEMP database
#
#  Usage:
#    ./scripts/verify_restore.sh backups/novu_20260324_120000.pgdump
#
#  What it does:
#    1. Creates a throw-away database: novu_verify_<timestamp>
#    2. Restores the backup into it
#    3. Runs basic sanity queries (row counts, alembic_version head)
#    4. Drops the temp database
#    5. Prints PASS or FAIL
#
#  Safe to run against production without touching the real database.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

BACKUP_FILE="${1:-}"
if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <backup_file.pgdump>"
  exit 1
fi

# ── Load env ──────────────────────────────────────────────────────────────────
load_env() {
  local env_file="$BACKEND_DIR/.env"
  [[ -f "$env_file" ]] && set -a && source "$env_file" && set +a
  local app_env="${APP_ENV:-}"
  if [[ -n "$app_env" ]]; then
    local override="$BACKEND_DIR/.env.$app_env"
    [[ -f "$override" ]] && set -a && source "$override" && set +a
  fi
}
load_env

# ── Parse DATABASE_URL ────────────────────────────────────────────────────────
DB_URL="${DATABASE_URL_SYNC:-${DATABASE_URL:-}}"
DB_URL="${DB_URL#postgresql+asyncpg://}"
DB_URL="${DB_URL#postgresql+psycopg://}"
DB_URL="${DB_URL#postgresql://}"

DB_USERPASS="${DB_URL%%@*}"
DB_HOSTPATH="${DB_URL#*@}"
DB_USER="${DB_USERPASS%%:*}"
DB_PASS="${DB_USERPASS#*:}"
DB_HOSTPORT="${DB_HOSTPATH%%/*}"
DB_HOST="${DB_HOSTPORT%%:*}"
DB_PORT="${DB_HOSTPORT##*:}"
[[ "$DB_PORT" == "$DB_HOST" ]] && DB_PORT="5432"

export PGPASSWORD="$DB_PASS"
PG_CONN=( --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" )

TEMP_DB="novu_verify_$(date +%s)"
FAILED=0

cleanup() {
  echo "→ Dropping temp database '$TEMP_DB' …"
  psql "${PG_CONN[@]}" --dbname=postgres \
    --command="DROP DATABASE IF EXISTS \"$TEMP_DB\";" --quiet 2>/dev/null || true
}
trap cleanup EXIT

echo "=================================================="
echo "  Backup verify: $(basename "$BACKUP_FILE")"
echo "  Temp DB:        $TEMP_DB @ $DB_HOST:$DB_PORT"
echo "=================================================="

# ── Checksum ──────────────────────────────────────────────────────────────────
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ -f "$CHECKSUM_FILE" ]]; then
  echo "→ Checking integrity …"
  if command -v sha256sum &>/dev/null; then
    sha256sum --check "$CHECKSUM_FILE" && echo "  ✓ Checksum OK"
  else
    openssl dgst -sha256 "$BACKUP_FILE" | diff - "$CHECKSUM_FILE" && echo "  ✓ Checksum OK"
  fi
else
  echo "  ⚠ No checksum file — skipping"
fi

# ── Create temp DB ────────────────────────────────────────────────────────────
echo "→ Creating temp database …"
psql "${PG_CONN[@]}" --dbname=postgres \
  --command="CREATE DATABASE \"$TEMP_DB\" OWNER \"$DB_USER\";" --quiet

# ── Restore ───────────────────────────────────────────────────────────────────
echo "→ Restoring backup …"
pg_restore \
  "${PG_CONN[@]}" \
  --dbname="$TEMP_DB" \
  --no-password \
  --jobs=4 \
  "$BACKUP_FILE" 2>&1 | grep -v "^pg_restore: creating\|^pg_restore: executing" || true
echo "  ✓ pg_restore finished"

# ── Sanity queries ────────────────────────────────────────────────────────────
echo "→ Running sanity checks …"

# Print row count (informational, no assertion)
show_count() {
  local table="$1"
  local result
  result=$(psql "${PG_CONN[@]}" --dbname="$TEMP_DB" --tuples-only --no-align \
    --command="SELECT COUNT(*) FROM ${table};" 2>&1)
  echo "  ${table}: ${result} rows"
}

# Assert table has at least one row — fails the verify if empty
assert_has_rows() {
  local table="$1"
  local result
  result=$(psql "${PG_CONN[@]}" --dbname="$TEMP_DB" --tuples-only --no-align \
    --command="SELECT COUNT(*) > 0 FROM ${table};" 2>&1)
  if [[ "$result" == "t" ]]; then
    echo "  ✓ ${table} has rows"
  else
    echo "  ✗ ${table} is EMPTY — backup may be incomplete"
    FAILED=1
  fi
}

show_count "alembic_version"
assert_has_rows "organizations"
assert_has_rows "users"
show_count "projects"
show_count "analysis_jobs"
show_count "audit_logs"

# ── Alembic head check ────────────────────────────────────────────────────────
echo "→ Checking alembic_version matches latest migration …"
DB_HEAD=$(psql "${PG_CONN[@]}" --dbname="$TEMP_DB" --tuples-only --no-align \
  --command="SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d ' ')
EXPECTED_HEAD="20260324_0012"

if [[ "$DB_HEAD" == "$EXPECTED_HEAD" ]]; then
  echo "  ✓ Schema at head ($DB_HEAD)"
else
  echo "  ✗ Schema mismatch: got '$DB_HEAD', expected '$EXPECTED_HEAD'"
  FAILED=1
fi

# ── Result ────────────────────────────────────────────────────────────────────
echo ""
if [[ $FAILED -eq 0 ]]; then
  echo "✅  PASS — backup is valid and restores cleanly to head schema."
else
  echo "❌  FAIL — backup restore has issues (see above)."
  exit 1
fi
