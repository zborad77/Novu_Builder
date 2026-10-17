#!/usr/bin/env bash
# Novu Builder — operator backup entrypoint (R-40)
#
# Backs up:
#   1. PostgreSQL database (pg_dump custom archive -> .pgdump)   <- AUTHORITATIVE DB RESTORE INPUT
#   2. Local compatibility storage volume archive (photos, exports)   <- LOCAL/DEV ONLY
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
# Restore (DB-only contract): ./ops/restore.sh <db_TIMESTAMP.pgdump>
# Verify:  python-backend/scripts/verify_restore.sh <db_TIMESTAMP.pgdump>

set -euo pipefail

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: required command not found: $1"
    exit 1
  }
}
require_cmd rsync
require_cmd ssh
require_cmd sha256sum

die() {
  echo "ERROR: $*" >&2
  exit 1
}

warn() {
  echo "WARNING: $*" >&2
}

read_env_value() {
  local key="$1"
  local file="$2"
  local line value

  [[ -f "$file" ]] || return 1
  line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$file" | tail -1 || true)"
  [[ -n "$line" ]] || return 1

  value="${line#*=}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  if [[ "$value" =~ ^\".*\"$ ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" =~ ^\'.*\'$ ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s\n' "$value"
}

read_runtime_or_env_value() {
  local key="$1"
  local app_env="$2"
  local candidate value

  if [[ -n "${!key:-}" ]]; then
    printf '%s\n' "${!key}"
    return 0
  fi

  for candidate in ".env.${app_env}" ".env" "python-backend/.env.${app_env}" "python-backend/.env"; do
    if value="$(read_env_value "$key" "$candidate")"; then
      printf '%s\n' "$value"
      return 0
    fi
  done

  return 1
}

resolve_app_env() {
  if [[ -n "${APP_ENV:-}" ]]; then
    printf '%s\n' "$APP_ENV"
    return 0
  fi

  local candidate
  for candidate in ".env" "python-backend/.env"; do
    if candidate="$(read_env_value APP_ENV "$candidate")"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  printf '%s\n' "development"
}

resolve_storage_backend() {
  if [[ -n "${STORAGE_BACKEND:-}" ]]; then
    printf '%s\n' "$STORAGE_BACKEND"
    return 0
  fi

  local app_env="$1"
  local candidate
  for candidate in ".env.${app_env}" ".env" "python-backend/.env.${app_env}" "python-backend/.env"; do
    if candidate="$(read_env_value STORAGE_BACKEND "$candidate")"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  printf '%s\n' "local"
}

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/\\r}"
  value="${value//$'\t'/\\t}"
  printf '%s' "$value"
}

json_string_or_null() {
  local value="${1:-}"
  if [[ -z "$value" ]]; then
    printf 'null'
  else
    printf '"%s"' "$(json_escape "$value")"
  fi
}

json_bool_or_null() {
  local value="${1:-}"
  case "$value" in
    true|false)
      printf '%s' "$value"
      ;;
    "")
      printf 'null'
      ;;
    *)
      die "Expected boolean true/false for JSON field, got: $value"
      ;;
  esac
}

json_int_or_null() {
  local value="${1:-}"
  if [[ -z "$value" ]]; then
    printf 'null'
    return 0
  fi
  [[ "$value" =~ ^[0-9]+$ ]] || die "Expected integer for JSON field, got: $value"
  printf '%s' "$value"
}

resolve_database_url_for_full_state() {
  local app_env="$1"
  local candidate

  for candidate in DATABASE_URL_SYNC DATABASE_URL; do
    if value="$(read_runtime_or_env_value "$candidate" "$app_env")"; then
      printf '%s\n' "$value"
      return 0
    fi
  done

  return 1
}

