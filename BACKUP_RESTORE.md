# Novu Builder — Backup & Restore Runbook

**Co se zálohuje:**
- `postgres_data` Docker volume — relační data (projekty, uživatelé, joby, audit log)
- `storage_data` Docker volume — nahrané fotky a vygenerované exporty (PDF)

**Co se NEZÁLOHUJE (není třeba):**
- `redis_data` — pouze cache a job queue; po obnově se fronta obnoví přirozeně
- Kód a konfigurace — jsou v git repozitáři

---

## Automatický zálohovací skript

Repozitář obsahuje `scripts/backup.sh` — spouštěj ručně nebo z cronu.

```bash
# Jednorázové spuštění
BACKUP_DIR=/backups ./scripts/backup.sh

# S vlastní retencí
RETAIN_DAYS=30 BACKUP_DIR=/backups ./scripts/backup.sh
```

**Výstup zálohy:**
```
/backups/
  db_20260328_020000.sql.gz      ← pg_dump komprimovaný gzip
  storage_20260328_020001.tar.gz ← tar archiv storage_data volume
```

### Cron job (denní záloha ve 2:00)

```bash
# Přidej do crontab -e
0 2 * * * cd /opt/novu-builder && BACKUP_DIR=/backups ./scripts/backup.sh >> /var/log/novu-backup.log 2>&1
```

### Off-site kopie (NUTNÉ pro produkci)

Skript samo o sobě neposílá zálohy mimo host. Přidej rotaci a vzdálené kopírování:

```bash
# Příklad: rsync na zálohovací server
rsync -az --delete /backups/ backup-server:/novu-backups/$(hostname)/

# Příklad: kopie do S3
aws s3 sync /backups/ s3://novu-backups/$(hostname)/ --storage-class STANDARD_IA
```

---

## Manuální záloha DB (těsně před migrací nebo deployem)

```bash
# Záloha s časovým razítkem
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker compose exec db pg_dump -U novu novu_builder \
  | gzip > /backups/db_manual_${TIMESTAMP}.sql.gz

echo "Záloha uložena: /backups/db_manual_${TIMESTAMP}.sql.gz"
ls -lh /backups/db_manual_${TIMESTAMP}.sql.gz   # ověř velikost (nesmí být 0)
```

---

## Restore — PostgreSQL

**Kdy:** Korumpovaná data, selhání migrace, havárie disku

### Postup

```bash
# 1. ZAPIŠ: datum, čas, záloha, ze které se obnovuje, důvod
#    (log incident pro audit trail)

# 2. Stop backend a worker — DB musí být volná pro zápis
docker compose stop backend worker

# 3. Ověř dostupnost zálohy
ls -lh /backups/db_*.sql.gz
# Vyber správný soubor (nejnovější před incidentem)
BACKUP_FILE="/backups/db_20260328_020000.sql.gz"

# 4. Drop a recreate DB
docker compose exec db psql -U novu -c "DROP DATABASE IF EXISTS novu_builder;"
docker compose exec db psql -U novu -c "CREATE DATABASE novu_builder;"

# 5. Restore
gunzip -c $BACKUP_FILE | docker compose exec -T db psql -U novu novu_builder

# 6. Ověř počet tabulek po restore
docker compose exec db psql -U novu novu_builder \
  -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"
# Musí být 15+ tabulek

# 7. Aplikuj čekající migrace (pokud restore je ze starší zálohy)
docker compose run --rm backend alembic upgrade head

# 8. Spusť backend a worker
docker compose start backend worker

# 9. Ověření (viz sekce Validace níže)
```

---

## Restore — Storage (fotky a exporty)

**Kdy:** Ztracené soubory, corrupted volume, přesun na jiný host

```bash
# 1. Stop backend a worker
docker compose stop backend worker

# 2. Vyber zálohu
BACKUP_FILE="/backups/storage_20260328_020001.tar.gz"
ls -lh $BACKUP_FILE   # ověř, že existuje a není prázdná

# 3. Vyčisti a obnov volume
docker run --rm \
  -v novu_builder_storage_data:/data \
  -v /backups:/backup:ro \
  alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/$(basename $BACKUP_FILE) -C /"

# 4. Ověř počet souborů
docker run --rm \
  -v novu_builder_storage_data:/data \
  alpine \
  sh -c "find /data -type f | wc -l"
# Srovnej s počtem fotek v DB (viz validace)

# 5. Spusť backend a worker
docker compose start backend worker
```

