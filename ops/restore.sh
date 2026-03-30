#!/usr/bin/env bash
# =============================================================================
#  ops/restore.sh — Restore PostgreSQL from .pgdump backup (Docker Compose)
#
#  AUTHORITATIVE DB-only restore path for backups produced by scripts/backup.sh.
#
#  Usage:
#    ./ops/restore.sh <db_backup.pgdump>                    # interactive; verify runs first
#    ./ops/restore.sh <db_backup.pgdump> --yes              # unattended (CI / recovery)
#    ./ops/restore.sh <db_backup.pgdump> --skip-verify      # bypass verify (explicit)
#    ./ops/restore.sh <db_backup.pgdump> --yes --skip-verify
#
#  This script works with backups produced by:
#    scripts/backup.sh   → db_TIMESTAMP.pgdump + db_TIMESTAMP.pgdump.sha256 + db_TIMESTAMP.json
#                        (AUTHORITATIVE DB restore contract)
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
#    9. Polls liveness endpoint
#
#  verify_restore.sh requires: psql, pg_restore on host + DATABASE_URL in
#  python-backend/.env. Use --skip-verify if these are not available.
#
#  Requirements: docker compose, curl
#  Run from: project root (next to docker-compose.yml)
# =============================================================================
set -euo pipefail

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: required command not found: $1"
    exit 1
  }
}
require_cmd sha256sum
require_cmd timeout

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
warn() { log "WARNING: $*"; }

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
      warn "Using deprecated legacy manifest name '$(basename "$manifest_legacy")'. Rename it to '$(basename "$manifest_new")'." >&2
      printf '%s\n' "$manifest_legacy"
      return 0
    fi
  fi

  die "Manifest file not found. Expected: $manifest_new"
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
DB_RESTORE_STATUS="NOT EXECUTED"
DB_RESTORE_REASON="restore pipeline has not completed"
PRODUCTION_DR_STATUS="NOT VERIFIED"
PRODUCTION_DR_REASON="this restore flow does not verify full production disaster recovery"
PREVERIFY_STATUS="NOT EXECUTED"
VERIFY_DB_QUERY_USABILITY_STATUS="NOT EXECUTED"
VERIFY_DB_QUERY_USABILITY_REASON="pre-restore verify has not reported DB query usability"
VERIFY_SCHEMA_HEAD_ALIGNMENT_STATUS="NOT EXECUTED"
VERIFY_SCHEMA_HEAD_ALIGNMENT_REASON="pre-restore verify has not reported schema/head alignment"
VERIFY_REFERENCE_SAMPLE_VALIDATION_STATUS="NOT EXECUTED"
VERIFY_REFERENCE_SAMPLE_VALIDATION_REASON="pre-restore verify has not reported DB-to-storage sample validation"
VERIFY_SIGNED_URL_VALIDATION_STATUS="NOT EXECUTED"
VERIFY_SIGNED_URL_VALIDATION_REASON="pre-restore verify has not reported signed URL/access path validation"
VERIFY_APP_MEDIA_SMOKE_STATUS="NOT EXECUTED"
VERIFY_APP_MEDIA_SMOKE_REASON="pre-restore verify has not reported application media smoke validation"
FINAL_SUMMARY_PRINTED=0

step_label() {
  case "$1" in
    MAINTENANCE_INTENT) echo "1. Maintenance mode / write stop intent" ;;
    BACKUP_SET_VALIDATION) echo "2. Backup set validation" ;;
    S3_PROTECTION_PREREQUISITES) echo "3. S3 prerequisites validation" ;;
    S3_PRE_RESTORE_VALIDATION) echo "4. S3 pre-restore validation" ;;
    MEDIA_RESTORE) echo "5. Media restore step" ;;
    MEDIA_VALIDATION) echo "6. Media validation step" ;;
    DB_RESTORE) echo "7. DB restore" ;;
    SCHEMA_HEAD_VALIDATION) echo "8. Schema/head validation" ;;
    BACKEND_HANDOFF_READINESS) echo "9. Backend liveness / handoff readiness" ;;
    POST_RESTORE_VALIDATION) echo "10. Post-restore validation" ;;
    RELEASE_READINESS_DECISION) echo "11. Release readiness decision" ;;
    *) echo "$1" ;;
  esac
}