BACKUP_DIR="${BACKUP_DIR:-./backups}"
POSTGRES_USER="${POSTGRES_USER:-novu}"
POSTGRES_DB="${POSTGRES_DB:-novu_builder}"
RETAIN_DAYS="${RETAIN_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_BASENAME="db_${TIMESTAMP}"
APP_ENV_CURRENT="$(resolve_app_env)"
STORAGE_BACKEND_CURRENT="$(resolve_storage_backend "$APP_ENV_CURRENT")"
S3_BUCKET_CURRENT=""
S3_REGION_CURRENT=""
S3_RECOVERY_POINT_CURRENT=""
STORAGE_SNAPSHOT_CONSISTENT_RAW=""
S3_BUCKET_JSON_VALUE="null"
S3_REGION_JSON_VALUE="null"
S3_RECOVERY_POINT_JSON_VALUE="null"
STORAGE_SNAPSHOT_CONSISTENT_JSON_VALUE="null"
VARIANT_A_FOUNDATION_MINIMUM=0
DR_CONTRACT_VERSION="variant-a-foundation-v1"
DR_RECOVERY_POINT_MODEL="db-artifact-paired-with-explicit-s3-recovery-point"
S3_FULL_COVERAGE_DECLARED="${S3_FULL_COVERAGE_DECLARED:-false}"
PRODUCTION_S3_DB_ONLY_MODE=0
INCLUDE_STORAGE_ARCHIVE=1
STORAGE_COVERAGE="local-volume-archive-compatibility-only"
STORAGE_ARCHIVE_INCLUDED=true
STORAGE_ARCHIVE_JSON_VALUE="\"storage_${TIMESTAMP}.tar.gz\""
PRODUCTION_DR_ELIGIBLE=false
BACKUP_SCOPE="db-only"
S3_MEDIA_MANIFEST_BASENAME=""
S3_MEDIA_MANIFEST_FORMAT=""
S3_MEDIA_RESTORE_STRATEGY=""
S3_OBJECT_COUNT=""
S3_MEDIA_MANIFEST_JSON_VALUE="null"
S3_MEDIA_MANIFEST_FORMAT_JSON_VALUE="null"
S3_MEDIA_RESTORE_STRATEGY_JSON_VALUE="null"
S3_OBJECT_COUNT_JSON_VALUE="null"

if [[ "$STORAGE_BACKEND_CURRENT" == "s3" ]]; then
  if value="$(read_runtime_or_env_value S3_BUCKET "$APP_ENV_CURRENT")"; then
    S3_BUCKET_CURRENT="$value"
  fi
  if value="$(read_runtime_or_env_value S3_REGION "$APP_ENV_CURRENT")"; then
    S3_REGION_CURRENT="$value"
  fi
  if value="$(read_runtime_or_env_value S3_RECOVERY_POINT "$APP_ENV_CURRENT")"; then
    S3_RECOVERY_POINT_CURRENT="$value"
  fi
  if value="$(read_runtime_or_env_value STORAGE_SNAPSHOT_CONSISTENT "$APP_ENV_CURRENT")"; then
    STORAGE_SNAPSHOT_CONSISTENT_RAW="$value"
  fi
fi

S3_BUCKET_JSON_VALUE="$(json_string_or_null "$S3_BUCKET_CURRENT")"
S3_REGION_JSON_VALUE="$(json_string_or_null "$S3_REGION_CURRENT")"
S3_RECOVERY_POINT_JSON_VALUE="$(json_string_or_null "$S3_RECOVERY_POINT_CURRENT")"
STORAGE_SNAPSHOT_CONSISTENT_JSON_VALUE="$(json_bool_or_null "$STORAGE_SNAPSHOT_CONSISTENT_RAW")"

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] Starting Novu Builder backup → $BACKUP_DIR"
echo "  -> Runtime mode: APP_ENV=${APP_ENV_CURRENT}, STORAGE_BACKEND=${STORAGE_BACKEND_CURRENT}"

if [[ "$APP_ENV_CURRENT" == "production" && "$STORAGE_BACKEND_CURRENT" == "s3" ]]; then
  PRODUCTION_S3_DB_ONLY_MODE=1
  INCLUDE_STORAGE_ARCHIVE=0
  STORAGE_COVERAGE="authoritative-s3-not-covered-by-this-backup"
  STORAGE_ARCHIVE_INCLUDED=false
  STORAGE_ARCHIVE_JSON_VALUE="null"

  warn "APP_ENV=production with STORAGE_BACKEND=s3 detected."
  if [[ "$S3_FULL_COVERAGE_DECLARED" == "true" ]]; then
    warn "Explicit full-state S3 coverage requested via S3_FULL_COVERAGE_DECLARED=true."
  else
    warn "This backup is DB-only truth. Authoritative S3/object storage is NOT covered by scripts/backup.sh."
    warn "Do not treat this backup as full production disaster recovery."
  fi
fi

