# Novu Builder — Operations Runbook

> Tento dokument popisuje postup řešení provozních incidentů.
> Všechny příkazy předpokládají spuštění z kořenového adresáře projektu
> (složka s `docker-compose.yml`), pokud není uvedeno jinak.

---

## Obsah

1. [DB DOWN — PostgreSQL nedostupná](#1-db-down--postgresql-nedostupná)
2. [REDIS DOWN — Redis nedostupný](#2-redis-down--redis-nedostupný)
3. [WORKER STUCK — Worker zpracovává nebo visí](#3-worker-stuck--worker-zpracovává-nebo-visí)
4. [DISK FULL — Disk je zaplněný](#4-disk-full--disk-je-zaplněný)
5. [BACKUP FAIL — Záloha selhala](#5-backup-fail--záloha-selhala)
6. [RESTORE POSTUP — Obnova z zálohy](#6-restore-postup--obnova-z-zálohy)

---

## 1. DB DOWN — PostgreSQL nedostupná

### Jak ověřit

```bash
# Stav kontejneru
docker compose ps db

# Přímý ping na DB
docker compose exec db psql -U novu -d novu_builder -c "SELECT 1;"

# Logy DB kontejneru (posledních 50 řádků)
docker compose logs --tail=50 db

# Stav backendu — health endpoint
curl -sf http://localhost:8000/api/v1/health || echo "BACKEND UNHEALTHY"
```

**Typické příznaky:**
- `docker compose ps db` ukazuje `Exit` nebo `Restarting`
- Backend vrací HTTP 503 nebo chyby spojení
- V logách backendu: `sqlalchemy.exc.OperationalError`, `could not connect to server`

### Jak restartovat

```bash
# 1. Restart DB kontejneru
docker compose restart db

# 2. Počkej na start (obvykle 5–15 s)
sleep 10

# 3. Ověř dostupnost
docker compose exec db psql -U novu -d novu_builder -c "SELECT version();"

# 4. Restart backendu a workeru (pokud nenavázali spojení sami)
docker compose restart backend worker
```

### Fallback — DB trvale nedostupná

Pokud restart nepomůže:

```bash
# 1. Zjisti příčinu z logů
docker compose logs db | grep -i "error\|fatal\|panic" | tail -20

# 2. Zkontroluj místo na disku (časté: Docker volume plný)
df -h
docker system df

# 3. Pokud je volume poškozen — obnov z zálohy
# Viz sekce 6. RESTORE POSTUP
```

---

## 2. REDIS DOWN — Redis nedostupný

### Jak ověřit

```bash
# Stav kontejneru
docker compose ps redis

# Ping Redis
docker compose exec redis redis-cli ping
# Očekávaná odpověď: PONG

# Logy
docker compose logs --tail=30 redis
```

**Typické příznaky:**
- Worker nepřijímá joby (BLPOP nefunguje)
- V logách workeru: `ConnectionError`, `redis.exceptions.ConnectionError`
- Přihlášení funguje, ale analýzy se nezařadí do fronty

### Jak restartovat

```bash
# Restart Redis
docker compose restart redis

# Ověř
docker compose exec redis redis-cli ping

# Restart workeru (worker si znovu naváže spojení)
docker compose restart worker

# Zkontroluj heartbeat workeru
docker compose exec redis redis-cli get novu:worker:heartbeat
# Mělo by vrátit ISO timestamp < 60 s zpátky
```

### Dopad a dočasný fallback

Redis DOWN **neblokuje čtení dat ani přihlášení** — backend tyto cesty obsluhuje bez Redis. Joby analýzy se nezařazují do fronty (vrátí 202, ale worker je nenačte). Po restartu Redis worker automaticky obnoví zpracování čekajících jobů z fronty.

---

## 3. WORKER STUCK — Worker zpracovává nebo visí

### Jak ověřit

```bash
# Stav kontejneru workeru
docker compose ps worker

# Heartbeat — timestamp posledního tick
docker compose exec redis redis-cli get novu:worker:heartbeat
# Pokud je starší než 60 s nebo chybí → worker visí

# Aktuální stav jobů v DB
docker compose exec db psql -U novu novu_builder \
  -c "SELECT id, status, started_at, project_id FROM analysis_jobs WHERE status IN ('queued','running') ORDER BY created_at DESC LIMIT 10;"

# Logy workeru
docker compose logs --tail=100 worker
```

**Typické příznaky:**
- Job je v `running` stavu déle než 3 minuty (`_JOB_TIMEOUT_SECONDS = 180`)
- Heartbeat chybí nebo je starý > 60 s
- Worker kontejner restartoval (`Restarting`)

### Jak uvolnit stuck joby

```bash
# 1. Restart workeru (při startu automaticky označí 'running' joby jako 'failed')
docker compose restart worker

# 2. Ověř, že joby byly ošetřeny
docker compose exec db psql -U novu novu_builder \
  -c "SELECT id, status, error_message FROM analysis_jobs WHERE status = 'running';"
# Výsledek musí být prázdný

# 3. Pokud job zůstal v 'running', oprav ručně
docker compose exec db psql -U novu novu_builder \
  -c "UPDATE analysis_jobs SET status='failed', error_message='Manual operator recovery', finished_at=NOW() WHERE status='running';"
```

### Opakovaně selhávající joby

```bash
# Joby s vysokým retry_count
docker compose exec db psql -U novu novu_builder \
  -c "SELECT id, retry_count, error_message FROM analysis_jobs WHERE status='failed' ORDER BY retry_count DESC LIMIT 5;"
```

Maximální počet pokusů je `_MAX_JOB_RETRY_COUNT = 10`. Po překročení je job označen jako dead-letter a nevytváří nový pokus.

---

## 4. DISK FULL — Disk je zaplněný

### Jak ověřit

```bash
# Celkové místo
df -h

# Docker volumes a images
docker system df -v

# Největší adresáře v projektu
du -sh /opt/novu-builder/backups/*  2>/dev/null | sort -rh | head -10
du -sh storage/*                    2>/dev/null | sort -rh | head -10
```

### Uvolnění místa

```bash
# 1. Pruning starých Docker artefaktů (nepoužívané images, volumes, sítě)
docker system prune -f

# 2. Ruční pruning starých záloh (backup.sh drží defaultně posledních 7 dní)
# Ověř, co chceš mazat PŘED smazáním:
ls -lth backups/ | head -20
# Pak smaž ručně starší soubory:
find backups/ -name "*.pgdump" -mtime +14 -ls   # nejdřív jen zobraz
find backups/ -name "*.pgdump" -mtime +14 -delete
find backups/ -name "*.pgdump.sha256" -mtime +14 -delete
find backups/ -name "manifest_*.json" -mtime +14 -delete
find backups/ -name "storage_*.tar.gz" -mtime +14 -delete

# 3. Vyčisti ztracené/osiřelé foto soubory (pokud storage narostl)
# POZOR: pouze pokud víš, co mažeš — konzultuj s vývojářem
```

### Preventivní opatření

- Nastavit cron pro `backup.sh` s `RETAIN_DAYS=7` (default)
- Monitorovat `df -h` přes alerting systém
- Offsite sync: nastavit `BACKUP_REMOTE=user@host:/remote/backups` v env

---

## 5. BACKUP FAIL — Záloha selhala

### Jak ověřit příčinu

```bash
# Ruční spuštění zálohy s verbose výstupem
cd /opt/novu-builder
BACKUP_DIR=./backups ./scripts/backup.sh 2>&1 | tee /tmp/backup_debug.log

# Zkontroluj výstup
cat /tmp/backup_debug.log | grep -i "error\|warning\|failed"
```

**Typické příčiny:**

| Symptom | Příčina | Řešení |
|---|---|---|
| `ERROR: DB file missing or empty` | pg_dump selhal (DB nedostupná) | Ověř DB, viz sekce 1 |
| `ERROR: DB dump too small (<1KB)` | Prázdný dump (prázdná DB nebo chyba spojení) | Zkontroluj `docker compose exec db pg_dump ...` ručně |
| `WARNING: alembic head unknown` | Alembic migrace neproběhly nebo DB starší | Neblokuje zálohu, ale manifest bude mít `"alembic_head": "unknown"` |
| `ERROR: Another backup is already running` | Advisory lock — předchozí záloha stále běží nebo zamknuta | `rm /tmp/novu_backup.lock` a spusť znovu |
| `⚠ WARNING: remote sync failed` | rsync / SSH na BACKUP_REMOTE selhal | Lokální záloha je OK; oprav SSH klíče nebo síť |
| `disk quota exceeded` | Plný disk | Viz sekce 4 |

### Ověření existující zálohy

```bash
# Výpis posledních záloh
ls -lth backups/*.pgdump | head -10

# Ověření checksum konkrétní zálohy
sha256sum -c backups/db_YYYYMMDD_HHMMSS.pgdump.sha256

# Kontrola manifest souboru
cat backups/manifest_YYYYMMDD_HHMMSS.json
```

---

## 6. RESTORE POSTUP — Obnova z zálohy

> Podrobný postup viz [BACKUP_RESTORE.md](BACKUP_RESTORE.md).

### Rychlý přehled kroků

```bash
# Interaktivní restore (doporučeno)
./ops/restore.sh backups/db_YYYYMMDD_HHMMSS.pgdump

# Unattended restore (CI / recovery bez interakce)
./ops/restore.sh backups/db_YYYYMMDD_HHMMSS.pgdump --yes

# Bypass verify (jen pokud verify script není dostupný)
./ops/restore.sh backups/db_YYYYMMDD_HHMMSS.pgdump --yes --skip-verify
```

**Pořadí kroků, které skript provede:**
1. Ověří manifest + checksum
2. Spustí `verify_restore.sh` (non-destructivní kontrola v temp DB)
3. Zastaví backend + worker
4. Dropne a vytvoří novou DB
5. Obnoví data přes `pg_restore`
6. Ověří kritické tabulky + alembic_version
7. Aplikuje pending Alembic migrace (`alembic upgrade head`)
8. Spustí backend + worker
9. Polluje health endpoint

---

*Poslední aktualizace: 2026-03-29*