set_step_status() {
  local key="$1"
  local status="$2"
  local detail="${3:-}"
  printf -v "STEP_${key}_STATUS" '%s' "$status"
  printf -v "STEP_${key}_DETAIL" '%s' "$detail"
}

get_step_status() {
  local key="$1"
  local var="STEP_${key}_STATUS"
  printf '%s' "${!var:-NOT EXECUTED}"
}

get_step_detail() {
  local key="$1"
  local var="STEP_${key}_DETAIL"
  printf '%s' "${!var:-}"
}

capture_verify_step_status() {
  local step_name="$1"
  local status="$2"
  local detail="$3"

  case "$step_name" in
    db_query_usability)
      VERIFY_DB_QUERY_USABILITY_STATUS="$status"
      VERIFY_DB_QUERY_USABILITY_REASON="$detail"
      ;;
    schema_head_alignment)
      VERIFY_SCHEMA_HEAD_ALIGNMENT_STATUS="$status"
      VERIFY_SCHEMA_HEAD_ALIGNMENT_REASON="$detail"
      ;;
    reference_sample_validation)
      VERIFY_REFERENCE_SAMPLE_VALIDATION_STATUS="$status"
      VERIFY_REFERENCE_SAMPLE_VALIDATION_REASON="$detail"
      ;;
    signed_url_validation)
      VERIFY_SIGNED_URL_VALIDATION_STATUS="$status"
      VERIFY_SIGNED_URL_VALIDATION_REASON="$detail"
      ;;
    app_media_smoke)
      VERIFY_APP_MEDIA_SMOKE_STATUS="$status"
      VERIFY_APP_MEDIA_SMOKE_REASON="$detail"
      ;;
  esac
}

capture_verify_validation_output() {
  local output="$1"
  local line step_name status detail

  while IFS= read -r line; do
    [[ "$line" == POST_RESTORE_VALIDATION_STEP\|* ]] || continue
    IFS='|' read -r _prefix step_name status detail <<< "$line"
    capture_verify_step_status "$step_name" "$status" "$detail"
  done <<< "$output"
}

init_restore_steps() {
  set_step_status MAINTENANCE_INTENT "NOT EXECUTED" "write-stop intent has not been recorded"
  set_step_status BACKUP_SET_VALIDATION "NOT EXECUTED" "backup artifact checks have not started"
  set_step_status S3_PROTECTION_PREREQUISITES "NOT EXECUTED" "not required unless manifest declares production+s3"
  set_step_status S3_PRE_RESTORE_VALIDATION "NOT EXECUTED" "not required unless manifest declares production+s3"
  set_step_status MEDIA_RESTORE "NOT EXECUTED" "DB-only contract path does not include media restore"
  set_step_status MEDIA_VALIDATION "NOT EXECUTED" "DB-only contract path does not include media validation"
  set_step_status DB_RESTORE "NOT EXECUTED" "database restore has not started"
  set_step_status SCHEMA_HEAD_VALIDATION "NOT EXECUTED" "schema/head validation has not started"
  set_step_status BACKEND_HANDOFF_READINESS "NOT EXECUTED" "backend liveness has not been checked"
  set_step_status POST_RESTORE_VALIDATION "NOT EXECUTED" "post-restore validation has not completed"
  set_step_status RELEASE_READINESS_DECISION "NOT EXECUTED" "release readiness has not been decided"
}