if [[ "$STORAGE_BACKEND_CURRENT" == "s3" ]]; then
  if [[ -n "$S3_BUCKET_CURRENT" && -n "$S3_REGION_CURRENT" && -n "$S3_RECOVERY_POINT_CURRENT" && "$STORAGE_SNAPSHOT_CONSISTENT_RAW" == "true" ]]; then
    VARIANT_A_FOUNDATION_MINIMUM=1
  fi
fi

# ── 1. PostgreSQL dump (custom archive format) ────────────────────────────────
# Authoritative DB backup format: .pgdump (pg_dump custom archive)
# Restores via: ops/restore.sh or python-backend/scripts/restore_db.sh
DB_FILE="$BACKUP_DIR/${BACKUP_BASENAME}.pgdump"
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

# ── Metadata for deterministic DB restore contract ────────────────────────────
# Authoritative write contract:
#   db_TIMESTAMP.pgdump
#   db_TIMESTAMP.pgdump.sha256
#   db_TIMESTAMP.json
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
[ "$(wc -c < "$DB_FILE")" -gt 1024 ] || { echo "ERROR: DB dump too small (<1KB) — may be corrupt"; exit 1; }

# ── 2. File storage archive ───────────────────────────────────────────────────
# Uses a temporary alpine container to tar the named volume directly,
# avoiding any dependency on the backend container being stopped.
# In production+s3 this archive is skipped completely to avoid implying that
# local compatibility volume data represents authoritative production media.
STORAGE_FILE="$BACKUP_DIR/storage_${TIMESTAMP}.tar.gz"
if [[ $INCLUDE_STORAGE_ARCHIVE -eq 1 ]]; then
  echo "  → Storage archive (local compatibility only): $STORAGE_FILE"
  docker run --rm \
    -v novu_builder_storage_data:/data \
    alpine \
    tar czf - /data \
    > "$STORAGE_FILE"
else
  echo "  → Storage archive: skipped (production+s3 DB-only mode; authoritative S3/object storage not covered)"
fi

if [[ "$APP_ENV_CURRENT" == "production" && "$STORAGE_BACKEND_CURRENT" == "s3" && "$S3_FULL_COVERAGE_DECLARED" == "true" ]]; then
  [[ $VARIANT_A_FOUNDATION_MINIMUM -eq 1 ]] || die "Full-state S3 coverage requires S3_BUCKET, S3_REGION, S3_RECOVERY_POINT, and STORAGE_SNAPSHOT_CONSISTENT=true."
  require_cmd python

  DATABASE_URL_FOR_FULL_STATE="$(resolve_database_url_for_full_state "$APP_ENV_CURRENT")" \
    || die "Full-state S3 coverage requires DATABASE_URL_SYNC or DATABASE_URL."
  MEDIA_EXPORT_HELPER="${S3_MEDIA_EXPORT_HELPER_OVERRIDE:-python-backend/scripts/export_s3_recovery_manifest.py}"
  [[ -f "$MEDIA_EXPORT_HELPER" ]] || die "S3 media export helper not found: $MEDIA_EXPORT_HELPER"

  S3_MEDIA_MANIFEST_FILE="$BACKUP_DIR/${BACKUP_BASENAME}.s3-media.json"
  echo "  → S3 media manifest: $S3_MEDIA_MANIFEST_FILE"
  python "$MEDIA_EXPORT_HELPER" \
    --database-url "$DATABASE_URL_FOR_FULL_STATE" \
    --output "$S3_MEDIA_MANIFEST_FILE" \
    --bucket "$S3_BUCKET_CURRENT" \
    --region "$S3_REGION_CURRENT" \
    --declared-recovery-point "$S3_RECOVERY_POINT_CURRENT" \
    --db-backup-file "${BACKUP_BASENAME}.pgdump" \
    --db-manifest-file "${BACKUP_BASENAME}.json" \
    >/dev/null

  [[ -s "$S3_MEDIA_MANIFEST_FILE" ]] || die "S3 media manifest was not created or is empty."

  S3_MEDIA_MANIFEST_BASENAME="$(basename "$S3_MEDIA_MANIFEST_FILE")"
  S3_MEDIA_MANIFEST_FORMAT="$(python -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8')).get('format',''))" "$S3_MEDIA_MANIFEST_FILE")"
  S3_OBJECT_COUNT="$(python -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8')).get('unique_object_count',''))" "$S3_MEDIA_MANIFEST_FILE")"
  [[ "$S3_MEDIA_MANIFEST_FORMAT" == "novu-s3-media-manifest-v1" ]] || die "Unexpected S3 media manifest format: $S3_MEDIA_MANIFEST_FORMAT"
  [[ "$S3_OBJECT_COUNT" =~ ^[0-9]+$ ]] || die "S3 media manifest did not report a valid unique_object_count."

  PRODUCTION_S3_DB_ONLY_MODE=0
  BACKUP_SCOPE="db-plus-s3-media-manifest"
  PRODUCTION_DR_ELIGIBLE=true
  STORAGE_COVERAGE="authoritative-s3-media-manifest"
  DR_CONTRACT_VERSION="s3-full-state-v1"
  DR_RECOVERY_POINT_MODEL="db-artifact-paired-with-versioned-s3-object-manifest"
  S3_MEDIA_RESTORE_STRATEGY="versioned-copy-to-isolated-bucket-v1"
  S3_MEDIA_MANIFEST_JSON_VALUE="$(json_string_or_null "$S3_MEDIA_MANIFEST_BASENAME")"
  S3_MEDIA_MANIFEST_FORMAT_JSON_VALUE="$(json_string_or_null "$S3_MEDIA_MANIFEST_FORMAT")"
  S3_MEDIA_RESTORE_STRATEGY_JSON_VALUE="$(json_string_or_null "$S3_MEDIA_RESTORE_STRATEGY")"
  S3_OBJECT_COUNT_JSON_VALUE="$(json_int_or_null "$S3_OBJECT_COUNT")"
