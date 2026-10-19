#!/usr/bin/env bash
# =============================================================================
#  restore_db.sh - Restore PostgreSQL from pg_dump backup
#
#  Usage:
#    ./scripts/restore_db.sh backups/db_20260324_120000.pgdump
#    ./scripts/restore_db.sh backups/db_20260324_120000.pgdump --yes
#
#  This script validates the DB-only restore contract only. It does NOT validate
#  service startup, runtime configuration, or S3/object storage recovery.
#
#  Requirements: pg_restore, psql
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
warn() { log "WARNING: $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

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

  for candidate in "$BACKEND_DIR/.env.${app_env}" "$BACKEND_DIR/.env"; do
    if value="$(read_env_value "$key" "$candidate")"; then
      printf '%s\n' "$value"
      return 0
    fi
  done

  return 1
}

resolve_manifest_file() {
  local backup_file="$1"
  local manifest_new="${backup_file%.pgdump}.json"
  local backup_name backup_dir backup_timestamp manifest_legacy

  if [[ -f "$manifest_new" ]]; then
    printf '%s\n' "$manifest_new"
    return 0
  fi

  backup_name="$(basename "$backup_file")"
  backup_dir="$(dirname "$backup_file")"
  if [[ "$backup_name" =~ ^db_([0-9]{8}_[0-9]{6})\.pgdump$ ]]; then
    backup_timestamp="${BASH_REMATCH[1]}"
    manifest_legacy="${backup_dir}/manifest_${backup_timestamp}.json"
    if [[ -f "$manifest_legacy" ]]; then
      warn "Using deprecated legacy manifest name '$(basename "$manifest_legacy")'. Rename it to '$(basename "$manifest_new")'."
      printf '%s\n' "$manifest_legacy"
      return 0
    fi
  fi

  return 1
}