emit_final_summary() {
  local detail status step

  if [[ "${FINAL_SUMMARY_PRINTED:-0}" -eq 1 ]]; then
    return 0
  fi
  FINAL_SUMMARY_PRINTED=1

  echo ""
  echo "=================================================="
  echo "Restore orchestration status"
  echo "=================================================="
  echo ""
  echo "  Backup-set verify: $PREVERIFY_STATUS"
  echo "  DB restore status: $DB_RESTORE_STATUS"
  echo "  DB restore detail: $DB_RESTORE_REASON"
  echo "  Production DR status: $PRODUCTION_DR_STATUS"
  echo "  Production DR detail: $PRODUCTION_DR_REASON"
  echo ""
  for step in \
    MAINTENANCE_INTENT \
    BACKUP_SET_VALIDATION \
    S3_PROTECTION_PREREQUISITES \
    S3_PRE_RESTORE_VALIDATION \
    MEDIA_RESTORE \
    MEDIA_VALIDATION \
    DB_RESTORE \
    SCHEMA_HEAD_VALIDATION \
    BACKEND_HANDOFF_READINESS \
    POST_RESTORE_VALIDATION \
    RELEASE_READINESS_DECISION; do
    status="$(get_step_status "$step")"
    detail="$(get_step_detail "$step")"
    echo "  $(step_label "$step"): $status"
    if [[ -n "$detail" ]]; then
      echo "     $detail"
    fi
  done
  echo "  Verified DB query usability: $VERIFY_DB_QUERY_USABILITY_STATUS"
  echo "     $VERIFY_DB_QUERY_USABILITY_REASON"
  echo "  Verified schema/head alignment: $VERIFY_SCHEMA_HEAD_ALIGNMENT_STATUS"
  echo "     $VERIFY_SCHEMA_HEAD_ALIGNMENT_REASON"
  echo "  Verified DB -> storage sampled references: $VERIFY_REFERENCE_SAMPLE_VALIDATION_STATUS"
  echo "     $VERIFY_REFERENCE_SAMPLE_VALIDATION_REASON"
  echo "  Verified signed URL / storage access path: $VERIFY_SIGNED_URL_VALIDATION_STATUS"
  echo "     $VERIFY_SIGNED_URL_VALIDATION_REASON"
  echo "  Verified application media smoke: $VERIFY_APP_MEDIA_SMOKE_STATUS"
  echo "     $VERIFY_APP_MEDIA_SMOKE_REASON"
  echo ""
}

fail_restore() {
  local step="$1"
  local detail="$2"
  local message="${3:-$detail}"

  set_step_status "$step" "FAILED" "$detail"
  if [[ "$step" != "RELEASE_READINESS_DECISION" ]]; then
    set_step_status RELEASE_READINESS_DECISION "FAILED" "$message"
  fi
  case "$step" in
    DB_RESTORE|SCHEMA_HEAD_VALIDATION|BACKEND_HANDOFF_READINESS|POST_RESTORE_VALIDATION|RELEASE_READINESS_DECISION)
      DB_RESTORE_STATUS="FAILED"
      DB_RESTORE_REASON="$message"
      ;;
  esac
  log "ERROR: $message" >&2
  emit_final_summary
  exit 1
}