fi

# KROK 4: atomic manifest write (temp → mv prevents partial manifest on crash)
MANIFEST_FILE="$BACKUP_DIR/${BACKUP_BASENAME}.json"
MANIFEST_TMP="${MANIFEST_FILE}.tmp"
trap 'rm -f "$MANIFEST_TMP"' EXIT
# ── production_dr_eligible gating conditions ──────────────────────────────────
# production_dr_eligible=true requires ALL of the following conditions.
# DB-only manifests never satisfy them and stay false.
# Full-state S3 manifests may declare true only when they carry a paired,
# version-pinned media manifest for the same DB-backed reference set.
# ops/restore.sh is the authoritative gate that decides whether the claim
# remains truthful after isolated media restore and validation.
#
# Required conditions (none currently implemented):
#   (1) backup set validation PASSED
#   (2) DB restore PASSED
#   (3) schema/head alignment PASSED
#   (4) S3 protection prerequisites PASSED
#   (5) S3 pre-restore validation PASSED
#   (6) post-restore validation PASSED
#   (7) DB-referenced objects validation PASSED
#   (8) signed URL / storage access path validation PASSED
#   (9) application media smoke validation PASSED
#   (10) media restore step PASSED
#   (11) media validation step PASSED
#   (12) no blocker consistency failure proven via an explicit consistency gate
#
# DB-only manifests always keep production_dr_eligible=false. Full-state S3
# manifests may set production_dr_eligible=true only when they include a
# version-pinned media manifest generated from the same DB-backed reference set.
cat > "$MANIFEST_TMP" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "app_env": "${APP_ENV_CURRENT}",
  "backup_contract": "db-restore-v1",
  "dr_contract": "${DR_CONTRACT_VERSION}",
  "dr_recovery_point_model": "${DR_RECOVERY_POINT_MODEL}",
  "backup_scope": "${BACKUP_SCOPE}",
  "production_dr_eligible": ${PRODUCTION_DR_ELIGIBLE},
  "storage_backend": "${STORAGE_BACKEND_CURRENT}",
  "s3_bucket": ${S3_BUCKET_JSON_VALUE},
  "s3_region": ${S3_REGION_JSON_VALUE},
  "s3_recovery_point": ${S3_RECOVERY_POINT_JSON_VALUE},
  "storage_snapshot_consistent": ${STORAGE_SNAPSHOT_CONSISTENT_JSON_VALUE},
  "storage_coverage": "${STORAGE_COVERAGE}",
  "s3_media_manifest_file": ${S3_MEDIA_MANIFEST_JSON_VALUE},
  "s3_media_manifest_format": ${S3_MEDIA_MANIFEST_FORMAT_JSON_VALUE},
  "s3_media_restore_strategy": ${S3_MEDIA_RESTORE_STRATEGY_JSON_VALUE},
  "s3_object_count": ${S3_OBJECT_COUNT_JSON_VALUE},
  "storage_archive_included": ${STORAGE_ARCHIVE_INCLUDED},
  "storage_archive_file": ${STORAGE_ARCHIVE_JSON_VALUE},
  "db_file": "${BACKUP_BASENAME}.pgdump",
  "checksum_file": "${BACKUP_BASENAME}.pgdump.sha256",
  "alembic_head": "${ALEMBIC_HEAD}",
  "git_sha": "${GIT_SHA}",
  "backup_version": "v4"
}
EOF
mv "$MANIFEST_TMP" "$MANIFEST_FILE"
trap - EXIT
echo "  → Manifest: $MANIFEST_FILE"

