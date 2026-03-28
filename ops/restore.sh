#!/usr/bin/env bash
# =============================================================================
#  ops/restore.sh — Restore PostgreSQL from .pgdump backup (Docker Compose)
#
#  AUTHORITATIVE restore path for backups produced by scripts/backup.sh.
#
#  Usage:
#    ./ops/restore.sh <db_backup.pgdump>         # interactive confirmation
#    ./ops/restore.sh <db_backup.pgdump> --yes   # unattended (CI / recovery)
#
#  This script works with backups produced by:
#    scripts/backup.sh   → db_TIMESTAMP.pgdump     (AUTHORITATIVE)
#
#  For LEGACY .sql.gz backups (produced before 2026-03-28 by old scripts/backup.sh
#  or ops/backup.sh), use the legacy restore procedure documented at the bottom
#  of this file.
#
#  What it does:
#    1. Verifies backup file is non-empty and checksum (if .sha256 exists)
#    2. Stops backend + worker (DB must be idle)
#    3. Drops and recreates novu_builder database
#    4. Copies backup into DB container (pg_restore requires seekable file)
#    5. Restores data via pg_restore
#    6. Verifies table count (must be >= 10)
#    7. Applies any pending Alembic migrations (alembic upgrade head)
#    8. Restarts backend + worker
#    9. Polls health endpoint
#
#  Requirements: docker compose, curl
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
  echo "Usage: $0 <db_backup.pgdump> [--yes]"
  echo ""
  echo "  For LEGACY .sql.gz backups see the comment at the bottom of this file."
  exit 1
fi
[[ -f "$BACKUP_FILE" ]] || die "File not found: $BACKUP_FILE"

# Guard: refuse if someone passes a .sql.gz file by mistake
if [[ "$BACKUP_FILE" == *.sql.gz ]]; then
  die "This script requires .pgdump format (authoritative). Got: $BACKUP_FILE"$'\n'"  For legacy .sql.gz restore, see the LEGACY section at the bottom of this file."
fi

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

# ── 0. Verify checksum (if present) ────────────────────────────────────────────
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ -f "$CHECKSUM_FILE" ]]; then
  log "Verifying checksum …"
  if command -v sha256sum &>/dev/null; then
    sha256sum --check "$CHECKSUM_FILE" || die "Checksum mismatch — backup may be corrupt."
  else
    openssl dgst -sha256 "$BACKUP_FILE" | diff - "$CHECKSUM_FILE" || die "Checksum mismatch."
  fi
  log "✓ Checksum OK"
else
  log "⚠ No checksum file found — skipping integrity check"
fi

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

# ── 3. Copy backup into container + restore ────────────────────────────────────
# pg_restore (custom format) requires a seekable file — cannot be piped via stdin.
# We copy the backup into the container, restore, then remove it.
CONTAINER_ID=$(docker compose -f "$COMPOSE_FILE" ps -q db)
[[ -n "$CONTAINER_ID" ]] || die "DB container is not running."

log "Copying backup into DB container …"
docker cp "$BACKUP_FILE" "$CONTAINER_ID:/tmp/novu_restore.pgdump"

log "Restoring from $(basename "$BACKUP_FILE") …"
docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_restore \
  -U novu \
  --dbname=novu_builder \
  --no-password \
  --jobs=4 \
  /tmp/novu_restore.pgdump \
  2>&1 | grep -v "^pg_restore: creating\|^pg_restore: executing" || true

log "Cleaning up temp file in container …"
docker compose -f "$COMPOSE_FILE" exec -T db rm -f /tmp/novu_restore.pgdump

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

# =============================================================================
# LEGACY: Restore from .sql.gz (backups produced before 2026-03-28)
#
#  Old scripts (scripts/backup.sh before 2026-03-28, ops/backup.sh) produced:
#    db_TIMESTAMP.sql.gz  or  TIMESTAMP/postgres_TIMESTAMP.sql.gz
#
#  To restore a legacy .sql.gz backup manually:
#
#    docker compose stop backend worker
#    docker compose exec db psql -U novu postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='novu_builder' AND pid <> pg_backend_pid();"
#    docker compose exec db psql -U novu postgres -c "DROP DATABASE IF EXISTS novu_builder;"
#    docker compose exec db psql -U novu postgres -c "CREATE DATABASE novu_builder OWNER novu;"
#    gunzip -c /path/to/db_TIMESTAMP.sql.gz | docker compose exec -T db psql -U novu novu_builder
#    docker compose run --rm backend alembic upgrade head
#    docker compose start backend worker
#
#  This legacy path is NOT authoritative and has no automated verify script.
#  Migrate to .pgdump backups (scripts/backup.sh) as soon as possible.
# =============================================================================
