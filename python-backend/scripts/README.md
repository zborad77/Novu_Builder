# Database scripts

## Migrace

```bash
cd python-backend

# Aplikovat všechny migrace na aktuální DB
alembic upgrade head

# Zkontrolovat stav
alembic current

# Historie
alembic history --verbose
```

---

## Záloha

**Autoritativní backup entrypoint** pro produkci je `scripts/backup.sh` v kořeni projektu
(produkuje `.pgdump` + `.sha256`, používá `docker compose exec db` — nevyžaduje pg_dump na hostu).

Skripty níže jsou **alternativní cesta** pro případy, kdy je potřeba přímé pg připojení
(bez Docker Compose), nebo pro lokální vývoj.

```bash
# Záloha přes přímé pg připojení (vyžaduje pg_dump nainstalovaný na hostu)
# Zálohy se ukládají do python-backend/backups/ — JINÝ adresář než scripts/backup.sh
./scripts/backup_db.sh

# S explicitním env (produkce)
APP_ENV=production ./scripts/backup_db.sh

# Zálohy starší než 14 kusů se automaticky mažou (BACKUP_KEEP=14)
```

Výstup: `python-backend/backups/novu_TIMESTAMP.pgdump` + `.sha256`

---

## Restore

```bash
# POZOR: smaže a přepíše celou DB
# Pro Docker Compose produkci použij raději: ./ops/restore.sh <backup.pgdump>
./scripts/restore_db.sh backups/novu_20260324_120000.pgdump

# Bez potvrzovacího promptu (pro CI/automatizaci)
./scripts/restore_db.sh backups/novu_20260324_120000.pgdump --yes
```

---

## Ověření zálohy (bez rizika)

```bash
# Obnoví zálohu do dočasné DB, ověří strukturu a schema, pak DB zahodí
# Vyžaduje: psql, pg_restore na hostu + DATABASE_URL v python-backend/.env
./scripts/verify_restore.sh backups/novu_20260324_120000.pgdump
```

Viz také: `BACKUP_RESTORE.md` pro celkový přehled workflow.

---

## Cron záloha

> Pokud používáš Docker Compose produkci, preferuj cron přes `scripts/backup.sh`
> (kořen projektu) — nevyžaduje pg_dump na hostu.

Alternativní cron přes přímé pg připojení:

```cron
# Každý den ve 2:00 — flock zabrání spuštění duplicitního jobu
0 2 * * * APP_ENV=production flock -n /tmp/novu_backup.lock /opt/novu/python-backend/scripts/backup_db.sh >> /var/log/novu/backup.log 2>&1

# Ověření každý týden v neděli ve 3:00
0 3 * * 0 APP_ENV=production /opt/novu/python-backend/scripts/verify_restore.sh \
  $(ls -t /opt/novu/python-backend/backups/*.pgdump | head -1) >> /var/log/novu/verify.log 2>&1
```
