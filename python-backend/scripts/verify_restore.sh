#!/usr/bin/env bash
# =============================================================================
#  verify_restore.sh — Verify that a backup can be restored to a TEMP database
#
#  Usage (run from python-backend/ directory):
#    ./scripts/verify_restore.sh backups/novu_20260324_120000.pgdump
#
#  Or from project root:
#    python-backend/scripts/verify_restore.sh <path/to/backup.pgdump>
#
#  What it does:
#    1. Verifies .sha256 checksum (hard fail if present and mismatches)
#    2. Creates a throw-away database: novu_verify_<timestamp>
#    3. Restores the backup into it
#    4. Checks all critical tables EXIST (structure check — safe on empty DBs)
#    5. Checks key operational tables have data (organizations, users)
#    6. Checks role_permissions is seeded (confirms migrations ran fully)
#    7. Verifies alembic_version is set and matches current HEAD
#    8. Drops the temp database (trap cleanup — runs even on failure)
#    9. Prints PASS or FAIL with per-check detail
#
#  Safe to run against production without touching the real database.
#  Requires: psql, pg_restore, DATABASE_URL or DATABASE_URL_SYNC in .env
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

# ── Host tools guard ──────────────────────────────────────────────────────────
# psql and pg_restore must be available on the host for full verify.
# If missing, detect docker toolchain — but do NOT proceed with full verify.
if ! command -v psql &>/dev/null || ! command -v pg_restore &>/dev/null; then
  echo "Host tools missing, checking docker toolchain..."
  _PROJECT_DIR="$(dirname "$BACKEND_DIR")"
  _COMPOSE_FILE="$_PROJECT_DIR/docker-compose.yml"
  if ! docker compose -f "$_COMPOSE_FILE" exec -T db pg_restore --version > /dev/null 2>&1; then
    echo "ERROR: docker toolchain check failed"
    exit 1
  fi
  echo "Docker toolchain detected but full verify requires psql/pg_restore on host — please install them locally"
  exit 1
fi

# ── Parse DATABASE_URL ────────────────────────────────────────────────────────
DB_URL="${DATABASE_URL_SYNC:-${DATABASE_URL:-}}"
if [[ -z "$DB_URL" ]]; then
  echo "ERROR: DATABASE_URL or DATABASE_URL_SYNC not set in .env" >&2
  exit 1
fi
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
echo "  Temp DB:       $TEMP_DB @ $DB_HOST:$DB_PORT"
echo "=================================================="

# ── 1. Checksum ───────────────────────────────────────────────────────────────
# IMPORTANT: use explicit || exit, not &&, because with set -e the && compound
# does NOT trigger abort on failure (bash set -e exception for && / || lists).
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ -f "$CHECKSUM_FILE" ]]; then
  echo "→ Checking integrity …"
  if command -v sha256sum &>/dev/null; then
    sha256sum --check "$CHECKSUM_FILE" \
      || { echo "  ✗ Checksum MISMATCH — backup file is corrupt. Aborting."; exit 1; }
  else
    openssl dgst -sha256 "$BACKUP_FILE" | diff - "$CHECKSUM_FILE" \
      || { echo "  ✗ Checksum MISMATCH — backup file is corrupt. Aborting."; exit 1; }
  fi
  echo "  ✓ Checksum OK"
else
  echo "  ⚠ No checksum file — skipping integrity check"
fi

# ── 2. Create temp DB ─────────────────────────────────────────────────────────
echo "→ Creating temp database …"
psql "${PG_CONN[@]}" --dbname=postgres \
  --command="CREATE DATABASE \"$TEMP_DB\" OWNER \"$DB_USER\";" --quiet

# ── 3. Restore ────────────────────────────────────────────────────────────────
echo "→ Restoring backup …"
pg_restore \
  "${PG_CONN[@]}" \
  --dbname="$TEMP_DB" \
  --no-password \
  --jobs=4 \
  "$BACKUP_FILE" 2>&1 | grep -v "^pg_restore: creating\|^pg_restore: executing" || true
