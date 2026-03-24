#!/usr/bin/env bash
# =============================================================================
#  backup_db.sh — PostgreSQL backup via pg_dump (custom format)
#
#  Usage:
#    ./scripts/backup_db.sh                      # uses .env / env vars
#    APP_ENV=production ./scripts/backup_db.sh   # uses .env.production overlay
#
#  Output:
#    backups/novu_YYYYMMDD_HHMMSS.pgdump
#    backups/novu_YYYYMMDD_HHMMSS.pgdump.sha256
#
#  Requirements: pg_dump (PostgreSQL client tools), openssl or sha256sum
# =============================================================================
set -euo pipefail

# Prevent concurrent backup runs (advisory lock)
exec 9>/tmp/novu_backup.lock
if ! flock -n 9; then
  echo "ERROR: Another backup is already running. Exiting." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-$BACKEND_DIR/backups}"

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

# ── Parse DATABASE_URL ─────────────────────────────────────────────────────────
# Supports: postgresql+asyncpg://user:pass@host:port/dbname
#           postgresql+psycopg://user:pass@host:port/dbname
DB_URL="${DATABASE_URL_SYNC:-${DATABASE_URL:-}}"
if [[ -z "$DB_URL" ]]; then
  echo "ERROR: DATABASE_URL or DATABASE_URL_SYNC not set." >&2
  exit 1
fi

# Strip SQLAlchemy driver prefix
DB_URL="${DB_URL#postgresql+asyncpg://}"
DB_URL="${DB_URL#postgresql+psycopg://}"
DB_URL="${DB_URL#postgresql://}"

# user:pass@host:port/dbname
DB_USERPASS="${DB_URL%%@*}"
DB_HOSTPATH="${DB_URL#*@}"
DB_USER="${DB_USERPASS%%:*}"
DB_PASS="${DB_USERPASS#*:}"
DB_HOSTPORT="${DB_HOSTPATH%%/*}"
DB_NAME="${DB_HOSTPATH#*/}"
DB_HOST="${DB_HOSTPORT%%:*}"
DB_PORT="${DB_HOSTPORT##*:}"
[[ "$DB_PORT" == "$DB_HOST" ]] && DB_PORT="5432"

# ── Backup ────────────────────────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/novu_${TIMESTAMP}.pgdump"

echo "→ Backing up database '$DB_NAME' @ $DB_HOST:$DB_PORT …"
PGPASSWORD="$DB_PASS" pg_dump \
  --host="$DB_HOST" \
  --port="$DB_PORT" \
  --username="$DB_USER" \
  --dbname="$DB_NAME" \
  --format=custom \
  --compress=9 \
  --no-password \
  --no-owner \
  --no-privileges \
  --file="$BACKUP_FILE"

# Checksum
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if command -v sha256sum &>/dev/null; then
  sha256sum "$BACKUP_FILE" > "$CHECKSUM_FILE"
else
  openssl dgst -sha256 "$BACKUP_FILE" > "$CHECKSUM_FILE"
fi

SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "✓ Backup complete: $BACKUP_FILE ($SIZE)"
echo "  Checksum: $CHECKSUM_FILE"

# ── Prune old backups (keep last 14) ─────────────────────────────────────────
KEEP=${BACKUP_KEEP:-14}
mapfile -t OLD_BACKUPS < <(ls -t "$BACKUP_DIR"/*.pgdump 2>/dev/null | tail -n +$((KEEP + 1)))
for f in "${OLD_BACKUPS[@]}"; do
  echo "  Pruning old backup: $(basename "$f")"
  rm -f "$f" "${f}.sha256"
done
