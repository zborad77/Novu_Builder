# Novu Builder — Deployment & Rollback

**Stack:** Docker Compose (db + redis + backend + nginx + worker)
**Migrace:** Alembic — spouštěj ručně, NIKDY se neaplikují automaticky při startu

---

## První nasazení (fresh install)

### 1. Příprava prostředí

```bash
# Klonuj repozitář
git clone <repo-url> /opt/novu-builder
cd /opt/novu-builder

# Vytvoř produkční env soubor
cp .env.production.example .env.production
```

Vyplň `.env.production` (viz RELEASE_CHECKLIST.md, sekce 0):
```bash
# Vygeneruj bezpečné hodnoty
POSTGRES_PASSWORD=$(openssl rand -hex 32)
REDIS_PASSWORD=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
METRICS_AUTH_TOKEN=$(openssl rand -hex 32)
```

Production values that must be filled before `docker compose up`:

- `APP_BASE_URL` - deployed client URL, must not point to localhost/example domains
- `CORS_ALLOWED_ORIGINS` - deployed browser origins, comma-separated when needed
- `METRICS_AUTH_ENABLED=true`
- `METRICS_AUTH_TOKEN` - strong bearer token for `/api/v1/metrics`
- `STORAGE_BACKEND=s3`
- `S3_BUCKET` - real object-storage bucket/container name
- `S3_REGION` - set explicitly when not using the default

Optional S3 wiring:

- `S3_ENDPOINT_URL` for S3-compatible providers
- `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` together, or leave both unset for IAM/instance-role auth
- `S3_CDN_BASE_URL` when public media should resolve through a CDN

Note: `docker-compose.yml` still mounts `storage_data` for compatibility, but
when `STORAGE_BACKEND=s3` it is not the production source of uploaded media.

### 2. SSL certifikáty

```bash
mkdir -p nginx/certs
# Self-signed pro interní pilot:
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/key.pem \
  -out nginx/certs/cert.pem \
  -subj "/CN=novu-builder"
# Pro produkci: použij Let's Encrypt nebo certifikát od CA
```

### 3. Spuštění DB a Redis

```bash
docker compose --env-file .env.production up -d db redis
# Počkej na healthcheck
docker compose ps   # db a redis musí být "healthy"
```

### 4. Aplikace migrací

```bash
docker compose --env-file .env.production run --rm backend alembic upgrade head
# Musí skončit bez chyby a vypsat: Running upgrade ... -> 20260326_0018
docker compose --env-file .env.production run --rm backend alembic current
# Musí vrátit: 20260326_0018 (head)
```

### 5. Spuštění zbývajících služeb

```bash
docker compose --env-file .env.production up -d
docker compose ps   # všechny služby "running" nebo "healthy"
```

### 6. Ověření

```bash
# Liveness
curl -f https://localhost/api/v1/alive

# Public liveness
curl -k https://localhost/api/v1/health
curl -k https://localhost/api/v1/ready
# /health â†’ {"status":"ok","service":"python-backend"}
curl -k https://localhost/api/v1/ready
# /ready â†’ {"status":"ready","service":"python-backend"}
# Očekávané: {"status":"ok","service":"python-backend",...}

# Smoke check
python scripts/verify_deploy.py --base-url https://localhost --auth-email <email> --auth-password <password>
```

---

## Upgrade (nová verze aplikace)

### Před upgradema

```bash
# 1. Záloha DB těsně před deployem
BACKUP_DIR=/backups ./scripts/backup.sh

# 2. Zkontroluj, jestli jsou čekající migrace
docker compose --env-file .env.production run --rm backend alembic check
# "New upgrade operations detected" = bude potřeba migrace
```

### Postup upgradu

```bash
# 1. Stáhni nový kód
cd /opt/novu-builder
git pull origin main   # nebo konkrétní tag: git checkout v0.6.0

# 2. Buil nové image
docker compose --env-file .env.production build backend

# 3. STOP backend a worker (DB a Redis běží dál)
docker compose --env-file .env.production stop backend worker

# 4. Aplikuj migrace (pokud existují)
docker compose --env-file .env.production run --rm backend alembic upgrade head

# 5. Start nových kontejnerů
docker compose --env-file .env.production up -d backend worker

# 6. Ověření (viz níže)
```

### Post-deploy ověření

```bash
# a) Zdraví
curl -k https://localhost/api/v1/health
# Musí vrátit "status":"ok"

# b) Verze/prostředí
curl -k https://localhost/api/v1/

# c) Worker heartbeat (počkej 60s)
sleep 60
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" GET worker:heartbeat

# d) Smoke check
python scripts/verify_deploy.py --base-url https://localhost --auth-email <email> --auth-password <pass>

# Bezpecny wrapper pro preflight + explicitni migraci + post-deploy verification
python scripts/verify_release_gate.py --base-url https://localhost --apply-migrations --auth-email <email> --auth-password <pass>

# e) Zkontroluj logy na chyby
docker compose logs backend --tail=50 | grep -E "ERROR|CRITICAL"
docker compose logs worker --tail=50 | grep -E "ERROR|CRITICAL"
```

