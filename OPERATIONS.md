# Novu Builder — Operations Guide

Minimal single-host operations reference.
Pro detailní runbook, deployment postup a backup/restore viz:
- [RUNBOOK.md](RUNBOOK.md) — incident response
- [DEPLOY.md](DEPLOY.md) — deployment a rollback
- [BACKUP_RESTORE.md](BACKUP_RESTORE.md) — zálohy a obnova
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) — pre-deploy checklist
- [PRODUCTION_VERDICT.md](PRODUCTION_VERDICT.md) — readiness verdict

---

## Prerequisites

- Docker + Docker Compose v2
- A `.env.production` file in the project root — copy from `.env.production.example`:

```
POSTGRES_PASSWORD=<openssl rand -hex 32>
REDIS_PASSWORD=<openssl rand -hex 32>
JWT_SECRET=<openssl rand -hex 32>
METRICS_AUTH_TOKEN=<openssl rand -hex 32>
METRICS_AUTH_ENABLED=true
AI_ANALYSIS_PROVIDER=mock          # or claude / openai
ANTHROPIC_API_KEY=                 # required when provider=claude
APP_BASE_URL=https://app.example.com
CORS_ALLOWED_ORIGINS=https://app.example.com
STORAGE_BACKEND=s3
S3_BUCKET=novu-prod-bucket
S3_REGION=us-east-1
```

Spouštěj jako:
```bash
docker compose --env-file .env.production up -d
```

---

## Starting / stopping

```bash
# First start — runs DB migrations, then web server
docker compose up -d

# Check status
docker compose ps

# Tail logs
docker compose logs -f backend
docker compose logs -f redis

# Stop without removing volumes
docker compose stop

# Full teardown (preserves named volumes / data)
docker compose down
```

---

## Schema migrations

Migrations are **not** run automatically on app startup (R-17).
Run them explicitly before (re)starting the backend:

```bash
docker compose run --rm backend alembic upgrade head
```

To generate a new migration after model changes:

```bash
docker compose run --rm backend alembic revision --autogenerate -m "describe change"
```

---

## Health & metrics

| Endpoint                     | Auth                         | Purpose                                      |
|------------------------------|------------------------------|----------------------------------------------|
| `GET /api/v1/alive`          | none                         | Liveness probe — process is up               |
| `GET /api/v1/health`         | none                         | Public liveness probe â€” minimal, no internals |
| `GET /api/v1/ready`          | none                         | Public readiness probe â€” startup + DB ready  |
| `GET /api/v1/health/internal`| superadmin token + interní IP| Detailní stav: worker, joby, startup checks   |
| `GET /api/v1/metrics`        | Bearer `METRICS_AUTH_TOKEN`  | Prometheus scrape — IP whitelist v nginx      |

`/api/v1/metrics` vyžaduje Bearer token (`METRICS_AUTH_ENABLED=true`, výchozí).
nginx navíc povoluje přístup pouze z interní sítě (10.x, 172.x, 192.168.x, localhost).

`/api/v1/health` je zÃ¡mÄ›rnÄ› dependency-free a vracÃ­ jen minimÃ¡lnÃ­ payload.
`/api/v1/ready` vracÃ­ `200 {"status":"ready",...}` pouze kdyÅ¾ startup checks dobÄ›hly
a databÃ¡ze odpovÃ­dÃ¡; jinak vracÃ­ `503 {"status":"not_ready",...}`.
`/api/v1/health/internal` je diagnostickÃ½ endpoint pro operÃ¡tory a pÅ™i degradaci vracÃ­ HTTP 503.

### Key metrics exposed

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Requests by method / path template / status |
| `http_request_duration_seconds` | Histogram | Latency by method / path template / status |
| `http_requests_in_progress` | Gauge | Concurrency by method |
| `novu_db_alive` | Gauge | 1.0 = DB dostupná, 0.0 = výpadek |
| `novu_worker_alive` | Gauge | 1.0 = worker aktivní (heartbeat < 90 s) |
| `novu_jobs_queued` | Gauge | Počet jobů čekajících na zpracování |
| `novu_jobs_running` | Gauge | Počet právě běžících jobů |

| `novu_auth_failures_total` | Counter | Auth selhani podle endpointu a coarse-grained reason |
| `novu_upload_rejections_total` | Counter | Odmitnute uploady podle coarse-grained reason a HTTP status |

Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: novu-backend
    static_configs:
      - targets: ["<host>:443"]
    metrics_path: /api/v1/metrics
    scheme: https
    authorization:
      credentials: "<METRICS_AUTH_TOKEN>"
