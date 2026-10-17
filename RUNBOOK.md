# Novu Builder — Incident Runbook

**Platí pro:** v0.5.x, single-host Docker Compose deployment
**Stack:** FastAPI + PostgreSQL 16 + Redis 7 + nginx + worker process

Každý incident má strukturu: **Příznaky → Diagnóza → Náprava → Ověření → Prevence**

---

## INCIDENT-01: Worker Down

### Příznaky
- Analýzy zůstávají ve stavu `queued` a nikdy nepřejdou do `running`
- `GET /api/v1/health/internal` vrací `worker.alive: false`
- `docker compose ps worker` vrací `Exited` nebo kontejner chybí

### Diagnóza
```bash
docker compose ps worker
docker compose logs --tail=50 worker
# Zkontroluj konkrétní chybu (OOM, crash, chybějící env var)
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" GET worker:heartbeat
# Prázdný výstup = worker nepsal heartbeat déle než 90 s
```

### Náprava
```bash
# Restart workeru
docker compose restart worker

# Pokud opakovaně padá:
docker compose logs worker --tail=100   # zjistit root cause
docker compose up -d worker             # nový kontejner

# Pokud je fronta zahlcena, zkontroluj délku
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" LLEN job_queue
```

### Ověření
```bash
# Heartbeat se obnoví do 30 s
sleep 60 && docker compose exec redis redis-cli -a "$REDIS_PASSWORD" GET worker:heartbeat
# Existující 'queued' joby se zpracují (zkontroluj v DB nebo přes API)
```

### Prevence
- `restart: unless-stopped` je v docker-compose nastaven — kontejner se restartuje automaticky po crashi
- Nakonfigurovat alert: `novu_worker_alive == 0` po dobu > 2 minut

---

## INCIDENT-02: Redis Nedostupný

### Příznaky
- `docker compose logs backend` ukazuje Redis connection refused/timeout
- Rate limiting nefunguje (žádné 429 odpovědi)
- Worker nemůže číst ze queue (joby zaseknuty v `queued`)
- Varování v logu: `rate_limiter.disabled` nebo `redis.connection_error`

### Diagnóza
```bash
docker compose ps redis
docker compose logs --tail=50 redis
# Test připojení
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" ping
# Pokud redis kontejner neběží:
docker compose up -d redis
```

### Náprava
Redis **není** kritická závislost pro čtení dat — backend degraduje gracefully:
- Cache miss (pricebooks/suppliers se načtou přímo z DB)
- Rate limiting je dočasně vypnut
- Worker nemůže zpracovávat joby

```bash
# Restart Redis
docker compose restart redis

# Ověř, že data jsou zachována (Redis persistence je výchozí)
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" DBSIZE
```

### Ověření
```bash
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" ping   # PONG
docker compose logs backend --tail=20                           # žádné Redis chyby
```

### Prevence
- `restart: unless-stopped` v docker-compose
- Redis má defaultní `appendonly yes` — data přežijí restart
- Alert na `container/service Redis` down

---

## INCIDENT-03: DB Nedostupná

### Příznaky
- `GET /api/v1/health` vrací `{"status": "degraded"}`
- `novu_db_alive 0.0` v Prometheus metrikách
- Všechny API requesty vracejí 500 nebo 503
- `docker compose logs backend` ukazuje `asyncpg.exceptions.TooManyConnectionsError` nebo `ConnectionRefusedError`

### Diagnóza
```bash
docker compose ps db
docker compose logs --tail=50 db
docker compose exec db pg_isready -U novu -d novu_builder
# Zkontroluj místo na disku (nejčastější příčina pádu Postgres)
df -h /var/lib/docker/volumes
du -sh /var/lib/docker/volumes/novu_builder_postgres_data
```

### Náprava — Postgres běží, ale je problém s připojením
```bash
docker compose restart db
# Počkej na healthcheck
docker compose ps  # db musí být healthy
```

### Náprava — Disk plný
```bash
# POZOR: nevymaž data nekriticky, nejdřív uvolni log soubory
# Identifikuj velké soubory
find /var/lib/docker -size +100M -type f 2>/dev/null | sort -k1 -h
# Vyčisti stará Docker images
docker image prune -f
```

### Náprava — Korumpovaná data (krajní případ)
```bash
# ZAPIŠ DO LOGU: datum, čas, rozsah incidentu
# Přepni na zálohu (viz BACKUP_RESTORE.md — DB restore)
```

### Ověření
```bash
docker compose exec db pg_isready -U novu -d novu_builder
curl http://localhost:8000/api/v1/health | python -m json.tool
# novu_db_alive 1.0 v /api/v1/metrics
```

