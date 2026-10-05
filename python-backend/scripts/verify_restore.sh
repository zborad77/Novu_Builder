#!/usr/bin/env bash
# =============================================================================
#  verify_restore.sh - Verify that a backup can be restored to a temporary DB
#
#  Usage:
#    ./scripts/verify_restore.sh backups/db_20260324_120000.pgdump
#
#  This script validates the DB-only restore contract plus only the explicit
#  post-restore checks emitted below. It does NOT validate runtime startup,
#  service liveness, or full S3/object storage recovery.
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

extract_manifest_int_value() {
  local key="$1"
  local manifest_file="$2"

  sed -nE "s/.*\"${key}\"[[:space:]]*:[[:space:]]*([0-9]+).*/\1/p" "$manifest_file" | head -1
}

S3_PROTECTION_PREREQ_STATUS="NOT EXECUTED"
S3_PROTECTION_PREREQ_REASON="not required for this verify flow"
S3_PRE_RESTORE_VALIDATION_STATUS="NOT EXECUTED"
S3_PRE_RESTORE_VALIDATION_REASON="not required for this verify flow"
S3_VARIANT_A_READINESS_STATUS="NOT EXECUTED"
S3_VARIANT_A_READINESS_REASON="not required for this verify flow"
DB_QUERY_USABILITY_STATUS="NOT EXECUTED"
DB_QUERY_USABILITY_REASON="database query usability has not been checked"
SCHEMA_HEAD_ALIGNMENT_STATUS="NOT EXECUTED"
SCHEMA_HEAD_ALIGNMENT_REASON="schema/head alignment has not been checked"
REFERENCE_SAMPLE_VALIDATION_STATUS="NOT EXECUTED"
REFERENCE_SAMPLE_VALIDATION_REASON="DB-to-storage sample validation has not been checked"
SIGNED_URL_VALIDATION_STATUS="NOT EXECUTED"
SIGNED_URL_VALIDATION_REASON="signed URL/access path validation has not been checked"
APP_MEDIA_SMOKE_STATUS="NOT EXECUTED"
APP_MEDIA_SMOKE_REASON="application media smoke validation has not been checked"
FULL_STATE_S3_MANIFEST=0
MANIFEST_PRODUCTION_DR_ELIGIBLE="false"
# Full bi-directional storage consistency check is NOT run by verify_restore.sh.
# verify_restore.sh covers sampled DB-to-storage reference validation only.
# For a post-restore full consistency check run:
#   python scripts/check_storage_consistency.py --database-url "$DATABASE_URL"
# Exit 0 = clean or warnings-only; exit 1 = blocker (hard fail); exit 2 = scan error.
FULL_CONSISTENCY_CHECK_STATUS="NOT EXECUTED"
FULL_CONSISTENCY_CHECK_REASON="full DB<->S3 consistency check is out of scope for verify_restore.sh; run check_storage_consistency.py post-restore"

emit_post_restore_step() {
  local name="$1"
  local status="$2"
  local detail="$3"
  detail="${detail//|//}"
  printf 'POST_RESTORE_VALIDATION_STEP|%s|%s|%s\n' "$name" "$status" "$detail"
}

set_post_restore_status() {
  local step_name="$1"
  local status="$2"
  local detail="$3"

  case "$step_name" in
    db_query_usability)
      DB_QUERY_USABILITY_STATUS="$status"
      DB_QUERY_USABILITY_REASON="$detail"
      ;;
    schema_head_alignment)
      SCHEMA_HEAD_ALIGNMENT_STATUS="$status"
      SCHEMA_HEAD_ALIGNMENT_REASON="$detail"
      ;;
    reference_sample_validation)
      REFERENCE_SAMPLE_VALIDATION_STATUS="$status"
      REFERENCE_SAMPLE_VALIDATION_REASON="$detail"
      ;;
    signed_url_validation)
      SIGNED_URL_VALIDATION_STATUS="$status"
      SIGNED_URL_VALIDATION_REASON="$detail"
      ;;
    app_media_smoke)
      APP_MEDIA_SMOKE_STATUS="$status"
      APP_MEDIA_SMOKE_REASON="$detail"
      ;;
    *)
      die "unsupported post-restore validation step '$step_name'"
      ;;
  esac

  emit_post_restore_step "$step_name" "$status" "$detail"
}

