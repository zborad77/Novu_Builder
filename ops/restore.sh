#!/usr/bin/env bash
# =============================================================================
#  ops/restore.sh — Restore PostgreSQL from sql.gz backup (Docker Compose)
#
#  Usage:
#    ./ops/restore.sh <db_backup.sql.gz>         # interactive confirmation
#    ./ops/restore.sh <db_backup.sql.gz> --yes   # unattended (CI / recovery)
#
#  This script works with backups produced by:
#    scripts/backup.sh   → db_TIMESTAMP.sql.gz
#    ops/backup.sh       → TIMESTAMP/postgres_TIMESTAMP.sql.gz
#
#  For .pgdump format backups (from python-backend/scripts/backup_db.sh),
#  use python-backend/scripts/restore_db.sh instead.
#
#  What it does:
#    1. Verifies backup file is non-empty
#    2. Stops backend + worker (DB must be idle)
#    3. Drops and recreates novu_builder database
#    4. Restores data via psql
#    5. Verifies table count (must be >= 10)
#    6. Applies any pending Alembic migrations (alembic upgrade head)
#    7. Restarts backend + worker
#    8. Polls health endpoint
#
#  Requirements: docker compose, gunzip, curl
#  Run from: project root (next to docker-compose.yml)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"

BACKUP_FILE="${1:-}"
AUTO_YES="${2:-}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

# ── Validate input ─────────────────────────────────────────────────────────────
if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <db_backup.sql.gz> [--yes]"
  exit 1
fi
[[ -f "$BACKUP_FILE" ]] || die "File not found: $BACKUP_FILE"

BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)

echo "=================================================="
echo "  Novu Builder — Database Restore"
echo "  Backup: $(basename "$BACKUP_FILE") (${BACKUP_SIZE})"
echo "  Host:   $(hostname)"
echo "  Time:   $(date)"
echo "=================================================="
echo ""
echo "⚠  This will DROP and RECREATE the novu_builder database."
echo "   All existing data will be PERMANENTLY DELETED."
echo ""

if [[ "$AUTO_YES" != "--yes" ]]; then
  read -r -p "Type 'yes' to continue: " CONFIRM
  [[ "$CONFIRM" == "yes" ]] || { echo "Aborted."; exit 0; }
fi

cd "$PROJECT_DIR"

# ── 1. Stop backend + worker ───────────────────────────────────────────────────
log "Stopping backend and worker …"
docker compose -f "$COMPOSE_FILE" stop backend worker 2>/dev/null || true

# ── 2. Drop + recreate DB ──────────────────────────────────────────────────────
log "Terminating active connections …"
docker compose -f "$COMPOSE_FILE" exec -T db \
  psql -U novu postgres --quiet \
  --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='novu_builder' AND pid <> pg_backend_pid();" \
  2>/dev/null || true

log "Dropping database …"
docker compose -f "$COMPOSE_FILE" exec -T db \
  psql -U novu postgres --quiet \
  --command="DROP DATABASE IF EXISTS novu_builder;"

log "Creating database …"
docker compose -f "$COMPOSE_FILE" exec -T db \
  psql -U novu postgres --quiet \
  --command="CREATE DATABASE novu_builder OWNER novu;"

# ── 3. Restore ─────────────────────────────────────────────────────────────────
log "Restoring from $(basename "$BACKUP_FILE") …"
gunzip -c "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T db \
  psql -U novu novu_builder --quiet

log "pg_restore complete."

# ── 4. Verify table count ──────────────────────────────────────────────────────
log "Verifying schema …"
TABLE_COUNT=$(docker compose -f "$COMPOSE_FILE" exec -T db \
  psql -U novu novu_builder --tuples-only --no-align \
  --command="SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" \
  2>/dev/null | tr -d ' \r\n')

log "Tables found: ${TABLE_COUNT}"
if [[ "${TABLE_COUNT:-0}" -lt 10 ]]; then
  die "Only ${TABLE_COUNT} tables found — restore likely failed. Expected 10+."
fi

# ── 5. Apply pending migrations ────────────────────────────────────────────────
log "Applying pending Alembic migrations …"
docker compose -f "$COMPOSE_FILE" run --rm backend alembic upgrade head
log "Alembic at head."

# ── 6. Restart backend + worker ────────────────────────────────────────────────
log "Starting backend and worker …"
docker compose -f "$COMPOSE_FILE" start backend worker

# ── 7. Health poll ─────────────────────────────────────────────────────────────
log "Waiting for backend health (max 60s) …"
HEALTH_URL="http://localhost:8000/api/v1/health"
HEALTHY=0
for i in $(seq 1 12); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    HEALTHY=1
    break
  fi
  sleep 5
done

if [[ $HEALTHY -eq 1 ]]; then
  log "✓ Backend is healthy."
else
  log "⚠ Backend did not respond within 60s — check 'docker compose logs backend'."
fi

# ── 8. Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "=================================================="
log "✅ RESTORE COMPLETE"
echo "=================================================="
echo ""
echo "Verify data manually:"
echo "  docker compose exec db psql -U novu novu_builder -c 'SELECT COUNT(*) FROM organizations;'"
echo "  docker compose exec db psql -U novu novu_builder -c 'SELECT COUNT(*) FROM users WHERE is_active=true;'"
echo "  docker compose run --rm backend alembic current"
echo ""
echo "Smoke check:"
echo "  python scripts/smoke_check_live.py http://localhost <email> <password>"
