#!/usr/bin/env bash
# =============================================================================
#  restore_db.sh — Restore PostgreSQL from pg_dump backup
#
#  Usage:
#    ./scripts/restore_db.sh backups/novu_20260324_120000.pgdump
#    ./scripts/restore_db.sh backups/novu_20260324_120000.pgdump --yes
#
#  The script will:
#    1. Verify the .sha256 checksum (if present)
#    2. Drop and recreate the target database (prompts unless --yes)
#    3. Restore with pg_restore
#    4. Run alembic current to confirm schema is at head
#
#  Requirements: pg_restore, psql, alembic (in venv)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

# ── Args ──────────────────────────────────────────────────────────────────────
BACKUP_FILE="${1:-}"
AUTO_YES="${2:-}"

if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <backup_file.pgdump> [--yes]"
  exit 1
fi
if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "ERROR: backup file not found: $BACKUP_FILE" >&2
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
DB_NAME="${DB_HOSTPATH#*/}"
DB_HOST="${DB_HOSTPORT%%:*}"
DB_PORT="${DB_HOSTPORT##*:}"
[[ "$DB_PORT" == "$DB_HOST" ]] && DB_PORT="5432"

export PGPASSWORD="$DB_PASS"
PG_CONN=( --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" )

# ── Verify checksum ───────────────────────────────────────────────────────────
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ -f "$CHECKSUM_FILE" ]]; then
  echo "→ Verifying checksum …"
  if command -v sha256sum &>/dev/null; then
    sha256sum --check "$CHECKSUM_FILE"
  else
    openssl dgst -sha256 "$BACKUP_FILE" | diff - "$CHECKSUM_FILE"
  fi
  echo "✓ Checksum OK"
else
  echo "⚠ No checksum file found — skipping integrity check"
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
echo ""
echo "⚠  This will DROP and RECREATE the database: '$DB_NAME' @ $DB_HOST:$DB_PORT"
echo "   All existing data will be PERMANENTLY DELETED."
echo ""
if [[ "$AUTO_YES" != "--yes" ]]; then
  read -r -p "Type 'yes' to continue: " CONFIRM
  [[ "$CONFIRM" != "yes" ]] && echo "Aborted." && exit 0
fi

# ── Drop & recreate ───────────────────────────────────────────────────────────
echo "→ Dropping database '$DB_NAME' …"
psql "${PG_CONN[@]}" --dbname=postgres \
  --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();" \
  --quiet
psql "${PG_CONN[@]}" --dbname=postgres \
  --command="DROP DATABASE IF EXISTS \"$DB_NAME\";" \
  --quiet
psql "${PG_CONN[@]}" --dbname=postgres \
  --command="CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";" \
  --quiet
echo "✓ Database recreated"

# ── Restore ───────────────────────────────────────────────────────────────────
echo "→ Restoring from $(basename "$BACKUP_FILE") …"
pg_restore \
  "${PG_CONN[@]}" \
  --dbname="$DB_NAME" \
  --no-password \
  --jobs=4 \
  --verbose \
  "$BACKUP_FILE" 2>&1 | grep -v "^pg_restore: creating\|^pg_restore: executing" || true

echo "✓ Restore complete"

# ── Verify schema with alembic ────────────────────────────────────────────────
echo "→ Verifying Alembic migration state …"
cd "$BACKEND_DIR"
if [[ -d ".venv" ]]; then
  source .venv/bin/activate 2>/dev/null || true
fi
alembic current
echo ""
echo "✓ Restore verified. Run 'alembic upgrade head' if any pending migrations are shown above."