run_media_validation_suite() {
  local validation_db_url="$1"
  local helper_script="$BACKEND_DIR/scripts/validate_restored_media.py"
  local python_bin="${PYTHON_BIN:-python}"
  local output status
  local step_name step_status step_detail
  local saw_reference=0
  local saw_signed=0
  local saw_smoke=0

  [[ -f "$helper_script" ]] || die "post-restore media validation helper is missing: $helper_script"
  command -v "$python_bin" >/dev/null 2>&1 \
    || die "python interpreter '$python_bin' is required for post-restore media validation"

  set +e
  output="$("$python_bin" "$helper_script" \
    --database-url "$validation_db_url" \
    --sample-size "${RESTORE_STORAGE_REFERENCE_SAMPLE_SIZE:-3}" 2>&1)"
  status=$?
  set -e

  [[ -n "$output" ]] && printf '%s\n' "$output"

  while IFS= read -r line; do
    [[ "$line" == POST_RESTORE_VALIDATION_STEP\|* ]] || continue
    IFS='|' read -r _prefix step_name step_status step_detail <<< "$line"
    case "$step_name" in
      reference_sample_validation) saw_reference=1 ;;
      signed_url_validation) saw_signed=1 ;;
      app_media_smoke) saw_smoke=1 ;;
      *) continue ;;
    esac
    set_post_restore_status "$step_name" "$step_status" "$step_detail"
  done <<< "$output"

  [[ $saw_reference -eq 1 ]] || die "post-restore media validation did not report reference_sample_validation status"
  [[ $saw_signed -eq 1 ]] || die "post-restore media validation did not report signed_url_validation status"
  [[ $saw_smoke -eq 1 ]] || die "post-restore media validation did not report app_media_smoke status"

  if [[ $status -ne 0 ]]; then
    FAILED=1
  fi
}

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

validate_s3_media_manifest_pairing() {
  local manifest_file="$1"
  local backup_file="$2"
  local media_manifest_path="$3"
  local source_bucket source_region recovery_point media_backup_file media_manifest_file
  local media_bucket media_region media_recovery_point media_format media_count manifest_count

  [[ -f "$media_manifest_path" ]] || die "S3 media manifest file is missing: $media_manifest_path"

  media_format="$(extract_manifest_string_value "format" "$media_manifest_path")"
  [[ "$media_format" == "novu-s3-media-manifest-v1" ]] \
    || die "unsupported S3 media manifest format in $(basename "$media_manifest_path")"

  source_bucket="$(extract_manifest_string_value "s3_bucket" "$manifest_file")"
  source_region="$(extract_manifest_string_value "s3_region" "$manifest_file")"
  recovery_point="$(extract_manifest_string_value "s3_recovery_point" "$manifest_file")"
  media_backup_file="$(extract_manifest_string_value "db_backup_file" "$media_manifest_path")"
  media_manifest_file="$(extract_manifest_string_value "db_manifest_file" "$media_manifest_path")"
  media_bucket="$(extract_manifest_string_value "source_bucket" "$media_manifest_path")"
  media_region="$(extract_manifest_string_value "source_region" "$media_manifest_path")"
  media_recovery_point="$(extract_manifest_string_value "declared_recovery_point" "$media_manifest_path")"
  media_count="$(extract_manifest_int_value "unique_object_count" "$media_manifest_path")"
  manifest_count="$(extract_manifest_int_value "s3_object_count" "$manifest_file")"

  [[ "$media_backup_file" == "$(basename "$backup_file")" ]] \
    || die "S3 media manifest is not paired with this DB backup artifact"
  [[ "$media_manifest_file" == "$(basename "$manifest_file")" ]] \
    || die "S3 media manifest is not paired with this DB manifest"
  [[ "$media_bucket" == "$source_bucket" ]] \
    || die "S3 media manifest bucket does not match the DB manifest"
  [[ "$media_region" == "$source_region" ]] \
    || die "S3 media manifest region does not match the DB manifest"
  [[ "$media_recovery_point" == "$recovery_point" ]] \
    || die "S3 media manifest recovery point does not match the DB manifest"
  [[ -n "$media_count" && "$media_count" =~ ^[0-9]+$ ]] \
    || die "S3 media manifest does not report a valid unique_object_count"
  [[ "$manifest_count" == "$media_count" ]] \
    || die "S3 media manifest object count does not match the DB manifest"
}

