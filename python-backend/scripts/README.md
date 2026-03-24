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

## Záloha

```bash
# Záloha dev DB
./scripts/backup_db.sh

# Záloha produkce
APP_ENV=production ./scripts/backup_db.sh

# Zálohy se ukládají do python-backend/backups/
# Starší než 14 kusů se automaticky mažou (BACKUP_KEEP=14)
```

## Restore

```bash
# POZOR: smaže a přepíše celou DB
./scripts/restore_db.sh backups/novu_20260324_120000.pgdump

# Bez potvrzovacího promptu (pro CI/automatizaci)
./scripts/restore_db.sh backups/novu_20260324_120000.pgdump --yes
```

## Ověření zálohy (bez rizika)

```bash
# Obnoví zálohu do dočasné DB, ověří integritu a schema, pak DB zahodí
./scripts/verify_restore.sh backups/novu_20260324_120000.pgdump
```

## Cron záloha (příklad)

```cron
# Každý den ve 2:00 — flock zabrání spuštění duplicitního jobu
0 2 * * * APP_ENV=production flock -n /tmp/novu_backup.lock /opt/novu/python-backend/scripts/backup_db.sh >> /var/log/novu/backup.log 2>&1

# Ověření každý týden v neděli ve 3:00
0 3 * * 0 APP_ENV=production /opt/novu/python-backend/scripts/verify_restore.sh \
  $(ls -t /opt/novu/python-backend/backups/*.pgdump | head -1) >> /var/log/novu/verify.log 2>&1
```