detect_expected_head() {
  local versions_dir="$1"
  local revisions_file down_revisions_file
  local -a heads=()

  [[ -d "$versions_dir" ]] || die "Alembic versions directory not found: $versions_dir"

  revisions_file="$(mktemp)"
  down_revisions_file="$(mktemp)"
  grep -rh '^revision = ' "$versions_dir" | grep -oE '"[^"]+"' | tr -d '"' | sort -u > "$revisions_file"
  grep -rh '^down_revision = ' "$versions_dir" | grep -oE '"[^"]+"' | tr -d '"' | sort -u > "$down_revisions_file" || true
  mapfile -t heads < <(comm -23 "$revisions_file" "$down_revisions_file")
  rm -f "$revisions_file" "$down_revisions_file"

  if [[ ${#heads[@]} -ne 1 || -z "${heads[0]}" ]]; then
    die "Unable to determine a single Alembic HEAD from $versions_dir"
  fi

  printf '%s\n' "${heads[0]}"
}

manifest_has_non_null_string() {
  local key="$1"
  local manifest_file="$2"
  grep -Eq "\"${key}\"[[:space:]]*:[[:space:]]*\"[^\"]+\"" "$manifest_file"
}

manifest_has_bool_true() {
  local key="$1"
  local manifest_file="$2"
  grep -Eq "\"${key}\"[[:space:]]*:[[:space:]]*true" "$manifest_file"
}

extract_manifest_string_value() {
  local key="$1"
  local manifest_file="$2"

  sed -nE "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"([^\"]+)\".*/\1/p" "$manifest_file" | head -1
}

S3_PROTECTION_PREREQ_STATUS="NOT EXECUTED"
S3_PROTECTION_PREREQ_REASON="not required for this restore flow"
S3_PRE_RESTORE_VALIDATION_STATUS="NOT EXECUTED"
S3_PRE_RESTORE_VALIDATION_REASON="not required for this restore flow"
S3_VARIANT_A_READINESS_STATUS="NOT EXECUTED"
S3_VARIANT_A_READINESS_REASON="not required for this restore flow"

validate_s3_pre_restore_guards() {
  local manifest_file="$1"
  local app_env bucket_manifest region_manifest runtime_bucket runtime_region
  local effective_bucket effective_region access_key secret_key profile
  local versioning_output head_bucket_output list_objects_output list_versions_output

  S3_PROTECTION_PREREQ_STATUS="FAILED"
  S3_PROTECTION_PREREQ_REASON=""
  S3_PRE_RESTORE_VALIDATION_STATUS="NOT EXECUTED"
  S3_PRE_RESTORE_VALIDATION_REASON="prerequisites did not complete"
  S3_VARIANT_A_READINESS_STATUS="FAILED"
  S3_VARIANT_A_READINESS_REASON="future Variant A checks are not ready"

  app_env="$(extract_manifest_string_value "app_env" "$manifest_file")"
  [[ -n "$app_env" ]] || app_env="${APP_ENV:-production}"

  bucket_manifest="$(extract_manifest_string_value "s3_bucket" "$manifest_file")"
  region_manifest="$(extract_manifest_string_value "s3_region" "$manifest_file")"

  if runtime_bucket="$(read_runtime_or_env_value S3_BUCKET "$app_env")"; then :; else runtime_bucket=""; fi
  if runtime_region="$(read_runtime_or_env_value S3_REGION "$app_env")"; then :; else runtime_region=""; fi
  if access_key="$(read_runtime_or_env_value AWS_ACCESS_KEY_ID "$app_env")"; then :; else access_key=""; fi
  if secret_key="$(read_runtime_or_env_value AWS_SECRET_ACCESS_KEY "$app_env")"; then :; else secret_key=""; fi
  if profile="$(read_runtime_or_env_value AWS_PROFILE "$app_env")"; then :; else profile=""; fi

  effective_bucket="${bucket_manifest:-$runtime_bucket}"
  effective_region="${region_manifest:-$runtime_region}"

  if [[ -n "$bucket_manifest" && -n "$runtime_bucket" && "$bucket_manifest" != "$runtime_bucket" ]]; then
    S3_PROTECTION_PREREQ_REASON="manifest s3_bucket '$bucket_manifest' does not match configured S3_BUCKET '$runtime_bucket'"
    die "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if [[ -n "$region_manifest" && -n "$runtime_region" && "$region_manifest" != "$runtime_region" ]]; then
    S3_PROTECTION_PREREQ_REASON="manifest s3_region '$region_manifest' does not match configured S3_REGION '$runtime_region'"
    die "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if [[ -z "$effective_bucket" ]]; then
    S3_PROTECTION_PREREQ_REASON="bucket name is missing from both manifest metadata and runtime configuration"
    die "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if [[ -z "$effective_region" ]]; then
    S3_PROTECTION_PREREQ_REASON="region is missing from both manifest metadata and runtime configuration"
    die "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if [[ -z "$profile" && ( -z "$access_key" || -z "$secret_key" ) ]]; then
    S3_PROTECTION_PREREQ_REASON="AWS credentials are not configured; set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or AWS_PROFILE"
    die "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if ! command -v aws >/dev/null 2>&1; then
    S3_PROTECTION_PREREQ_REASON="aws CLI is required for production+s3 pre-restore validation but is not installed"
    die "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if ! versioning_output="$(aws s3api get-bucket-versioning --bucket "$effective_bucket" --region "$effective_region" 2>&1)"; then
    S3_PROTECTION_PREREQ_REASON="could not query bucket versioning for '$effective_bucket' in region '$effective_region': $versioning_output"
    die "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if ! grep -Eq '"Status"[[:space:]]*:[[:space:]]*"Enabled"' <<<"$versioning_output"; then
    S3_PROTECTION_PREREQ_REASON="bucket versioning is not enabled for '$effective_bucket' in region '$effective_region'"
    die "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi

  S3_PROTECTION_PREREQ_STATUS="PASSED"
  S3_PROTECTION_PREREQ_REASON="bucket, region, credentials, aws CLI, and versioning requirement validated"
  S3_PRE_RESTORE_VALIDATION_STATUS="FAILED"

  if ! head_bucket_output="$(aws s3api head-bucket --bucket "$effective_bucket" --region "$effective_region" 2>&1)"; then
    S3_PRE_RESTORE_VALIDATION_REASON="bucket '$effective_bucket' is not reachable with the current configuration: $head_bucket_output"
    die "S3 pre-restore validation FAILED: $S3_PRE_RESTORE_VALIDATION_REASON"
  fi
  if ! list_objects_output="$(aws s3api list-objects-v2 --bucket "$effective_bucket" --region "$effective_region" --max-keys 1 2>&1)"; then
    S3_PRE_RESTORE_VALIDATION_REASON="basic read/list check failed for bucket '$effective_bucket': $list_objects_output"
    die "S3 pre-restore validation FAILED: $S3_PRE_RESTORE_VALIDATION_REASON"
  fi
  if ! list_versions_output="$(aws s3api list-object-versions --bucket "$effective_bucket" --region "$effective_region" --max-keys 1 2>&1)"; then
    S3_PRE_RESTORE_VALIDATION_REASON="object/version listing check failed for bucket '$effective_bucket': $list_versions_output"
    die "S3 pre-restore validation FAILED: $S3_PRE_RESTORE_VALIDATION_REASON"
  fi

  S3_PRE_RESTORE_VALIDATION_STATUS="PASSED"
  S3_PRE_RESTORE_VALIDATION_REASON="bucket reachable, basic read/list succeeded, and object/version listing succeeded"

  if ! manifest_has_non_null_string "s3_recovery_point" "$manifest_file"; then
    S3_VARIANT_A_READINESS_REASON="manifest is missing s3_recovery_point"
  elif ! manifest_has_bool_true "storage_snapshot_consistent" "$manifest_file"; then
    S3_VARIANT_A_READINESS_REASON="manifest does not declare storage_snapshot_consistent=true"
  else
    S3_VARIANT_A_READINESS_STATUS="PASSED"
    S3_VARIANT_A_READINESS_REASON="future Variant A checks have the required storage foundation metadata"
  fi
}

validate_manifest_contract() {
  local manifest_file="$1"
  local backup_file="$2"
  local backup_scope

  grep -q '"backup_contract"'        "$manifest_file" || die "manifest missing backup_contract"
  grep -q '"backup_scope"'           "$manifest_file" || die "manifest missing backup_scope"
  grep -q '"production_dr_eligible"' "$manifest_file" || die "manifest missing production_dr_eligible"
  grep -q '"db_file"'                "$manifest_file" || die "manifest missing db_file"
  grep -q '"checksum_file"'          "$manifest_file" || die "manifest missing checksum_file"
  grep -q '"backup_version"'         "$manifest_file" || die "manifest missing backup_version"
  grep -q '"backup_contract"[[:space:]]*:[[:space:]]*"db-restore-v1"' "$manifest_file" \
    || die "unsupported manifest backup_contract"
  backup_scope="$(extract_manifest_string_value "backup_scope" "$manifest_file")"
  [[ "$backup_scope" == "db-only" ]] \
    || die "manifest backup_scope '$backup_scope' requires the orchestrated restore flow in ops/restore.sh"
  grep -q '"production_dr_eligible"[[:space:]]*:[[:space:]]*false' "$manifest_file" \
    || die "manifest production_dr_eligible must be false for this DB-only restore flow"
  grep -q "\"db_file\"[[:space:]]*:[[:space:]]*\"$(basename "$backup_file")\"" "$manifest_file" \
    || die "manifest db_file does not match backup artifact"
  grep -q "\"checksum_file\"[[:space:]]*:[[:space:]]*\"$(basename "${backup_file}.sha256")\"" "$manifest_file" \
    || die "manifest checksum_file does not match backup artifact"
  if grep -q '"dr_contract"' "$manifest_file"; then
    grep -q '"dr_contract"[[:space:]]*:[[:space:]]*"variant-a-foundation-v1"' "$manifest_file" \
      || die "unsupported manifest dr_contract"
  fi
  if grep -q '"dr_recovery_point_model"' "$manifest_file"; then
    grep -q '"dr_recovery_point_model"[[:space:]]*:[[:space:]]*"db-artifact-paired-with-explicit-s3-recovery-point"' "$manifest_file" \
      || die "unsupported manifest dr_recovery_point_model"
  fi
  if ! grep -q '"storage_backend"[[:space:]]*:[[:space:]]*"s3"' "$manifest_file"; then
    if manifest_has_non_null_string "s3_bucket" "$manifest_file" \
      || manifest_has_non_null_string "s3_region" "$manifest_file" \
      || manifest_has_non_null_string "s3_recovery_point" "$manifest_file" \
      || manifest_has_bool_true "storage_snapshot_consistent" "$manifest_file"; then
      die "manifest declares S3 DR metadata without storage_backend=s3"
    fi
  fi
  if manifest_has_bool_true "storage_snapshot_consistent" "$manifest_file"; then
    grep -q '"storage_backend"[[:space:]]*:[[:space:]]*"s3"' "$manifest_file" \
      || die "storage_snapshot_consistent=true requires storage_backend=s3"
    manifest_has_non_null_string "s3_bucket" "$manifest_file" \
      || die "storage_snapshot_consistent=true requires s3_bucket"
    manifest_has_non_null_string "s3_region" "$manifest_file" \
      || die "storage_snapshot_consistent=true requires s3_region"
    manifest_has_non_null_string "s3_recovery_point" "$manifest_file" \
      || die "storage_snapshot_consistent=true requires s3_recovery_point"
  fi

  if grep -q '"app_env"[[:space:]]*:[[:space:]]*"production"' "$manifest_file" \
    && grep -q '"storage_backend"[[:space:]]*:[[:space:]]*"s3"' "$manifest_file"; then
    if grep -q '"storage_archive_included"[[:space:]]*:[[:space:]]*true' "$manifest_file"; then
      die "manifest claims storage archive coverage for production+s3 backup; this DB-only restore flow refuses ambiguous production media claims"
    fi
    if grep -q '"storage_coverage"' "$manifest_file" \
      && ! grep -q '"storage_coverage"[[:space:]]*:[[:space:]]*"authoritative-s3-not-covered-by-this-backup"' "$manifest_file"; then
      die "manifest storage_coverage is inconsistent with production+s3 DB-only semantics"
    fi
    warn "Manifest declares APP_ENV=production with STORAGE_BACKEND=s3."
    warn "This restore validates database state only. Authoritative S3/object storage remains out of scope."
    if grep -q '"dr_contract"[[:space:]]*:[[:space:]]*"variant-a-foundation-v1"' "$manifest_file"; then
      if manifest_has_non_null_string "s3_bucket" "$manifest_file" \
        && manifest_has_non_null_string "s3_region" "$manifest_file" \
        && manifest_has_non_null_string "s3_recovery_point" "$manifest_file" \
        && manifest_has_bool_true "storage_snapshot_consistent" "$manifest_file"; then
        warn "Variant A foundation metadata is present, but this script does not restore S3/object storage or prove recovered media state."
      else
        warn "Variant A foundation contract is present, but required S3 recovery point metadata is incomplete."
      fi
    fi
  fi
}

load_env() {
  local env_file="$BACKEND_DIR/.env"
  [[ -f "$env_file" ]] && set -a && source "$env_file" && set +a
  local app_env="${APP_ENV:-}"
  if [[ -n "$app_env" ]]; then
    local override="$BACKEND_DIR/.env.$app_env"
    [[ -f "$override" ]] && set -a && source "$override" && set +a
  fi
}

BACKUP_FILE="${1:-}"
AUTO_YES="${2:-}"

if [[ -z "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <backup_file.pgdump> [--yes]"
  exit 1
fi
[[ -f "$BACKUP_FILE" ]] || die "backup file not found: $BACKUP_FILE"

MANIFEST_FILE="$(resolve_manifest_file "$BACKUP_FILE")" \
  || die "manifest file missing for $(basename "$BACKUP_FILE")"
validate_manifest_contract "$MANIFEST_FILE" "$BACKUP_FILE"
log "Manifest OK: $(basename "$MANIFEST_FILE")"

load_env
EXPECTED_HEAD="$(detect_expected_head "$BACKEND_DIR/alembic/versions")"
log "Expected Alembic HEAD: $EXPECTED_HEAD"
if grep -q '"app_env"[[:space:]]*:[[:space:]]*"production"' "$MANIFEST_FILE" \
  && grep -q '"storage_backend"[[:space:]]*:[[:space:]]*"s3"' "$MANIFEST_FILE"; then
  validate_s3_pre_restore_guards "$MANIFEST_FILE"
  log "S3 protection prerequisites: $S3_PROTECTION_PREREQ_STATUS"
  log "S3 pre-restore validation: $S3_PRE_RESTORE_VALIDATION_STATUS"
  if [[ "$S3_VARIANT_A_READINESS_STATUS" == "PASSED" ]]; then
    log "Variant A storage-readiness: PASSED"
  else
    warn "Variant A storage-readiness: FAILED (${S3_VARIANT_A_READINESS_REASON})"
  fi
fi

DB_URL="${DATABASE_URL_SYNC:-${DATABASE_URL:-}}"
[[ -n "$DB_URL" ]] || die "DATABASE_URL or DATABASE_URL_SYNC not set in .env"
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

CHECKSUM_FILE="${BACKUP_FILE}.sha256"
[[ -f "$CHECKSUM_FILE" ]] || die "checksum file missing for restore contract: $CHECKSUM_FILE"
log "Verifying checksum ..."
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum --check "$CHECKSUM_FILE"
else
  openssl dgst -sha256 "$BACKUP_FILE" | diff - "$CHECKSUM_FILE"
fi
log "Checksum OK"

echo ""
echo "WARNING: this will DROP and RECREATE the database '$DB_NAME' on $DB_HOST:$DB_PORT"
echo "All existing data will be permanently deleted."
echo ""
if [[ "$AUTO_YES" != "--yes" ]]; then
  read -r -p "Type 'yes' to continue: " CONFIRM
  [[ "$CONFIRM" == "yes" ]] || { echo "Aborted."; exit 0; }
fi

log "Dropping database '$DB_NAME' ..."
psql "${PG_CONN[@]}" --dbname=postgres \
  --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();" \
  --quiet
psql "${PG_CONN[@]}" --dbname=postgres \
  --command="DROP DATABASE IF EXISTS \"$DB_NAME\";" \
  --quiet
psql "${PG_CONN[@]}" --dbname=postgres \
  --command="CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";" \
  --quiet
log "Database recreated"

log "Restoring $(basename "$BACKUP_FILE") ..."
set +e
pg_restore \
  "${PG_CONN[@]}" \
  --dbname="$DB_NAME" \
  --no-password \
  --jobs=4 \
  --verbose \
  "$BACKUP_FILE" 2>&1 | grep -v "^pg_restore: creating\|^pg_restore: executing"
RESTORE_PIPE_STATUS=${PIPESTATUS[0]}
set -e
[[ $RESTORE_PIPE_STATUS -eq 0 ]] || die "pg_restore failed with exit code $RESTORE_PIPE_STATUS"
log "DB data restore applied"

check_table() {
  local tbl="$1"
  local exists
  exists=$(psql "${PG_CONN[@]}" --dbname="$DB_NAME" --tuples-only --no-align \
    --command="SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='${tbl}');" \
    2>/dev/null | tr -d ' \r\n')
  [[ "$exists" == "t" ]] || die "critical table '$tbl' is missing after restore"
  log "  table present: $tbl"
}

log "Running DB post-restore checks ..."
check_table "organizations"
check_table "users"
check_table "projects"
check_table "audit_logs"
check_table "role_permissions"

ALEMBIC_REV=$(psql "${PG_CONN[@]}" --dbname="$DB_NAME" --tuples-only --no-align \
  --command="SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d ' \r\n')
[[ -n "$ALEMBIC_REV" ]] || die "alembic_version is empty after restore"
[[ "$ALEMBIC_REV" == "$EXPECTED_HEAD" ]] || die "schema revision '$ALEMBIC_REV' does not match repository HEAD '$EXPECTED_HEAD'"
log "  schema/head alignment: $ALEMBIC_REV"

echo ""
echo "DB restore status:"
echo "  DB restore contract: PASSED"
echo "  Schema/head alignment: PASSED ($ALEMBIC_REV)"
if grep -q '"app_env"[[:space:]]*:[[:space:]]*"production"' "$MANIFEST_FILE" \
  && grep -q '"storage_backend"[[:space:]]*:[[:space:]]*"s3"' "$MANIFEST_FILE"; then
  echo "  S3 protection prerequisites: $S3_PROTECTION_PREREQ_STATUS"
  echo "  S3 pre-restore validation: $S3_PRE_RESTORE_VALIDATION_STATUS"
  echo "  Variant A storage-readiness: $S3_VARIANT_A_READINESS_STATUS"
  if [[ "$S3_VARIANT_A_READINESS_STATUS" != "PASSED" ]]; then
    echo "  Variant A storage-readiness reason: $S3_VARIANT_A_READINESS_REASON"
  fi
fi
echo "  Runtime environment: NOT VERIFIED BY THIS SCRIPT"
echo "  production_dr_eligible: false"
echo "  Full-state restore claim: NOT VERIFIED"
echo "  Production DR: NOT VERIFIED"
echo ""
echo "This validates the DB-only restore contract only."
echo "It does NOT validate service startup, runtime configuration, or S3/object storage recovery."
