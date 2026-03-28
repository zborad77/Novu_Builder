#!/usr/bin/env bash
# =============================================================================
#  ops/restore.sh — Restore PostgreSQL from .pgdump backup (Docker Compose)
#
#  AUTHORITATIVE restore path for backups produced by scripts/backup.sh.
#
#  Usage:
#    ./ops/restore.sh <db_backup.pgdump>                    # interactive; verify runs first
#    ./ops/restore.sh <db_backup.pgdump> --yes              # unattended (CI / recovery)
#    ./ops/restore.sh <db_backup.pgdump> --skip-verify      # bypass verify (explicit)
#    ./ops/restore.sh <db_backup.pgdump> --yes --skip-verify
#
#  This script works with backups produced by:
#    scripts/backup.sh   → db_TIMESTAMP.pgdump     (AUTHORITATIVE)
#
#  For LEGACY .sql.gz backups (produced before 2026-03-28 by old scripts/backup.sh
#  or ops/backup.sh), use the legacy restore procedure documented at the bottom
#  of this file.
#
#  What it does:
#    0. Runs verify_restore.sh against the backup (temp DB, non-destructive)
#       Skip with --skip-verify (prints WARNING + sleeps 2s)
#    1. Verifies backup file is non-empty and checksum (if .sha256 exists)
#    2. Stops backend + worker (DB must be idle)
#    3. Drops and recreates novu_builder database
#    4. Copies backup into DB container (pg_restore requires seekable file)
#    5. Restores data via pg_restore
#    6. Verifies critical tables exist + alembic_version is set
#    7. Applies any pending Alembic migrations (alembic upgrade head)
#    8. Restarts backend + worker
#    9. Polls health endpoint
#
#  verify_restore.sh requires: psql, pg_restore on host + DATABASE_URL in
#  python-backend/.env. Use --skip-verify if these are not available.
#
#  Requirements: docker compose, curl
#  Run from: project root (next to docker-compose.yml)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"

BACKUP_FILE="${1:-}"
AUTO_YES=""
SKIP_VERIFY=""
for _arg in "${@:2}"; do
  case "$_arg" in
    --yes)         AUTO_YES="--yes" ;;
    --skip-verify) SKIP_VERIFY="--skip-verify" ;;
    *) echo "Unknown argument: $_arg" >&2; exit 1 ;;
  esac
done

# ── Production safety guard ────────────────────────────────────────────────────
if [ "${ENV:-}" = "production" ] && [ "$SKIP_VERIFY" = "--skip-verify" ]; then
  echo "ERROR: skip-verify not allowed in production"
  exit 1
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

# ── Validate input ─────────────────────────────────────────────────────────────
if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <db_backup.pgdump> [--yes] [--skip-verify]"
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

# ── Checksum enforcement (mandatory) ──────────────────────────────────────────
if [ ! -f "${BACKUP_FILE}.sha256" ]; then
  die "Checksum file not found: ${BACKUP_FILE}.sha256 — aborting (generate with: sha256sum \"$BACKUP_FILE\" > \"${BACKUP_FILE}.sha256\")"
fi
log "Verifying checksum …"
sha256sum -c "${BACKUP_FILE}.sha256" || die "Checksum mismatch — backup may be corrupt."
log "✓ Checksum OK"
echo ""

# ── Pre-restore verify ─────────────────────────────────────────────────────────
VERIFY_SCRIPT="$PROJECT_DIR/python-backend/scripts/verify_restore.sh"
if [[ "$SKIP_VERIFY" == "--skip-verify" ]]; then
  echo "WARNING: verify skipped — unsafe operation"
  sleep 2
else
  [ -x "$VERIFY_SCRIPT" ] || { echo "ERROR: verify script missing or not executable: $VERIFY_SCRIPT"; exit 1; }
  if ! timeout 60 bash "$VERIFY_SCRIPT" "$BACKUP_FILE"; then
    echo "ERROR: verify_restore.sh FAILED or timed out (>60s) — aborting restore"
    exit 1
  fi
  echo "Verify OK — continuing restore"
fi
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

# ── 4. Verify critical tables and migration state ─────────────────────────────
# Check specific critical tables — concrete assertion, not a count heuristic.
log "Verifying restore integrity …"

_check_table() {
  local tbl="$1"
  local exists
  exists=$(docker compose -f "$COMPOSE_FILE" exec -T db \
    psql -U novu novu_builder --tuples-only --no-align \
    --command="SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='${tbl}');" \
    2>/dev/null | tr -d ' \r\n')
  if [[ "$exists" == "t" ]]; then
    log "  ✓ ${tbl}"
  else
    die "Critical table '${tbl}' is missing after restore — backup may be incomplete."
  fi
}

_check_table "organizations"
_check_table "users"
_check_table "projects"
_check_table "audit_logs"
_check_table "role_permissions"

# Verify alembic_version is populated (empty = migrations never ran or restore failed)
ALEMBIC_REV=$(docker compose -f "$COMPOSE_FILE" exec -T db \
  psql -U novu novu_builder --tuples-only --no-align \
  --command="SELECT version_num FROM alembic_version;" \
  2>/dev/null | tr -d ' \r\n')
[[ -n "$ALEMBIC_REV" ]] || die "alembic_version table is empty — restore is incomplete."
log "  ✓ alembic_version: $ALEMBIC_REV"

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