init_restore_steps

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
  [[ -n "$app_env" ]] || app_env="production"

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
    fail_restore S3_PROTECTION_PREREQUISITES "$S3_PROTECTION_PREREQ_REASON" "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if [[ -n "$region_manifest" && -n "$runtime_region" && "$region_manifest" != "$runtime_region" ]]; then
    S3_PROTECTION_PREREQ_REASON="manifest s3_region '$region_manifest' does not match configured S3_REGION '$runtime_region'"
    fail_restore S3_PROTECTION_PREREQUISITES "$S3_PROTECTION_PREREQ_REASON" "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if [[ -z "$effective_bucket" ]]; then
    S3_PROTECTION_PREREQ_REASON="bucket name is missing from both manifest metadata and runtime configuration"
    fail_restore S3_PROTECTION_PREREQUISITES "$S3_PROTECTION_PREREQ_REASON" "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if [[ -z "$effective_region" ]]; then
    S3_PROTECTION_PREREQ_REASON="region is missing from both manifest metadata and runtime configuration"
    fail_restore S3_PROTECTION_PREREQUISITES "$S3_PROTECTION_PREREQ_REASON" "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if [[ -z "$profile" && ( -z "$access_key" || -z "$secret_key" ) ]]; then
    S3_PROTECTION_PREREQ_REASON="AWS credentials are not configured; set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or AWS_PROFILE"
    fail_restore S3_PROTECTION_PREREQUISITES "$S3_PROTECTION_PREREQ_REASON" "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if ! command -v aws >/dev/null 2>&1; then
    S3_PROTECTION_PREREQ_REASON="aws CLI is required for production+s3 pre-restore validation but is not installed"
    fail_restore S3_PROTECTION_PREREQUISITES "$S3_PROTECTION_PREREQ_REASON" "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if ! versioning_output="$(aws s3api get-bucket-versioning --bucket "$effective_bucket" --region "$effective_region" 2>&1)"; then
    S3_PROTECTION_PREREQ_REASON="could not query bucket versioning for '$effective_bucket' in region '$effective_region': $versioning_output"
    fail_restore S3_PROTECTION_PREREQUISITES "$S3_PROTECTION_PREREQ_REASON" "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi
  if ! grep -Eq '"Status"[[:space:]]*:[[:space:]]*"Enabled"' <<<"$versioning_output"; then
    S3_PROTECTION_PREREQ_REASON="bucket versioning is not enabled for '$effective_bucket' in region '$effective_region'"
    fail_restore S3_PROTECTION_PREREQUISITES "$S3_PROTECTION_PREREQ_REASON" "S3 protection prerequisites FAILED: $S3_PROTECTION_PREREQ_REASON"
  fi

  S3_PROTECTION_PREREQ_STATUS="PASSED"
  S3_PROTECTION_PREREQ_REASON="bucket, region, credentials, aws CLI, and versioning requirement validated"
  set_step_status S3_PROTECTION_PREREQUISITES "PASSED" "$S3_PROTECTION_PREREQ_REASON"
  S3_PRE_RESTORE_VALIDATION_STATUS="FAILED"

  if ! head_bucket_output="$(aws s3api head-bucket --bucket "$effective_bucket" --region "$effective_region" 2>&1)"; then
    S3_PRE_RESTORE_VALIDATION_REASON="bucket '$effective_bucket' is not reachable with the current configuration: $head_bucket_output"
    fail_restore S3_PRE_RESTORE_VALIDATION "$S3_PRE_RESTORE_VALIDATION_REASON" "S3 pre-restore validation FAILED: $S3_PRE_RESTORE_VALIDATION_REASON"
  fi
  if ! list_objects_output="$(aws s3api list-objects-v2 --bucket "$effective_bucket" --region "$effective_region" --max-keys 1 2>&1)"; then
    S3_PRE_RESTORE_VALIDATION_REASON="basic read/list check failed for bucket '$effective_bucket': $list_objects_output"
    fail_restore S3_PRE_RESTORE_VALIDATION "$S3_PRE_RESTORE_VALIDATION_REASON" "S3 pre-restore validation FAILED: $S3_PRE_RESTORE_VALIDATION_REASON"
  fi
  if ! list_versions_output="$(aws s3api list-object-versions --bucket "$effective_bucket" --region "$effective_region" --max-keys 1 2>&1)"; then
    S3_PRE_RESTORE_VALIDATION_REASON="object/version listing check failed for bucket '$effective_bucket': $list_versions_output"
    fail_restore S3_PRE_RESTORE_VALIDATION "$S3_PRE_RESTORE_VALIDATION_REASON" "S3 pre-restore validation FAILED: $S3_PRE_RESTORE_VALIDATION_REASON"
  fi

  S3_PRE_RESTORE_VALIDATION_STATUS="PASSED"
  S3_PRE_RESTORE_VALIDATION_REASON="bucket reachable, basic read/list succeeded, and object/version listing succeeded"
  set_step_status S3_PRE_RESTORE_VALIDATION "PASSED" "$S3_PRE_RESTORE_VALIDATION_REASON"

  if ! manifest_has_non_null_string "s3_recovery_point" "$manifest_file"; then
    S3_VARIANT_A_READINESS_REASON="manifest is missing s3_recovery_point"
  elif ! manifest_has_bool_true "storage_snapshot_consistent" "$manifest_file"; then
    S3_VARIANT_A_READINESS_REASON="manifest does not declare storage_snapshot_consistent=true"
  else
    S3_VARIANT_A_READINESS_STATUS="PASSED"
    S3_VARIANT_A_READINESS_REASON="future Variant A checks have the required storage foundation metadata"
  fi
}

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
set_step_status MAINTENANCE_INTENT "PASSED" "operator-facing write-stop intent recorded; this script does not implement infrastructure maintenance mode"