---

## Rollback

### Kdy rollbackovat

- Backend vrací > 5 % 5xx odpovědí po deployi
- `/health` hlásí `degraded` a příčina je v nové verzi
- Nová verze selhala při post-deploy ověření

### Postup rollback (bez migrace zpět)

Nejčastější případ — nová verze má bug v kódu, ale migrace byly kompatibilní:

```bash
# 1. Stop nových kontejnerů
docker compose --env-file .env.production stop backend worker

# 2. Přepni na předchozí image
#    Pokud jsi buildil s tagem:
docker compose --env-file .env.production up -d --no-build backend worker
#    Nebo: upravte docker-compose.yml na předchozí image tag a:
docker compose --env-file .env.production up -d backend worker

# 3. Ověření
curl -k https://localhost/api/v1/health
```

### Rollback s migrací zpět (NEBEZPEČNÉ)

Pouze pokud migrace přidala/odebrala sloupce, které způsobují problém:

```bash
# POZOR: downgrade může smazat data (DROP COLUMN)!
# VŽDY mít zálohu z před upgradu.

# 1. Zjisti cílovou revizi
docker compose run --rm backend alembic history --verbose | head -20

# 2. Downgrade
docker compose run --rm backend alembic downgrade <target-revision>
# nebo: alembic downgrade -1  (jeden krok zpět)

# 3. Spusť starou verzi kódu
docker compose up -d backend worker
```

---

## Migrace — co si dát pozor

### Bezpečnostní pravidla

1. **Záloha VŽDY před migrací** — i jedna migrace může smazat sloupec
2. **Migrace testovat ve staging** před produkčním deployem
3. **DB a backend nesynchronizovat živě** — backend stop → migrace → backend start
4. **Downgrade migrací je destruktivní** — migrate_check + backup, nikdy impulzivně

### Aktuální stav migrací (v0.5.0)
```
HEAD: 20260326_0018_add_role_permissions
      20260326_0017_add_password_reset_tokens
      20260326_0016_add_status_check_constraints
      20260326_0015_financial_float_to_numeric   ← změní typy sloupců
      20260326_0014_add_performance_indexes
      20260326_0013_add_user_tokens_valid_after
      ...
      20260318_0001_initial_schema
```

Migrace `0015` (float→numeric) je **destruktivní při downgradu** — ztratíš přesnost dat. Nikdy nechoď pod `20260321_0010`.

### Postup při chybě migrace v půlce

```bash
# 1. Zkontroluj, kde se migrace zastavila
docker compose run --rm backend alembic current

# 2. Zkontroluj DB, jestli jsou v konzistentním stavu
docker compose exec db psql -U novu novu_builder \
  -c "\d+ <tabulka-ze-selhávající-migrace>"

# 3a. Pokud DB je čistá (DDL nebyl aplikován):
docker compose run --rm backend alembic stamp <předchozí-revize>
# oprav příčinu, pak upgrade znovu

# 3b. Pokud DDL byl částečně aplikován:
# → Restore z zálohy (viz BACKUP_RESTORE.md)
```

---

## Worker — speciální situace při deployi

Worker konzumuje Redis queue. Při restartu workeru:
- Rozpracované joby se **neztratí** — Redis queue je perzistentní
- Joby ve stavu `running` zůstanou `running` v DB, ale reálně se nedokončí
- Po restartu worker zpracuje `queued` joby, ale `running` joby neretryuje automaticky

**Po upgradu workeru:**

```bash
# Zkontroluj zaseknuté "running" joby
docker compose exec db psql -U novu novu_builder \
  -c "SELECT id, status, created_at FROM analysis_jobs WHERE status='running' ORDER BY created_at;"

# Pokud jsou starší než 10 minut a worker byl restartován, jsou zaseknuté
# Manuálně je přehodit na queued (přes admin API nebo přímo v DB) pro retry
```

---

## Prometheus scrape config (po deployi)

Po každém deployi ověř, že Prometheus stále sbírá metriky:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: novu-backend
    static_configs:
      - targets: ["<backend-host>:80"]
    metrics_path: /api/v1/metrics
    scheme: https
    tls_config:
      insecure_skip_verify: true   # jen pokud self-signed cert
    authorization:
      credentials: "<METRICS_AUTH_TOKEN>"
```

**Poznámka:** Prometheus musí být ve stejné sítí jako backend (docker internal nebo VPN), protože nginx blokuje `/api/v1/metrics` z veřejného internetu.

---

*Poslední revize: 2026-03-28 | Platí pro v0.5.x*