---

## Kompletní restore (DB + Storage společně)

Pokud obnovuješ z totální havárie (nový host nebo ztráta obou volumes):

```bash
# Pořadí je důležité:
# 1. DB restore → záloha z TÉHOŽ časového razítka jako storage
# 2. Storage restore → ze stejného časového razítka
# 3. alembic upgrade head (pokud je záloha starší)
# 4. Start backend + worker
# 5. Validace

# POZOR: Pokud zálohy nejsou ze stejného okamžiku:
# - DB je autoritativní (storage_key v DB musí odpovídat souborům ve storage)
# - Chybějící soubory ve storage způsobí 404 při zobrazení fotek, ale APP FUNGUJE
# - Přebývající soubory ve storage (bez záznamu v DB) jsou neškodné (orphans)
```

---

## Validační kroky po obnově

```bash
# 1. Zdraví backendu
curl http://localhost:8000/api/v1/health
# Očekáváno: {"status":"ok",...}

# 2. DB je dostupná a čitelná
docker compose exec db psql -U novu novu_builder \
  -c "SELECT COUNT(*) as organizations FROM organizations;"
docker compose exec db psql -U novu novu_builder \
  -c "SELECT COUNT(*) as users FROM users WHERE is_active=true;"
docker compose exec db psql -U novu novu_builder \
  -c "SELECT COUNT(*) as projects FROM projects;"

# 3. Alembic je na HEAD
docker compose run --rm backend alembic current
# Musí: 20260326_0018 (head)

# 4. Login funguje
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<email>","password":"<heslo>"}' \
  | python -m json.tool | grep accessToken

# 5. Storage je čitelný (alespoň jeden projekt s fotkami)
docker compose exec db psql -U novu novu_builder \
  -c "SELECT p.storage_key FROM project_photos p LIMIT 1;" \
  | grep -v "^-" | grep -v "storage_key" | grep -v "^(" | head -1 | \
  xargs -I{} docker compose exec backend test -f /data/storage/{} \
  && echo "Storage: soubor nalezen" || echo "WARN: soubor nenalezen"

# 6. Worker heartbeat (počkej 90s od startu)
sleep 90
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" GET worker:heartbeat
# Nesmí být prázdné

# 7. Smoke check
python scripts/smoke_check_live.py http://localhost <email> <heslo>
```

---

## Odhad RTO / RPO

| Scénář | Recovery Time (RTO) | Recovery Point (RPO) |
|--------|--------------------|--------------------|
| Worker restart | < 1 min | žádná ztráta dat |
| Backend restart | 1–3 min (healthcheck) | žádná ztráta dat |
| DB restore z denní zálohy | 15–30 min | max. 24 h dat |
| Storage restore z denní zálohy | 10–20 min | max. 24 h fotek |
| Kompletní obnova na novém hostu | 45–90 min | max. 24 h + čas instalace |

**Poznámka:** RTO lze zkrátit zálohou s vyšší frekvencí (každé 4 h) nebo WAL archivingem (PostgreSQL streaming replication). Viz sekce Limity níže.

---

## Limity zálohovací strategie (v0.5.0)

Následující **NENÍ** implementováno a pro produkci je potřeba doplnit:

| Co chybí | Dopad | Jak doplnit |
|----------|-------|-------------|
| Off-site kopie | Záloha na stejném disku jako data — havárie disku = ztráta obou | rsync/S3 cron job |
| Restore drill | Nevíme, jestli záloha je obnovitelná | Měsíční test restore na stagingu |
| WAL archiving | RPO max. 24 h (nebo méně pokud vyšší cron frekvence) | Barman nebo pgBackRest |
| Záloha šifrování | Záloha obsahuje čitelná data | gpg encrypt nebo S3 SSE |
| Monitorování stáří zálohy | Cron může tiše selhávat | Alert pokud záloha > 26 h stará |

---

*Poslední revize: 2026-03-28 | Platí pro v0.5.x*
