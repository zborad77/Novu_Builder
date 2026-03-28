#!/usr/bin/env bash
# Novu Builder — operator backup entrypoint (R-40)
#
# Backs up:
#   1. PostgreSQL database (pg_dump custom archive → .pgdump)   ← AUTHORITATIVE FORMAT
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
#
# Restore: ./ops/restore.sh <db_TIMESTAMP.pgdump>
# Verify:  python-backend/scripts/verify_restore.sh <db_TIMESTAMP.pgdump>

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
POSTGRES_USER="${POSTGRES_USER:-novu}"
POSTGRES_DB="${POSTGRES_DB:-novu_builder}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] Starting Novu Builder backup → $BACKUP_DIR"

# ── 1. PostgreSQL dump (custom archive format) ────────────────────────────────
# Authoritative DB backup format: .pgdump (pg_dump custom archive)
# Restores via: ops/restore.sh or python-backend/scripts/restore_db.sh
DB_FILE="$BACKUP_DIR/db_${TIMESTAMP}.pgdump"
echo "  → DB dump: $DB_FILE"
docker compose exec -T db \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-privileges \
  > "$DB_FILE"

# Checksum for integrity verification
if command -v sha256sum &>/dev/null; then
  sha256sum "$DB_FILE" > "${DB_FILE}.sha256"
else
  openssl dgst -sha256 "$DB_FILE" > "${DB_FILE}.sha256"
fi
echo "  → Checksum: ${DB_FILE}.sha256"

# ── Manifest (supplemental artefact — does not affect .pgdump or .sha256) ────
MANIFEST_FILE="$BACKUP_DIR/manifest_${TIMESTAMP}.json"
ALEMBIC_HEAD=$(docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" \
  --tuples-only --no-align \
  --command="SELECT version_num FROM alembic_version;" 2>/dev/null \
  | tr -d ' \r\n') || ALEMBIC_HEAD="unknown"
[[ -n "$ALEMBIC_HEAD" ]] || ALEMBIC_HEAD="unknown"
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# KROK 1: warn if metadata could not be resolved
[[ "$ALEMBIC_HEAD" == "unknown" ]] && echo "WARNING: alembic head unknown"
[[ "$GIT_SHA"      == "unknown" ]] && echo "WARNING: git sha unknown"

# KROK 2+3: manifest only if pg_dump + checksum both produced non-empty files
[ -s "$DB_FILE" ]              || { echo "ERROR: DB file missing or empty — manifest not written"; exit 1; }
[ -s "${DB_FILE}.sha256" ]     || { echo "ERROR: Checksum file missing or empty — manifest not written"; exit 1; }

# KROK 4: atomic write (temp → mv prevents partial manifest on crash/interrupt)
MANIFEST_TMP="${MANIFEST_FILE}.tmp"
cat > "$MANIFEST_TMP" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "db_file": "db_${TIMESTAMP}.pgdump",
  "checksum_file": "db_${TIMESTAMP}.pgdump.sha256",
  "alembic_head": "${ALEMBIC_HEAD}",
  "git_sha": "${GIT_SHA}",
  "backup_version": "v2"
}
EOF
mv "$MANIFEST_TMP" "$MANIFEST_FILE"
echo "  → Manifest: $MANIFEST_FILE"

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
find "$BACKUP_DIR" -maxdepth 1 -name "db_*.pgdump"        -mtime +"$RETAIN_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -name "db_*.pgdump.sha256" -mtime +"$RETAIN_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -name "manifest_*.json"    -mtime +"$RETAIN_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -name "storage_*.tar.gz"   -mtime +"$RETAIN_DAYS" -delete

echo "[$(date -Iseconds)] Backup complete."
echo "  DB:      $DB_FILE  ($(du -sh "$DB_FILE" | cut -f1))"
echo "  Storage: $STORAGE_FILE  ($(du -sh "$STORAGE_FILE" | cut -f1))"

# ── 4. Off-site sync (optional) ───────────────────────────────────────────────
# Set BACKUP_REMOTE to enable: e.g. BACKUP_REMOTE=user@host:/remote/backups
# Failure does NOT affect the exit status of the local backup.
if [[ -n "${BACKUP_REMOTE:-}" ]]; then
  echo "[$(date -Iseconds)] Syncing to remote: $BACKUP_REMOTE"
  _SYNC_FILES=( "$DB_FILE" "${DB_FILE}.sha256" )
  [[ -f "$MANIFEST_FILE" ]] && _SYNC_FILES+=( "$MANIFEST_FILE" )
  if rsync -az "${_SYNC_FILES[@]}" "$BACKUP_REMOTE/"; then
    echo "  → Remote sync OK"
  else
    echo "  ⚠ WARNING: remote sync failed — local backup is intact"
  fi
fi
