#!/usr/bin/env bash
# Novu Builder — minimal backup script (R-40)
#
# Backs up:
#   1. PostgreSQL database (pg_dump → gzip)
#   2. File storage volume (photos, exports)
#
# Usage:
#   BACKUP_DIR=/backups ./scripts/backup.sh
#
# Cron example (daily at 02:00, keep 7 days):
#   0 2 * * * cd /opt/novu-builder && BACKUP_DIR=/backups ./scripts/backup.sh >> /var/log/novu-backup.log 2>&1
#
# Environment variables:
#   BACKUP_DIR      — where to write backup files  (default: ./backups)
#   POSTGRES_USER   — postgres user                (default: novu)
#   POSTGRES_DB     — postgres database name       (default: novu_builder)
#   RETAIN_DAYS     — how many days of backups to keep (default: 7)
#
# IMPORTANT: This script must be run from the project root (next to docker-compose.yml).
# Secrets are read from the running containers — never hardcoded here.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
POSTGRES_USER="${POSTGRES_USER:-novu}"
POSTGRES_DB="${POSTGRES_DB:-novu_builder}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] Starting Novu Builder backup → $BACKUP_DIR"

# ── 1. PostgreSQL dump ────────────────────────────────────────────────────────
DB_FILE="$BACKUP_DIR/db_${TIMESTAMP}.sql.gz"
echo "  → DB dump: $DB_FILE"
docker compose exec -T db \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "$DB_FILE"

# ── 2. File storage archive ───────────────────────────────────────────────────
# Uses a temporary alpine container to tar the named volume directly,
# avoiding any dependency on the backend container being stopped.
STORAGE_FILE="$BACKUP_DIR/storage_${TIMESTAMP}.tar.gz"
echo "  → Storage archive: $STORAGE_FILE"
docker run --rm \
  -v novu_builder_storage_data:/data \
  alpine \
  tar czf - /data \
  > "$STORAGE_FILE"

# ── 3. Prune old backups ──────────────────────────────────────────────────────
echo "  → Pruning backups older than ${RETAIN_DAYS} days"
find "$BACKUP_DIR" -maxdepth 1 -name "db_*.sql.gz"      -mtime +"$RETAIN_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -name "storage_*.tar.gz" -mtime +"$RETAIN_DAYS" -delete

echo "[$(date -Iseconds)] Backup complete."
echo "  DB:      $DB_FILE  ($(du -sh "$DB_FILE" | cut -f1))"
echo "  Storage: $STORAGE_FILE  ($(du -sh "$STORAGE_FILE" | cut -f1))"
