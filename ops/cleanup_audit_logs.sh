#!/usr/bin/env bash
# =============================================================================
# cleanup_audit_logs.sh — Audit log retention policy (C9)
#
# Retention policy:
#   - Security events (login, password_reset, permission_change, impersonation):
#     retain for 365 days
#   - All other audit events: retain for 90 days
#
# Usage:
#   ./ops/cleanup_audit_logs.sh
#
# Cron example (run daily at 02:30):
#   30 2 * * * /path/to/ops/cleanup_audit_logs.sh >> /var/log/audit-cleanup.log 2>&1
# =============================================================================
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
DB_NAME="${POSTGRES_DB:-novu}"
DB_USER="${POSTGRES_USER:-postgres}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

log "Starting audit log cleanup..."

# Security-sensitive events — kept for 365 days
SECURITY_ACTIONS="('login','logout','password_reset','password_change','permission_change','impersonation_start','impersonation_end','token_revoked','admin_password_reset')"

# Delete non-security events older than 90 days
DELETED_GENERAL=$(docker compose -f "${COMPOSE_FILE}" exec -T "${DB_SERVICE}" \
    psql -U "${DB_USER}" -d "${DB_NAME}" -tAc \
    "DELETE FROM audit_logs
     WHERE action NOT IN ${SECURITY_ACTIONS}
       AND created_at < NOW() - INTERVAL '90 days';
     SELECT ROW_COUNT();" 2>/dev/null | tail -1 || echo "0")

# Delete security events older than 365 days
DELETED_SECURITY=$(docker compose -f "${COMPOSE_FILE}" exec -T "${DB_SERVICE}" \
    psql -U "${DB_USER}" -d "${DB_NAME}" -tAc \
    "DELETE FROM audit_logs
     WHERE action IN ${SECURITY_ACTIONS}
       AND created_at < NOW() - INTERVAL '365 days';
     SELECT ROW_COUNT();" 2>/dev/null | tail -1 || echo "0")

log "Deleted ${DELETED_GENERAL} general audit events (>90 days)"
log "Deleted ${DELETED_SECURITY} security audit events (>365 days)"
log "Audit log cleanup complete."