```

---

## Redis caching (R-32)

Pricebooks and suppliers lists are cached in Redis to reduce DB load:

| Scope | TTL | Cache key pattern | Invalidated on |
|-------|-----|-------------------|----------------|
| Pricebook list (per org) | 300 s | `cache:pricebooks:list:{org_id}` | `POST /pricebooks` |
| Supplier list (per org, active/all) | 60 s | `cache:suppliers:list:{org_id}:{flag}` | `PATCH /suppliers/{id}` |

All cache reads fail open — a Redis outage causes a cache miss, not an error.
Superadmin (cross-tenant) views bypass the cache entirely.

---

## Backup & restore (R-40)

### What is backed up

| Data | Location | Method |
|------|----------|--------|
| PostgreSQL | `postgres_data` Docker volume | `pg_dump` |
| File storage (photos, exports) | S3 bucket from `S3_BUCKET` | provider-native backup / versioning |

When `STORAGE_BACKEND=s3` (required in production), the compatibility
`storage_data` Docker volume is not the source of uploaded media.

### Running a backup

```bash
# One-shot backup to ./backups/  (produces db_TIMESTAMP.pgdump + storage_TIMESTAMP.tar.gz)
BACKUP_DIR=/backups ./scripts/backup.sh

# Or with custom retention
RETAIN_DAYS=14 BACKUP_DIR=/backups ./scripts/backup.sh
```

### Automated daily backup (cron)

```cron
0 2 * * * cd /opt/novu-builder && BACKUP_DIR=/backups ./scripts/backup.sh >> /var/log/novu-backup.log 2>&1
```

### Verify before restore (recommended, non-destructive)

```bash
# Restore to TEMP DB, validate, clean up — does not touch production
# Requires: psql, pg_restore on host + DATABASE_URL in python-backend/.env
python-backend/scripts/verify_restore.sh /backups/db_YYYYMMDD_HHMMSS.pgdump
```

### Restore procedure

#### 1. Database restore

```bash
# One-command restore (stops services, restores .pgdump, runs migrations, restarts)
./ops/restore.sh /backups/db_YYYYMMDD_HHMMSS.pgdump

# Unattended (CI / automation)
./ops/restore.sh /backups/db_YYYYMMDD_HHMMSS.pgdump --yes
```

ops/restore.sh performs post-restore integrity checks (specific critical tables +
alembic_version populated) before restarting services.

#### 2. Storage restore

```bash
# Stop backend and worker (both access storage)
docker compose stop backend worker

# Clear and restore the volume
docker run --rm \
  -v novu_builder_storage_data:/data \
  -v /backups:/backup \
  alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/storage_YYYYMMDD_HHMMSS.tar.gz -C /"

docker compose start backend worker
```

### What is NOT automated

- Off-site / remote copy of backup files (use `rsync`, `rclone`, S3, etc.)
- Backup verify to temp DB is automated via `python-backend/scripts/verify_restore.sh`
- Full restore drill on clean environment (separate host) remains manual
- Point-in-time recovery (needs WAL archiving or Barman — out of scope for single-host)

---

## Worker process (R-19)

Worker je součástí `docker-compose.yml` jako samostatná služba `worker`.
Spouští se automaticky s `docker compose up -d` a restartuje se při pádu (`restart: unless-stopped`).

```bash
# Stav workeru
docker compose ps worker
docker compose logs -f worker

# Worker heartbeat (obnovuje se každých 30 s, TTL = 120 s)
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" GET worker:heartbeat
```

Pokud jsou joby zaseknuté ve stavu `queued`, worker nejspíš neběží — viz RUNBOOK.md INCIDENT-01.

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Backend exits on startup | `docker compose logs backend` — usually schema mismatch; run `alembic upgrade head` |
| 502 from nginx | Backend healthcheck failing — `docker compose ps` + `docker compose logs backend` |
| Analysis jobs stuck in `queued` | Worker not running — start `app.worker.runner` |
| Cache stale after pricebook change | TTL expires in ≤5 min; or `redis-cli DEL cache:pricebooks:list:{org_id}` |
| Redis unavailable | App and worker fail open — all features degrade gracefully, no crash |
