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

### SLO / error budget

Production SLO definitions, Prometheus recording rules a reporting workflow jsou v:

- [docs/production-slo-system.md](docs/production-slo-system.md)
- `ops/alerting/slo-rules.yml`
- `scripts/report_slo.py`

Typický weekly report:

```bash
python scripts/report_slo.py \
  --prometheus-url http://127.0.0.1:9090 \
  --window 30d \
  --job novu-backend \
  --json-out artifacts/slo-report.json \
  --markdown-out artifacts/slo-report.md
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
| PostgreSQL | `postgres_data` Docker volume | `scripts/backup.sh` -> `.pgdump` + `.sha256` + manifest |
| File storage (photos, exports) in production | S3 bucket from `S3_BUCKET` | external bucket controls outside repo scripts |

When `STORAGE_BACKEND=s3` (required in production), the compatibility
`storage_data` Docker volume is not the source of uploaded media.
In that mode, repo backup/restore is DB-only and does not provide full production DR.

### Running a backup

```bash
# One-shot backup to ./backups/
BACKUP_DIR=/backups ./scripts/backup.sh

# Or with custom retention
RETAIN_DAYS=14 BACKUP_DIR=/backups ./scripts/backup.sh
```

Current semantics:

- local/dev may also produce `storage_TIMESTAMP.tar.gz`
- `production+s3` produces DB artifact set only
- manifest may record Variant A foundation metadata:
  - `dr_contract`
  - `dr_recovery_point_model`
  - `s3_bucket`
  - `s3_region`
  - `s3_recovery_point`
  - `storage_snapshot_consistent`
- `production+s3` manifest explicitly marks `production_dr_eligible=false`
- even with foundation metadata present, repo scripts still do not claim full
  DB + S3 disaster recovery

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
# One-command DB restore (stops services, restores .pgdump, runs migrations, restarts)
./ops/restore.sh /backups/db_YYYYMMDD_HHMMSS.pgdump

# Unattended (CI / automation)
./ops/restore.sh /backups/db_YYYYMMDD_HHMMSS.pgdump --yes
```

`ops/restore.sh` validates:

- manifest contract
- checksum
- production+s3 S3 protection prerequisites
- production+s3 S3 pre-restore validation
- DB restore
- schema/head alignment
- backend liveness

`ops/restore.sh` does not validate:

- S3/object storage recovery
- full production disaster recovery
- full application readiness beyond dependency-free liveness

Variant A foundation boundary:

- restore reads the new S3 recovery-point metadata only as contract metadata
- contradictory S3 DR metadata fails closed
- full production DR is still not implemented or claimed

#### 2. Production + S3 boundary

For `APP_ENV=production` with `STORAGE_BACKEND=s3`:

- repo scripts do not restore production object storage
- S3 recovery must be performed outside repo scripts
- do not treat DB restore success as full-state production restore
- follow [BACKUP_RESTORE.md](BACKUP_RESTORE.md) for the authoritative production boundary

#### 3. Local/dev compatibility only

`storage_YYYYMMDD_HHMMSS.tar.gz` is a local/dev compatibility artifact.
It is not an authoritative production recovery mechanism for `STORAGE_BACKEND=s3`.

### What is NOT automated

- Production S3 backup/recovery automation
- Full production DR drill
- Full-state production restore validation
- Off-site / remote copy of backup files for S3 media
- Backup verify to temp DB is automated via `python-backend/scripts/verify_restore.sh`
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