validate_manifest_contract() {
  local manifest_file="$1"
  local backup_file="$2"
  local backup_scope dr_contract dr_recovery_point_model media_manifest_file
  local production_dr_eligible

  grep -q '"backup_contract"'        "$manifest_file" || die "manifest missing backup_contract"
  grep -q '"backup_scope"'           "$manifest_file" || die "manifest missing backup_scope"
  grep -q '"production_dr_eligible"' "$manifest_file" || die "manifest missing production_dr_eligible"
  grep -q '"db_file"'                "$manifest_file" || die "manifest missing db_file"
  grep -q '"checksum_file"'          "$manifest_file" || die "manifest missing checksum_file"
  grep -q '"backup_version"'         "$manifest_file" || die "manifest missing backup_version"
  grep -q '"backup_contract"[[:space:]]*:[[:space:]]*"db-restore-v1"' "$manifest_file" \
    || die "unsupported manifest backup_contract"
  grep -q "\"db_file\"[[:space:]]*:[[:space:]]*\"$(basename "$backup_file")\"" "$manifest_file" \
    || die "manifest db_file does not match backup artifact"
  grep -q "\"checksum_file\"[[:space:]]*:[[:space:]]*\"$(basename "${backup_file}.sha256")\"" "$manifest_file" \
    || die "manifest checksum_file does not match backup artifact"
  backup_scope="$(extract_manifest_string_value "backup_scope" "$manifest_file")"
  dr_contract="$(extract_manifest_string_value "dr_contract" "$manifest_file")"
  dr_recovery_point_model="$(extract_manifest_string_value "dr_recovery_point_model" "$manifest_file")"
  media_manifest_file="$(extract_manifest_string_value "s3_media_manifest_file" "$manifest_file")"
  production_dr_eligible="false"
  if grep -q '"production_dr_eligible"[[:space:]]*:[[:space:]]*true' "$manifest_file"; then
    production_dr_eligible="true"
  fi
  MANIFEST_PRODUCTION_DR_ELIGIBLE="$production_dr_eligible"

  case "$backup_scope" in
    db-only)
      [[ "$production_dr_eligible" == "false" ]] \
        || die "manifest production_dr_eligible must be false for the db-only verify flow"
      [[ "$dr_contract" == "variant-a-foundation-v1" ]] \
        || die "unsupported dr_contract for db-only backup scope"
      [[ "$dr_recovery_point_model" == "db-artifact-paired-with-explicit-s3-recovery-point" ]] \
        || die "unsupported dr_recovery_point_model for db-only backup scope"
      ;;
    db-plus-s3-media-manifest)
      FULL_STATE_S3_MANIFEST=1
      [[ "$production_dr_eligible" == "true" ]] \
        || die "full-state S3 backup scope requires production_dr_eligible=true"
      [[ "$dr_contract" == "s3-full-state-v1" ]] \
        || die "unsupported dr_contract for full-state S3 backup scope"
      [[ "$dr_recovery_point_model" == "db-artifact-paired-with-versioned-s3-object-manifest" ]] \
        || die "unsupported dr_recovery_point_model for full-state S3 backup scope"
      [[ -n "$media_manifest_file" ]] \
        || die "full-state S3 backup scope requires s3_media_manifest_file"
      grep -q '"s3_media_manifest_format"[[:space:]]*:[[:space:]]*"novu-s3-media-manifest-v1"' "$manifest_file" \
        || die "full-state S3 backup scope requires s3_media_manifest_format=novu-s3-media-manifest-v1"
      grep -q '"s3_media_restore_strategy"[[:space:]]*:[[:space:]]*"versioned-copy-to-isolated-bucket-v1"' "$manifest_file" \
        || die "full-state S3 backup scope requires s3_media_restore_strategy=versioned-copy-to-isolated-bucket-v1"
      extract_manifest_int_value "s3_object_count" "$manifest_file" >/dev/null \
        || die "full-state S3 backup scope requires s3_object_count"
      ;;
    *)
      die "unsupported manifest backup_scope"
      ;;
  esac

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
    if [[ "$backup_scope" == "db-only" ]] && grep -q '"storage_archive_included"[[:space:]]*:[[:space:]]*true' "$manifest_file"; then
      die "manifest claims storage archive coverage for production+s3 backup; this DB-only verify flow refuses ambiguous production media claims"
    fi
    if [[ "$backup_scope" == "db-only" ]] && grep -q '"storage_coverage"' "$manifest_file" \
      && ! grep -q '"storage_coverage"[[:space:]]*:[[:space:]]*"authoritative-s3-not-covered-by-this-backup"' "$manifest_file"; then
      die "manifest storage_coverage is inconsistent with production+s3 DB-only semantics"
    fi
    if [[ "$backup_scope" == "db-plus-s3-media-manifest" ]] && ! grep -q '"storage_coverage"[[:space:]]*:[[:space:]]*"authoritative-s3-media-manifest"' "$manifest_file"; then
      die "manifest storage_coverage is inconsistent with full-state production+s3 semantics"
    fi
    warn "Manifest declares APP_ENV=production with STORAGE_BACKEND=s3."
    if [[ "$backup_scope" == "db-only" ]]; then
      warn "This verify flow covers database state only. Authoritative S3/object storage remains out of scope."
    else
      warn "This verify flow validates pairing and preflight checks for the full-state S3 contract, but it does not restore media."
    fi
    if [[ "$dr_contract" == "variant-a-foundation-v1" ]]; then
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
if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
  echo "Usage: $0 <backup_file.pgdump>"
  exit 1