# ── Manifest validation ────────────────────────────────────────────────────────
MANIFEST_FILE="$(resolve_manifest_file "$BACKUP_FILE")"
grep -q '"backup_contract"'            "$MANIFEST_FILE" || fail_restore BACKUP_SET_VALIDATION "manifest missing backup_contract"
grep -q '"backup_scope"'               "$MANIFEST_FILE" || fail_restore BACKUP_SET_VALIDATION "manifest missing backup_scope"
grep -q '"production_dr_eligible"'     "$MANIFEST_FILE" || fail_restore BACKUP_SET_VALIDATION "manifest missing production_dr_eligible"
grep -q '"db_file"'                    "$MANIFEST_FILE" || fail_restore BACKUP_SET_VALIDATION "manifest missing db_file"
grep -q '"checksum_file"'              "$MANIFEST_FILE" || fail_restore BACKUP_SET_VALIDATION "manifest missing checksum_file"
grep -q '"backup_version"'             "$MANIFEST_FILE" || fail_restore BACKUP_SET_VALIDATION "manifest missing backup_version"
grep -q '"backup_contract"[[:space:]]*:[[:space:]]*"db-restore-v1"' "$MANIFEST_FILE" || fail_restore BACKUP_SET_VALIDATION "unsupported manifest backup_contract"
grep -q '"backup_scope"[[:space:]]*:[[:space:]]*"db-only"'           "$MANIFEST_FILE" || fail_restore BACKUP_SET_VALIDATION "manifest backup_scope must be 'db-only'"
grep -q '"production_dr_eligible"[[:space:]]*:[[:space:]]*false'     "$MANIFEST_FILE" || fail_restore BACKUP_SET_VALIDATION "manifest production_dr_eligible must be false for this DB-only restore flow"
grep -q "\"db_file\"[[:space:]]*:[[:space:]]*\"$(basename "$BACKUP_FILE")\"" "$MANIFEST_FILE" \
  || fail_restore BACKUP_SET_VALIDATION "manifest db_file does not match backup artifact"
grep -q "\"checksum_file\"[[:space:]]*:[[:space:]]*\"$(basename "${BACKUP_FILE}.sha256")\"" "$MANIFEST_FILE" \
  || fail_restore BACKUP_SET_VALIDATION "manifest checksum_file does not match backup artifact"
PRODUCTION_S3_MANIFEST=0
VARIANT_A_FOUNDATION_DECLARED=0
VARIANT_A_FOUNDATION_COMPLETE=0
if grep -q '"dr_contract"' "$MANIFEST_FILE"; then
  grep -q '"dr_contract"[[:space:]]*:[[:space:]]*"variant-a-foundation-v1"' "$MANIFEST_FILE" \
    || fail_restore BACKUP_SET_VALIDATION "unsupported manifest dr_contract"
  VARIANT_A_FOUNDATION_DECLARED=1
fi
if grep -q '"dr_recovery_point_model"' "$MANIFEST_FILE"; then
  grep -q '"dr_recovery_point_model"[[:space:]]*:[[:space:]]*"db-artifact-paired-with-explicit-s3-recovery-point"' "$MANIFEST_FILE" \
    || fail_restore BACKUP_SET_VALIDATION "unsupported manifest dr_recovery_point_model"
fi
if ! grep -q '"storage_backend"[[:space:]]*:[[:space:]]*"s3"' "$MANIFEST_FILE"; then
  if manifest_has_non_null_string "s3_bucket" "$MANIFEST_FILE" \
    || manifest_has_non_null_string "s3_region" "$MANIFEST_FILE" \
    || manifest_has_non_null_string "s3_recovery_point" "$MANIFEST_FILE" \
    || manifest_has_bool_true "storage_snapshot_consistent" "$MANIFEST_FILE"; then
    fail_restore BACKUP_SET_VALIDATION "manifest declares S3 DR metadata without storage_backend=s3"
  fi
fi
if manifest_has_bool_true "storage_snapshot_consistent" "$MANIFEST_FILE"; then
  grep -q '"storage_backend"[[:space:]]*:[[:space:]]*"s3"' "$MANIFEST_FILE" \
    || fail_restore BACKUP_SET_VALIDATION "storage_snapshot_consistent=true requires storage_backend=s3"
  manifest_has_non_null_string "s3_bucket" "$MANIFEST_FILE" \
    || fail_restore BACKUP_SET_VALIDATION "storage_snapshot_consistent=true requires s3_bucket"
  manifest_has_non_null_string "s3_region" "$MANIFEST_FILE" \
    || fail_restore BACKUP_SET_VALIDATION "storage_snapshot_consistent=true requires s3_region"
  manifest_has_non_null_string "s3_recovery_point" "$MANIFEST_FILE" \
    || fail_restore BACKUP_SET_VALIDATION "storage_snapshot_consistent=true requires s3_recovery_point"