### Prevence
- Nastavit alerting na volné místo na disku (`< 20% volných`)
- Pravidelné zálohy (viz BACKUP_RESTORE.md)

---

> Production note:
> For `APP_ENV=production` with `STORAGE_BACKEND=s3`, this repo does not
> implement production media restore. Any references below to local storage
> files or `storage_data` volume apply to local/dev compatibility only.
> The authoritative production boundary is defined in [BACKUP_RESTORE.md](BACKUP_RESTORE.md).

## INCIDENT-04: Storage Failure (foto/exporty)

### Příznaky
- Upload fotek selže s 500
- `GET /mock-storage/{key}` vrací 404 nebo 500
- `docker compose exec backend ls /data/storage` selhává nebo vrací prázdno
- Backend log: `FileNotFoundError` nebo `PermissionError`

### Diagnóza
```bash
# Zkontroluj volume mount
docker compose exec backend df -h /data/storage
docker compose exec backend ls -la /data/storage

# Zkontroluj oprávnění
docker compose exec backend stat /data/storage

# Zkontroluj místo
df -h /var/lib/docker/volumes/novu_builder_storage_data
```

### Náprava — Volume nenamontován
```bash
docker compose down backend worker
docker compose up -d backend worker
# Volume se automaticky remountuje
```

### Náprava — Chybějící soubory (poškozená data)
```bash
# Restore z zálohy (viz BACKUP_RESTORE.md — Storage restore)
```

### Ověření
```bash
docker compose exec backend python -c "
import pathlib, os
root = os.environ.get('STORAGE_ROOT', '/data/storage')
p = pathlib.Path(root) / 'health_test.txt'
p.write_text('ok')
print('Write OK:', p.read_text())
p.unlink()
print('Storage read/write OK')
"
```

### Prevence
- Denní záloha `storage_data` volume
- Monitoring volného místa

---

## INCIDENT-05: Selhání Migrace

### Příznaky
- Backend se nespustí, log obsahuje: `alembic.util.exc.CommandError: Can't locate revision identified by...`
- nebo: `ERROR: column "xyz" of relation does not exist`
- `alembic current` nevrací `(head)`

### Diagnóza
```bash
docker compose run --rm backend alembic current
docker compose run --rm backend alembic history --verbose
# Zjisti rozdíl mezi aktuální revizí a HEAD
docker compose run --rm backend alembic show 20260326_0018
```

### Náprava — Migrace nebyla spuštěna před deployem
```bash
# POZOR: Nejdřív záloha!
docker compose run --rm backend python -m app.db.session  # ověř připojení
docker compose run --rm backend alembic upgrade head
docker compose restart backend worker
```

### Náprava — Migrace selhala napůl (dirty state)
```bash
# Zobraz aktuální stav
docker compose run --rm backend alembic current
# Pokud je revize jako "dirty" nebo "failed":
# 1. Ruční oprava v DB (nebezpečné, zápiš každý krok)
# nebo
# 2. Restore z zálohy před migrací (bezpečnější)
docker compose run --rm backend alembic stamp <předchozí-revize>
# Pak vyřeš root cause, pak upgrade
```

### Náprava — Rollback migrace
```bash
# Downgrade o jeden krok zpět
docker compose run --rm backend alembic downgrade -1
# POZOR: Downgrade může ztratit data (DROP COLUMN). Vždy mít zálohu!
```

### Ověření
```bash
docker compose run --rm backend alembic current
# Musí skončit na: 20260326_0018 (head)
curl http://localhost:8000/api/v1/health
```

### Prevence
- Vždy záloha DB těsně před migrací
- Migraci testovat v staging prostředí
- V CI pipeline: `alembic check` jako gate

---

## INCIDENT-06: Degraded Health (`/health` vrací `"status": "degraded"`)

### Příznaky
- `GET /api/v1/health` vrací `{"status": "degraded"}`
- Prometheus: `novu_db_alive 0.0`

### Diagnóza
```bash
# Zobrazí detailní stav (vyžaduje superadmin token + interní IP)
curl -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
     http://localhost:8000/api/v1/health/internal | python -m json.tool

# Klíčová pole v odpovědi:
# "db": "ok" / "error"
# "worker": {"alive": true/false}
# "startupChecks": {...}
# "jobs": {"running": N, "queued": N}
```

### Náprava
- `db: error` → viz INCIDENT-03
- `worker.alive: false` → viz INCIDENT-01
- `startupChecks` selhávají → `docker compose logs backend` pro konkrétní selhání

### Ověření
```bash
curl http://localhost:8000/api/v1/health   # {"status":"ok"}
```

---

## INCIDENT-07: Vysoká Chybovost (High Error Rate)

