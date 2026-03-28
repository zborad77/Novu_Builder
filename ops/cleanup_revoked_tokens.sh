#!/usr/bin/env bash
# =============================================================================
# cleanup_revoked_tokens.sh — maže expirované záznamy z tabulky revoked_tokens
#
# Tokeny jsou expirované, jakmile jejich expires_at < NOW(). Smazání těchto
# záznamů je bezpečné: revokace funguje na principu "záznamu v DB" — pokud
# token expiroval, JWT middleware ho stejně odmítne kvůli exp poli.
#
# Použití:
#   ./ops/cleanup_revoked_tokens.sh
#
# Cron (každou noc ve 3:00):
#   0 3 * * * /path/to/project/ops/cleanup_revoked_tokens.sh >> /var/log/novu-cleanup.log 2>&1
#
# Retention poznámka:
#   Tato operace maže POUZE záznamy, kde expires_at < NOW().
#   Aktivní revokace (token ještě nevypršel) NEJSOU smazány.
# =============================================================================
set -euo pipefail

COMPOSE_FILE="$(dirname "$0")/../docker-compose.yml"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "Spouštím cleanup revoked_tokens..."

DELETED=$(docker compose -f "${COMPOSE_FILE}" exec -T db \
    psql -U novu novu_builder -t -A -c \
    "WITH deleted AS (DELETE FROM revoked_tokens WHERE expires_at < NOW() RETURNING jti) SELECT count(*) FROM deleted;" \
  2>/dev/null | tr -d '[:space:]' || echo "unknown")

log "Hotovo. Smazáno záznamů: ${DELETED}"