fi
if grep -q '"app_env"[[:space:]]*:[[:space:]]*"production"' "$MANIFEST_FILE" \
  && grep -q '"storage_backend"[[:space:]]*:[[:space:]]*"s3"' "$MANIFEST_FILE"; then
  PRODUCTION_S3_MANIFEST=1
  set_step_status MEDIA_RESTORE "NOT IMPLEMENTED" "future Variant A placeholder; this script does not restore S3/media objects"
  set_step_status MEDIA_VALIDATION "NOT VERIFIED" "future Variant A placeholder; this script does not verify recovered media state"
  PRODUCTION_DR_REASON="media restore and media validation are not implemented by this restore flow"
  if grep -q '"storage_archive_included"[[:space:]]*:[[:space:]]*true' "$MANIFEST_FILE"; then
    fail_restore BACKUP_SET_VALIDATION "manifest claims storage archive coverage for production+s3 backup. This DB-only restore flow refuses ambiguous production media claims."
  fi
  if grep -q '"storage_coverage"' "$MANIFEST_FILE" \
    && ! grep -q '"storage_coverage"[[:space:]]*:[[:space:]]*"authoritative-s3-not-covered-by-this-backup"' "$MANIFEST_FILE"; then
    fail_restore BACKUP_SET_VALIDATION "manifest storage_coverage is inconsistent with production+s3 DB-only semantics."
  fi
  if manifest_has_non_null_string "s3_bucket" "$MANIFEST_FILE" \
    && manifest_has_non_null_string "s3_region" "$MANIFEST_FILE" \
    && manifest_has_non_null_string "s3_recovery_point" "$MANIFEST_FILE" \
    && manifest_has_bool_true "storage_snapshot_consistent" "$MANIFEST_FILE"; then
    VARIANT_A_FOUNDATION_COMPLETE=1
  fi
  warn "Manifest declares APP_ENV=production with STORAGE_BACKEND=s3."
  warn "This restore covers database state only. Authoritative S3/object storage remains out of scope."
  if [[ $VARIANT_A_FOUNDATION_DECLARED -eq 1 && $VARIANT_A_FOUNDATION_COMPLETE -eq 1 ]]; then
    warn "Variant A foundation metadata is present, but this flow does not restore S3/object storage or prove recovered media state."
  elif [[ $VARIANT_A_FOUNDATION_DECLARED -eq 1 ]]; then
    warn "Variant A foundation contract is present, but required S3 recovery point metadata is incomplete."
  fi
  validate_s3_pre_restore_guards "$MANIFEST_FILE"
  log "S3 protection prerequisites: $S3_PROTECTION_PREREQ_STATUS"
  log "S3 pre-restore validation: $S3_PRE_RESTORE_VALIDATION_STATUS"
  if [[ "$S3_VARIANT_A_READINESS_STATUS" == "PASSED" ]]; then
    log "Variant A storage-readiness: PASSED"
  else
    warn "Variant A storage-readiness: FAILED (${S3_VARIANT_A_READINESS_REASON})"
  fi
fi
if [[ $PRODUCTION_S3_MANIFEST -eq 0 ]]; then
  PRODUCTION_DR_REASON="this flow keeps the DB-only restore path compatible and does not verify full production disaster recovery"
fi
log "✓ Manifest OK ($(basename "$MANIFEST_FILE"))"
EXPECTED_HEAD="$(detect_expected_head "$PROJECT_DIR/python-backend/alembic/versions")"
log "Expected Alembic HEAD: $EXPECTED_HEAD"
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
VERIFY_SCRIPT="${VERIFY_SCRIPT_OVERRIDE:-$PROJECT_DIR/python-backend/scripts/verify_restore.sh}"
PREVERIFY_STATUS="PASSED"
if [[ "$SKIP_VERIFY" == "--skip-verify" ]]; then
  echo "WARNING: verify skipped — unsafe operation"
  PREVERIFY_STATUS="SKIPPED (operator override)"
  sleep 2
else
  [ -f "$VERIFY_SCRIPT" ] || { echo "ERROR: verify script missing: $VERIFY_SCRIPT"; exit 1; }
  if ! timeout 60 bash "$VERIFY_SCRIPT" "$BACKUP_FILE"; then
    echo "ERROR: verify_restore.sh FAILED or timed out (>60s) — aborting restore"
    exit 1
  fi
  echo "Verify OK — continuing restore"
fi
echo ""