fi

MANIFEST_FILE="$(resolve_manifest_file "$BACKUP_FILE")" \
  || die "manifest file missing for $(basename "$BACKUP_FILE")"
validate_manifest_contract "$MANIFEST_FILE" "$BACKUP_FILE"
log "Manifest OK: $(basename "$MANIFEST_FILE")"
if [[ $FULL_STATE_S3_MANIFEST -eq 1 ]]; then
  MEDIA_MANIFEST_PATH="$(dirname "$BACKUP_FILE")/$(extract_manifest_string_value "s3_media_manifest_file" "$MANIFEST_FILE")"
  validate_s3_media_manifest_pairing "$MANIFEST_FILE" "$BACKUP_FILE" "$MEDIA_MANIFEST_PATH"
  log "S3 media manifest pairing OK: $(basename "$MEDIA_MANIFEST_PATH")"
fi

load_env
EXPECTED_HEAD="$(detect_expected_head "$BACKEND_DIR/alembic/versions")"
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

if ! command -v psql >/dev/null 2>&1 || ! command -v pg_restore >/dev/null 2>&1; then
  echo "Host tools missing, checking docker toolchain..."
  _PROJECT_DIR="$(dirname "$BACKEND_DIR")"
  _COMPOSE_FILE="$_PROJECT_DIR/docker-compose.yml"
  if ! docker compose -f "$_COMPOSE_FILE" exec -T db pg_restore --version > /dev/null 2>&1; then
    echo "ERROR: docker toolchain check failed"
    exit 1
  fi
  echo "Docker toolchain detected but full verify requires psql/pg_restore on host - please install them locally"
  exit 1
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
DB_HOST="${DB_HOSTPORT%%:*}"
DB_PORT="${DB_HOSTPORT##*:}"
[[ "$DB_PORT" == "$DB_HOST" ]] && DB_PORT="5432"

