#!/usr/bin/env bash
# =============================================================================
# [LEGACY — non-authoritative]
# ops/backup.sh — lokální záloha PostgreSQL + storage souborů
#
# POZOR: Tento skript je LEGACY. Produkuje .sql.gz formát, který je
# deprecated jako autoritativní DB backup formát (od 2026-03-28).
#
# Autoritativní DB backup: ./scripts/backup.sh  (produkuje .pgdump)
# Autoritativní restore:   ./ops/restore.sh <db_TIMESTAMP.pgdump>
#
# Tento skript zůstává zachován pro:
#   - existující .sql.gz zálohy (jejich obnovu viz legacy sekce v ops/restore.sh)
#   - prostředí, kde není možné použít scripts/backup.sh
#
# Použití:
#   ./ops/backup.sh                     # interaktivní
#   BACKUP_DIR=/mnt/backups ./ops/backup.sh   # jiný cíl
#
# Zálohy jsou uchovány po dobu RETENTION_DAYS (výchozí: 14).
# Starší zálohy jsou smazány automaticky.
# =============================================================================
set -euo pipefail

# ── Konfigurace ────────────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-$(dirname "$0")/../backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"

# ── Compose projekt (docker compose -p nebo výchozí název složky) ──────────────
COMPOSE_FILE="$(dirname "$0")/../docker-compose.yml"

# ── Funkce ─────────────────────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

# ── Příprava ────────────────────────────────────────────────────────────────────
mkdir -p "${BACKUP_PATH}"
log "Záloha zahájena → ${BACKUP_PATH}"

# ── 1. PostgreSQL dump ──────────────────────────────────────────────────────────
log "Dumping PostgreSQL..."
docker compose -f "${COMPOSE_FILE}" exec -T db \
    pg_dump -U novu novu_builder \
    | gzip > "${BACKUP_PATH}/postgres_${TIMESTAMP}.sql.gz" \
  || die "pg_dump selhal"
log "PostgreSQL dump hotov: postgres_${TIMESTAMP}.sql.gz"

# ── 2. Storage snapshot (volitelné — pouze pokud volume je přístupný) ───────────
STORAGE_SOURCE="$(dirname "$0")/../storage"
if [ -d "${STORAGE_SOURCE}" ]; then
    log "Záloha storage souborů..."
    tar -czf "${BACKUP_PATH}/storage_${TIMESTAMP}.tar.gz" \
        -C "${STORAGE_SOURCE}" . \
      || die "tar storage selhal"
    log "Storage snapshot hotov: storage_${TIMESTAMP}.tar.gz"
else
    log "Storage adresář '${STORAGE_SOURCE}' nenalezen — přeskakuji (Docker volume)."
    log "Pro zálohu Docker volume spusť:"
    log "  docker run --rm -v novu_builder_storage_data:/data -v \$(pwd)/backups:/out alpine tar czf /out/storage_${TIMESTAMP}.tar.gz -C /data ."
fi

# ── 3. Rotace starých záloh ──────────────────────────────────────────────────────
log "Mazání záloh starších než ${RETENTION_DAYS} dní..."
find "${BACKUP_DIR}" -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -exec rm -rf {} + 2>/dev/null || true

# ── 4. Souhrn ────────────────────────────────────────────────────────────────────
BACKUP_SIZE="$(du -sh "${BACKUP_PATH}" 2>/dev/null | cut -f1)"
log "Záloha dokončena. Velikost: ${BACKUP_SIZE}. Cesta: ${BACKUP_PATH}"

# =============================================================================
# RESTORE — pokyny (nespouštět automaticky, pouze manuálně)
#
# 1. Obnova PostgreSQL ze zálohy:
#   gunzip -c backups/TIMESTAMP/postgres_TIMESTAMP.sql.gz \
#     | docker compose exec -T db psql -U novu novu_builder
#
# 2. Obnova storage souborů (bind-mount varianta):
#   tar -xzf backups/TIMESTAMP/storage_TIMESTAMP.tar.gz -C storage/
#
# 3. Obnova storage souborů (Docker volume varianta):
#   docker run --rm \
#     -v novu_builder_storage_data:/data \
#     -v $(pwd)/backups/TIMESTAMP:/backup \
#     alpine tar xzf /backup/storage_TIMESTAMP.tar.gz -C /data
#
# Po obnově restartuj backend a worker:
#   docker compose restart backend worker
# =============================================================================