if [[ "$PREVERIFY_STATUS" == "SKIPPED (operator override)" ]]; then
  set_step_status BACKUP_SET_VALIDATION "PASSED" "manifest and checksum validated; pre-restore verify skipped by operator override"
else
  set_step_status BACKUP_SET_VALIDATION "PASSED" "manifest, checksum, and pre-restore verify completed"
fi

if [[ "$AUTO_YES" != "--yes" ]]; then
  read -r -p "Type 'yes' to continue: " CONFIRM
  [[ "$CONFIRM" == "yes" ]] || { echo "Aborted."; exit 0; }
fi

cd "$PROJECT_DIR"
set_step_status DB_RESTORE "IN PROGRESS" "write-stop request issued; database recreation and pg_restore are starting"

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
  --command="DROP DATABASE IF EXISTS novu_builder;" \
  || fail_restore DB_RESTORE "could not drop database novu_builder"

log "Creating database …"
docker compose -f "$COMPOSE_FILE" exec -T db \
  psql -U novu postgres --quiet \
  --command="CREATE DATABASE novu_builder OWNER novu;" \
  || fail_restore DB_RESTORE "could not create database novu_builder"

# ── 3. Copy backup into container + restore ────────────────────────────────────
# pg_restore (custom format) requires a seekable file — cannot be piped via stdin.
# We copy the backup into the container, restore, then remove it.
CONTAINER_ID=$(docker compose -f "$COMPOSE_FILE" ps -q db)
[[ -n "$CONTAINER_ID" ]] || fail_restore DB_RESTORE "DB container is not running"

log "Copying backup into DB container …"
docker cp "$BACKUP_FILE" "$CONTAINER_ID:/tmp/novu_restore.pgdump" \
  || fail_restore DB_RESTORE "could not copy backup into DB container"

log "Restoring from $(basename "$BACKUP_FILE") …"
set +e
docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_restore \
  -U novu \
  --dbname=novu_builder \
  --no-password \
  --jobs=4 \
  /tmp/novu_restore.pgdump \
  2>&1 | grep -v "^pg_restore: creating\|^pg_restore: executing"
RESTORE_PIPE_STATUS=${PIPESTATUS[0]}
set -e
[[ $RESTORE_PIPE_STATUS -eq 0 ]] || fail_restore DB_RESTORE "pg_restore failed with exit code $RESTORE_PIPE_STATUS"

log "Cleaning up temp file in container …"
docker compose -f "$COMPOSE_FILE" exec -T db rm -f /tmp/novu_restore.pgdump || true

set_step_status DB_RESTORE "PASSED" "backend/worker stop requested, database recreated, and pg_restore finished"
log "DB restore step finished."

# ── 4. Verify critical tables and migration state ─────────────────────────────
# Check specific critical tables — concrete assertion, not a count heuristic.
log "Verifying restore integrity …"

set_step_status SCHEMA_HEAD_VALIDATION "IN PROGRESS" "critical tables, alembic state, and schema/head alignment are being checked"

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
    fail_restore SCHEMA_HEAD_VALIDATION "critical table '${tbl}' is missing after restore — backup may be incomplete"
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
[[ -n "$ALEMBIC_REV" ]] || fail_restore SCHEMA_HEAD_VALIDATION "alembic_version is empty after restore"
log "  ✓ alembic_version: $ALEMBIC_REV"

# ── 5. Apply pending migrations ────────────────────────────────────────────────
log "Applying pending Alembic migrations …"
docker compose -f "$COMPOSE_FILE" run --rm backend alembic upgrade head \
  || fail_restore SCHEMA_HEAD_VALIDATION "alembic upgrade head failed during restore"
POST_MIGRATION_REV=$(docker compose -f "$COMPOSE_FILE" exec -T db \
  psql -U novu novu_builder --tuples-only --no-align \
  --command="SELECT version_num FROM alembic_version;" \
  2>/dev/null | tr -d ' \r\n')
[[ -n "$POST_MIGRATION_REV" ]] || fail_restore SCHEMA_HEAD_VALIDATION "alembic_version is empty after migration step"
[[ "$POST_MIGRATION_REV" == "$EXPECTED_HEAD" ]] || fail_restore SCHEMA_HEAD_VALIDATION "schema revision '$POST_MIGRATION_REV' does not match repository HEAD '$EXPECTED_HEAD' after restore"
log "  ✓ schema/head alignment verified: $POST_MIGRATION_REV"
set_step_status SCHEMA_HEAD_VALIDATION "PASSED" "critical tables and schema/head alignment validated at revision $POST_MIGRATION_REV"