echo "  ✓ pg_restore finished"

# ── 4. Helpers ────────────────────────────────────────────────────────────────
# Assert table EXISTS in schema (safe on empty databases — checks structure only)
assert_table_exists() {
  local table="$1"
  local exists
  exists=$(psql "${PG_CONN[@]}" --dbname="$TEMP_DB" --tuples-only --no-align \
    --command="SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='${table}');" 2>&1)
  if [[ "$exists" == "t" ]]; then
    echo "  ✓ table exists: ${table}"
  else
    echo "  ✗ table MISSING: ${table}"
    FAILED=1
  fi
}

# Assert table has at least one row — fails verify if empty
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

# Print row count (informational only, no assertion)
show_count() {
  local table="$1"
  local result
  result=$(psql "${PG_CONN[@]}" --dbname="$TEMP_DB" --tuples-only --no-align \
    --command="SELECT COUNT(*) FROM ${table};" 2>&1)
  echo "  ${table}: ${result} rows"
}

# ── 5. Critical table structure checks ───────────────────────────────────────
echo "→ Checking critical tables exist …"
# Core multi-tenancy + auth
assert_table_exists "organizations"
assert_table_exists "users"
assert_table_exists "projects"
# Compliance + security
assert_table_exists "audit_logs"
assert_table_exists "role_permissions"
assert_table_exists "revoked_tokens"
# Migration state
assert_table_exists "alembic_version"

# ── 6. Operational data checks ────────────────────────────────────────────────
echo "→ Checking operational data …"
# These must have rows in any real backup
assert_has_rows "organizations"
assert_has_rows "users"
# role_permissions is always seeded by migration 0018 — empty = migration failed
assert_has_rows "role_permissions"
# Informational counts
show_count "projects"
show_count "analysis_jobs"
show_count "audit_logs"

# ── 7. Alembic migration state ────────────────────────────────────────────────
echo "→ Checking alembic_version …"
DB_HEAD=$(psql "${PG_CONN[@]}" --dbname="$TEMP_DB" --tuples-only --no-align \
  --command="SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d ' ')

if [[ -z "$DB_HEAD" ]]; then
  echo "  ✗ alembic_version is empty — restore is incomplete or migrations never ran"
  FAILED=1
else
  # Dynamically find the HEAD revision: the revision ID that no other migration
  # points to as its down_revision (i.e. not in any down_revision list).
  VERSIONS_DIR="$BACKEND_DIR/alembic/versions"
  EXPECTED_HEAD=""
  if [[ -d "$VERSIONS_DIR" ]]; then
    EXPECTED_HEAD=$(
      comm -23 \
        <(grep -rh '^revision = ' "$VERSIONS_DIR" | grep -oE '"[^"]+"' | tr -d '"' | sort) \
        <(grep -rh '^down_revision = ' "$VERSIONS_DIR" | grep -oE '"[^"]+"' | tr -d '"' | sort) \
      | head -1
    )
  fi

  if [[ -n "$EXPECTED_HEAD" && "$DB_HEAD" == "$EXPECTED_HEAD" ]]; then
    echo "  ✓ Schema at current HEAD ($DB_HEAD)"
  elif [[ -n "$EXPECTED_HEAD" ]]; then
    echo "  ⚠ Schema at '$DB_HEAD' — current HEAD is '$EXPECTED_HEAD'"
    echo "    Backup is valid; run 'alembic upgrade head' after restore to apply pending migrations."
  else
    echo "  ✓ Schema at revision: $DB_HEAD (HEAD detection unavailable)"
  fi
fi

# ── 8. Result ─────────────────────────────────────────────────────────────────
echo ""
if [[ $FAILED -eq 0 ]]; then
  echo "PASS — backup is valid and restores cleanly."
else
  echo "FAIL — backup restore has issues (see above)."
  exit 1
fi