### Příznaky
- Prometheus: `rate(http_requests_total{status_code=~"5.."}[5m])` stoupá
- Uživatelé hlásí "500 Internal Server Error"
- Backend log plný ERROR/CRITICAL zpráv

### Diagnóza
```bash
# Real-time logy s filtrováním na chyby
docker compose logs -f backend 2>&1 | grep -E "ERROR|CRITICAL|500|traceback" | head -50

# Metriky pro diagnostiku
curl -H "Authorization: Bearer $METRICS_TOKEN" \
     http://localhost:8000/api/v1/metrics \
     | grep http_requests_total | grep -v "^#"

# Joby v chybném stavu
docker compose exec db psql -U novu novu_builder \
  -c "SELECT status, COUNT(*) FROM analysis_jobs GROUP BY status;"
```

### Náprava — Memory/resource exhaustion
```bash
docker stats  # sleduj využití paměti backend/worker kontejnerů
docker compose restart backend worker
```

### Náprava — Chyba v konkrétním endpointu
```bash
# Najdi nejčastější chybu v logu
docker compose logs backend --tail=500 2>&1 | grep "500" | sort | uniq -c | sort -rn | head-20
# Identifikuj problematický endpoint a příčinu, pak nasaď fix nebo rollback
```

### Ověření
```bash
# Chybovost by měla klesnout pod 1%
curl http://localhost:8000/api/v1/alive  # 200
```

---

## INCIDENT-08: Token / Auth Anomálie

### Příznaky
- Uživatelé hlásí, že jsou náhle odhlášeni bez vlastní akce
- Audit log ukazuje neočekávané `access_denied` nebo `auth_failure` záznamy
- Podezřelé přihlášení ze zahraničních IP adres

### Diagnóza
```bash
# Prohlédni audit log pro podezřelé záznamy
docker compose exec db psql -U novu novu_builder \
  -c "SELECT action, user_id, ip_address, created_at
      FROM audit_logs
      WHERE action LIKE 'auth%' OR action LIKE 'access_denied%'
      ORDER BY created_at DESC
      LIMIT 50;"

# Zkontroluj počet aktivních revokovaných tokenů
docker compose exec db psql -U novu novu_builder \
  -c "SELECT COUNT(*) FROM revoked_tokens WHERE expires_at > NOW();"

# Zkontroluj tokens_valid_after pro podezřelého uživatele
docker compose exec db psql -U novu novu_builder \
  -c "SELECT id, email, tokens_valid_after FROM users WHERE email = 'user@example.com';"
```

### Náprava — Kompromitovaný uživatelský účet
```bash
# 1. Okamžitá invalidace všech tokenů uživatele (přes admin API):
curl -X POST \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"password": "<nové-dočasné-heslo>"}' \
  https://<host>/api/v1/admin/users/<user_id>/reset-password

# 2. Deaktivace účtu (přes admin API) pokud je to nutné:
curl -X PATCH \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"isActive": false}' \
  https://<host>/api/v1/admin/users/<user_id>
```

### Náprava — Kompromitovaný JWT_SECRET
```bash
# EXTRÉMNĚ ZÁVAŽNÝ INCIDENT — invaliduje VŠECHNY tokeny všech uživatelů
# 1. Záloha DB
# 2. Vygeneruj nový JWT_SECRET: openssl rand -hex 32
# 3. Aktualizuj .env.production
# 4. docker compose up -d --force-recreate backend worker
# 5. Informuj všechny uživatele, že se musí znovu přihlásit
```

### Ověření
```bash
# Ověř, že starý token daného uživatele přestane fungovat
curl -H "Authorization: Bearer <starý-token>" \
     https://<host>/api/v1/auth/me   # musí vrátit 401
```

### Prevence
- Pravidelně prohlížet audit log (`audit_logs` tabulka)
- Nastavit alert na `> 10 auth_failure za minutu`
- JWT tokeny expirují po 60 minutách — omezuje škodu při úniku

---

## Rychlý přehled diagnózy

| Příznak | První krok |
|---------|-----------|
| Backend neodpovídá | `docker compose ps` + `docker compose logs backend` |
| `/health` = degraded | `curl localhost:8000/api/v1/health/internal` s superadmin tokenem |
| Joby zaseknuté | `docker compose ps worker` + `docker compose logs worker` |
| 502 z nginx | `docker compose ps backend` — nejspíš healthcheck selhává |
| Migrace selhala | `docker compose run --rm backend alembic current` |
| Redis problém | `docker compose exec redis redis-cli -a "$REDIS_PASSWORD" ping` |
| DB problém | `docker compose exec db pg_isready -U novu` |
| Auth selhání | Audit log v DB: `SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 20` |

---

*Poslední revize: 2026-03-28 | Platí pro v0.5.x*