# ── 6. Restart backend + worker ────────────────────────────────────────────────
set_step_status BACKEND_HANDOFF_READINESS "IN PROGRESS" "backend and worker restart requested; waiting for liveness confirmation"
log "Starting backend and worker …"
docker compose -f "$COMPOSE_FILE" start backend worker || fail_restore BACKEND_HANDOFF_READINESS "could not start backend and worker after restore"

# ── 7. Health poll ─────────────────────────────────────────────────────────────
log "Waiting for backend liveness (max 60s) …"
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
  set_step_status BACKEND_HANDOFF_READINESS "PASSED" "backend responded to liveness probe at $HEALTH_URL"
  log "✓ Backend process responded to liveness probe."
else
  set_step_status BACKEND_HANDOFF_READINESS "FAILED" "backend did not respond to liveness probe within 60s at $HEALTH_URL"
  warn "Backend did not respond within 60s — check 'docker compose logs backend'."
fi

# ── 8. Summary ─────────────────────────────────────────────────────────────────
if [[ $HEALTHY -eq 1 ]]; then
  set_step_status POST_RESTORE_VALIDATION "PASSED" "DB restore, schema/head validation, and backend liveness checks completed"
  DB_RESTORE_STATUS="PASSED"
  DB_RESTORE_REASON="database restore, schema/head validation, and backend liveness completed"
  if [[ $PRODUCTION_S3_MANIFEST -eq 1 ]]; then
    set_step_status RELEASE_READINESS_DECISION "PASSED" "DB handoff ready only; media restore is not implemented and Production DR remains NOT VERIFIED"
  else
    set_step_status RELEASE_READINESS_DECISION "PASSED" "DB handoff ready for the DB-only restore contract; Production DR remains NOT VERIFIED"
  fi
else
  set_step_status POST_RESTORE_VALIDATION "FAILED" "backend liveness was not confirmed, so post-restore validation is incomplete"
  set_step_status RELEASE_READINESS_DECISION "FAILED" "backend liveness was not confirmed; do not release restored services"
  DB_RESTORE_STATUS="FAILED"
  DB_RESTORE_REASON="database state was restored but backend liveness was not confirmed"
fi

emit_final_summary

echo "  DB restore contract: PASSED"
echo "  Schema/head alignment: PASSED ($POST_MIGRATION_REV)"
if [[ $HEALTHY -eq 1 ]]; then
  echo "  Backend liveness probe: PASSED ($HEALTH_URL)"
else
  echo "  Backend liveness probe: FAILED (no response within 60s)"
fi
echo "  Production DR: NOT VERIFIED"
if [[ $PRODUCTION_S3_MANIFEST -eq 1 ]]; then
  echo "  S3 protection prerequisites: $S3_PROTECTION_PREREQ_STATUS"
  echo "  S3 pre-restore validation: $S3_PRE_RESTORE_VALIDATION_STATUS"
  echo "  Variant A storage-readiness: $S3_VARIANT_A_READINESS_STATUS"
  if [[ "$S3_VARIANT_A_READINESS_STATUS" != "PASSED" ]]; then
    echo "  Variant A storage-readiness reason: $S3_VARIANT_A_READINESS_REASON"
  fi
  echo "  Authoritative S3/object storage recovery: NOT VERIFIED / OUT OF SCOPE"
  if [[ $VARIANT_A_FOUNDATION_COMPLETE -eq 1 ]]; then
    echo "  Variant A foundation contract: metadata recorded only; full DR still not implemented"
  elif [[ $VARIANT_A_FOUNDATION_DECLARED -eq 1 ]]; then
    echo "  Variant A foundation contract: present but incomplete; full DR still not implemented"
  fi
fi
echo ""
echo "This workflow validates DB restore integrity and schema/head alignment only."
echo "A dependency-free liveness probe does NOT prove full application readiness or S3 media recovery."
if [[ $HEALTHY -ne 1 ]]; then
  echo ""
  echo "Release readiness decision: FAILED (backend liveness was not confirmed; Production DR remains NOT VERIFIED)"
  exit 1
fi
echo ""
echo "Release readiness decision: PASSED (DB handoff ready only; Production DR remains NOT VERIFIED)"
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