# ── 3. Prune old backups ──────────────────────────────────────────────────────
echo "  → Pruning backups older than ${RETAIN_DAYS} days"
find "$BACKUP_DIR" -maxdepth 1 -name "db_*.pgdump"        -mtime +"$RETAIN_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -name "db_*.pgdump.sha256" -mtime +"$RETAIN_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -name "db_*.json"          -mtime +"$RETAIN_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -name "manifest_*.json"    -mtime +"$RETAIN_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -name "storage_*.tar.gz"   -mtime +"$RETAIN_DAYS" -delete

echo "[$(date -Iseconds)] Backup complete."
echo "  DB:      $DB_FILE  ($(du -sh "$DB_FILE" | cut -f1))"
echo "  production_dr_eligible: ${PRODUCTION_DR_ELIGIBLE}"
if [[ $INCLUDE_STORAGE_ARCHIVE -eq 1 ]]; then
  echo "  Storage: $STORAGE_FILE  ($(du -sh "$STORAGE_FILE" | cut -f1))"
  echo "  Meaning: DB restore contract + local compatibility storage archive only"
  echo "  Production DR claim: NOT eligible"
elif [[ "$PRODUCTION_DR_ELIGIBLE" == "true" ]]; then
  echo "  Storage: $S3_MEDIA_MANIFEST_FILE"
  echo "  Meaning: DB backup paired with version-pinned S3 media manifest (${S3_OBJECT_COUNT} objects)"
  echo "  Production DR claim: eligible only after isolated media restore + validation succeeds"
else
  echo "  Storage: skipped"
  echo "  Meaning: DB-only backup; authoritative S3/object storage is NOT covered"
  if [[ $VARIANT_A_FOUNDATION_MINIMUM -eq 1 ]]; then
    echo "  Variant A foundation: explicit S3 recovery point metadata recorded for later pairing"
    echo "  Recovery point model: DB artifact + declared S3 recovery point only"
  else
    echo "  Variant A foundation: incomplete; required S3 recovery point metadata is not fully declared"
  fi
  echo "  Production DR claim: NOT eligible"
fi

# ── 4. Off-site sync (optional) ───────────────────────────────────────────────
# Set BACKUP_REMOTE to enable: e.g. BACKUP_REMOTE=user@host:/remote/backups
# Failure does NOT affect the exit status of the local backup.
if [[ -n "${BACKUP_REMOTE:-}" ]]; then
  echo "[$(date -Iseconds)] Syncing DB artifact set to remote: $BACKUP_REMOTE"
  SYNC_FILES=( "$DB_FILE" "${DB_FILE}.sha256" )
  [[ -f "$MANIFEST_FILE" ]] && SYNC_FILES+=( "$MANIFEST_FILE" )
  echo "Sync files:"
  echo "${SYNC_FILES[@]}"
  echo "Destination: $BACKUP_REMOTE/$TIMESTAMP"
  [ -z "${BACKUP_REMOTE:-}" ] && { echo "ERROR: BACKUP_REMOTE not set"; exit 1; }
  BACKUP_REMOTE_PATH="${BACKUP_REMOTE_PATH:-}"
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$BACKUP_REMOTE" "mkdir -p ${BACKUP_REMOTE_PATH}/$TIMESTAMP" || {
    echo "WARNING: failed to create remote directory"
  }
  if timeout 60 rsync -az \
    -e "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10" \
    "${SYNC_FILES[@]}" "$BACKUP_REMOTE/$TIMESTAMP/"; then
    echo "  → Remote sync OK"
  else
    echo "  ⚠ WARNING: remote sync failed — local backup is intact"
  fi
fi