export PGPASSWORD="$DB_PASS"
PG_CONN=( --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" )
VALIDATION_DB_URL="postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}"

TEMP_DB="novu_verify_$(date +%s)"
FAILED=0

cleanup() {
  echo "Dropping temp database '$TEMP_DB' ..."
  psql "${PG_CONN[@]}" --dbname=postgres \
    --command="DROP DATABASE IF EXISTS \"$TEMP_DB\";" --quiet 2>/dev/null || true
}
trap cleanup EXIT

echo "=================================================="
echo "  Backup verify: $(basename "$BACKUP_FILE")"
echo "  Temp DB:       $TEMP_DB @ $DB_HOST:$DB_PORT"
echo "=================================================="

CHECKSUM_FILE="${BACKUP_FILE}.sha256"
[[ -f "$CHECKSUM_FILE" ]] || die "checksum file missing for verify contract: $CHECKSUM_FILE"
echo "Checking checksum ..."
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum --check "$CHECKSUM_FILE" || { echo "  checksum mismatch"; exit 1; }
else
  openssl dgst -sha256 "$BACKUP_FILE" | diff - "$CHECKSUM_FILE" || { echo "  checksum mismatch"; exit 1; }
fi
echo "  checksum OK"

echo "Creating temp database ..."
psql "${PG_CONN[@]}" --dbname=postgres \
  --command="CREATE DATABASE \"$TEMP_DB\" OWNER \"$DB_USER\";" --quiet

echo "Restoring backup ..."
set +e
pg_restore \
  "${PG_CONN[@]}" \
  --dbname="$TEMP_DB" \
  --no-password \
  --jobs=4 \
  "$BACKUP_FILE" 2>&1 | grep -v "^pg_restore: creating\|^pg_restore: executing"
RESTORE_PIPE_STATUS=${PIPESTATUS[0]}
set -e
[[ $RESTORE_PIPE_STATUS -eq 0 ]] || die "pg_restore failed with exit code $RESTORE_PIPE_STATUS"
echo "  pg_restore finished"

assert_table_exists() {
  local table="$1"
  local exists
  exists=$(psql "${PG_CONN[@]}" --dbname="$TEMP_DB" --tuples-only --no-align \
    --command="SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='${table}');" \
    2>/dev/null | tr -d ' \r\n')
  if [[ "$exists" == "t" ]]; then
    echo "  table exists: $table"
  else
    echo "  table missing: $table"
    FAILED=1
  fi
}

assert_has_rows() {
  local table="$1"
  local result
  result=$(psql "${PG_CONN[@]}" --dbname="$TEMP_DB" --tuples-only --no-align \
    --command="SELECT COUNT(*) > 0 FROM ${table};" 2>/dev/null | tr -d ' \r\n')
  if [[ "$result" == "t" ]]; then
    echo "  rows present: $table"
  else
    echo "  table empty: $table"
    FAILED=1
  fi
}

show_count() {
  local table="$1"
  local result
  result=$(psql "${PG_CONN[@]}" --dbname="$TEMP_DB" --tuples-only --no-align \
    --command="SELECT COUNT(*) FROM ${table};" 2>/dev/null | tr -d ' \r\n')
  echo "  ${table}: ${result} rows"
}

echo "Checking critical tables ..."
assert_table_exists "organizations"
assert_table_exists "users"
assert_table_exists "projects"
assert_table_exists "audit_logs"
assert_table_exists "role_permissions"
assert_table_exists "revoked_tokens"
assert_table_exists "alembic_version"

echo "Checking operational data ..."
assert_has_rows "organizations"
assert_has_rows "users"
assert_has_rows "role_permissions"
show_count "projects"
show_count "analysis_jobs"
show_count "audit_logs"

if [[ $FAILED -eq 0 ]]; then
  set_post_restore_status \
    "db_query_usability" \
    "PASSED" \
    "critical tables exist and basic operational queries returned expected results"
else
  set_post_restore_status \
    "db_query_usability" \
    "FAILED" \
    "critical table presence or basic operational query checks failed"
fi

echo "Checking alembic_version ..."
DB_HEAD=$(psql "${PG_CONN[@]}" --dbname="$TEMP_DB" --tuples-only --no-align \
  --command="SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d ' \r\n')

if [[ -z "$DB_HEAD" ]]; then
  echo "  alembic_version is empty"
  FAILED=1
  set_post_restore_status \
    "schema_head_alignment" \
    "FAILED" \
    "alembic_version is empty after restore"
elif [[ "$DB_HEAD" == "$EXPECTED_HEAD" ]]; then
  echo "  schema/head alignment OK: $DB_HEAD"
  set_post_restore_status \
    "schema_head_alignment" \
    "PASSED" \
    "database schema revision matches repository HEAD ($DB_HEAD)"
else
  echo "  schema/head mismatch: DB=$DB_HEAD REPO=$EXPECTED_HEAD"
  FAILED=1
  set_post_restore_status \
    "schema_head_alignment" \
    "FAILED" \
    "database schema revision '$DB_HEAD' does not match repository HEAD '$EXPECTED_HEAD'"
fi

if [[ $FAILED -eq 0 ]]; then
  run_media_validation_suite "${VALIDATION_DB_URL}/${TEMP_DB}"
else
  set_post_restore_status \
    "reference_sample_validation" \
    "NOT EXECUTED" \
    "skipped because DB query usability or schema/head alignment already failed"
  set_post_restore_status \
    "signed_url_validation" \
    "NOT EXECUTED" \
    "skipped because DB query usability or schema/head alignment already failed"
  set_post_restore_status \
    "app_media_smoke" \
    "NOT EXECUTED" \
    "skipped because DB query usability or schema/head alignment already failed"
fi

echo ""
if [[ $FAILED -eq 0 ]]; then
  echo "DB restore verification status: PASSED"
  if grep -q '"app_env"[[:space:]]*:[[:space:]]*"production"' "$MANIFEST_FILE" \
    && grep -q '"storage_backend"[[:space:]]*:[[:space:]]*"s3"' "$MANIFEST_FILE"; then
    echo "S3 protection prerequisites: $S3_PROTECTION_PREREQ_STATUS"
    echo "S3 pre-restore validation: $S3_PRE_RESTORE_VALIDATION_STATUS"
    echo "Variant A storage-readiness: $S3_VARIANT_A_READINESS_STATUS"
    if [[ "$S3_VARIANT_A_READINESS_STATUS" != "PASSED" ]]; then
      echo "Variant A storage-readiness reason: $S3_VARIANT_A_READINESS_REASON"
    fi
  fi
  echo "DB query usability: $DB_QUERY_USABILITY_STATUS"
  echo "DB query usability detail: $DB_QUERY_USABILITY_REASON"
  echo "Schema/head alignment: $SCHEMA_HEAD_ALIGNMENT_STATUS"
  echo "Schema/head alignment detail: $SCHEMA_HEAD_ALIGNMENT_REASON"
  echo "DB -> storage sampled reference validation: $REFERENCE_SAMPLE_VALIDATION_STATUS"
  echo "DB -> storage sampled reference detail: $REFERENCE_SAMPLE_VALIDATION_REASON"
  echo "Signed URL / storage access path validation: $SIGNED_URL_VALIDATION_STATUS"
  echo "Signed URL / storage access path detail: $SIGNED_URL_VALIDATION_REASON"
  echo "Application media smoke validation: $APP_MEDIA_SMOKE_STATUS"
  echo "Application media smoke detail: $APP_MEDIA_SMOKE_REASON"
  echo "Full DB<->S3 consistency check: $FULL_CONSISTENCY_CHECK_STATUS"
  echo "Full DB<->S3 consistency detail: $FULL_CONSISTENCY_CHECK_REASON"
  echo "production_dr_eligible (manifest): $MANIFEST_PRODUCTION_DR_ELIGIBLE"
  if [[ $FULL_STATE_S3_MANIFEST -eq 1 ]]; then
    echo "Full-state backup contract: DECLARED"
    echo "Full-state restore claim: NOT VERIFIED"
    echo "Production DR: NOT VERIFIED"
    echo "This verifies backup-set pairing and sampled media usability for the full-state S3 contract."
    echo "It does NOT validate service liveness, isolated media restore execution, or full post-restore S3 recovery."
  else
    echo "Full-state restore claim: NOT VERIFIED"
    echo "Production DR: NOT VERIFIED"
    echo "This verifies the DB-only restore contract plus only the explicit sampled media checks emitted above."
    echo "It does NOT validate runtime startup, service liveness, full media restore, or full S3/object storage recovery."
  fi
else
  echo "FAIL - DB restore verification failed."
  exit 1
fi
