# Novu Builder — Operations Guide

Minimal single-host operations reference.
Not a replacement for a full runbook — expands as the system grows.

---

## Prerequisites

- Docker + Docker Compose v2
- A `.env` file in the project root with at minimum:

```
POSTGRES_PASSWORD=<strong-random>
JWT_SECRET=<strong-random-32-chars-min>
AI_ANALYSIS_PROVIDER=mock          # or anthropic / openai
ANTHROPIC_API_KEY=                 # required when provider=anthropic
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

| Endpoint      | Auth     | Purpose                                     |
|---------------|----------|---------------------------------------------|
| `GET /alive`  | none     | Liveness probe — process is up              |
| `GET /health` | none     | Readiness + DB connectivity + job counts    |
| `GET /metrics`| **none** | Prometheus scrape — **restrict at proxy** |

`/metrics` is intentionally unauthenticated for Prometheus scraping.
In production, restrict it at the nginx layer:

```nginx
location /metrics {
    allow 10.0.0.0/8;   # internal Prometheus scraper
    deny all;
}
```

### Key metrics exposed

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Requests by method / path template / status |
| `http_request_duration_seconds` | Histogram | Latency by method / path template / status |
| `http_requests_in_progress` | Gauge | Concurrency by method |

Prometheus scrape config example:

```yaml
scrape_configs:
  - job_name: novu-backend
    static_configs:
      - targets: ["localhost:8000"]
    metrics_path: /metrics
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
| File storage (photos, exports) | `storage_data` Docker volume | `tar` via alpine container |

### Running a backup

```bash
# One-shot backup to ./backups/
BACKUP_DIR=/backups ./scripts/backup.sh

# Or with custom retention
RETAIN_DAYS=14 BACKUP_DIR=/backups ./scripts/backup.sh
```

### Automated daily backup (cron)

```cron
0 2 * * * cd /opt/novu-builder && BACKUP_DIR=/backups ./scripts/backup.sh >> /var/log/novu-backup.log 2>&1
```

### Restore procedure

#### 1. Database restore

```bash
# Stop the backend (not DB) to avoid writes during restore
docker compose stop backend

# Drop and recreate the database
docker compose exec db psql -U novu -c "DROP DATABASE novu_builder;"
docker compose exec db psql -U novu -c "CREATE DATABASE novu_builder;"

# Restore from dump
gunzip -c /backups/db_YYYYMMDD_HHMMSS.sql.gz \
  | docker compose exec -T db psql -U novu novu_builder

# Run any pending migrations, then restart
docker compose run --rm backend alembic upgrade head
docker compose start backend
```

#### 2. Storage restore

```bash
# Stop backend first
docker compose stop backend

# Clear and restore the volume
docker run --rm \
  -v novu_builder_storage_data:/data \
  -v /backups:/backup \
  alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/storage_YYYYMMDD_HHMMSS.tar.gz -C /"

docker compose start backend
```

### What is NOT automated

- Off-site / remote copy of backup files (use `rsync`, `rclone`, S3, etc.)
- Backup verification (restore drill)
- Point-in-time recovery (needs WAL archiving or Barman — out of scope for single-host)

---

## Worker process (R-19)

The analysis job worker runs as a separate process consuming the Redis queue.
Add it to docker-compose as a second backend service when needed:

```yaml
worker:
  build:
    context: ./python-backend
  restart: unless-stopped
  depends_on:
    db:
      condition: service_healthy
    redis:
      condition: service_healthy
  environment:
    <<: *backend-env    # share env with backend
  command: ["python", "-m", "app.worker.runner"]
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Backend exits on startup | `docker compose logs backend` — usually schema mismatch; run `alembic upgrade head` |
| 502 from nginx | Backend healthcheck failing — `docker compose ps` + `docker compose logs backend` |
| Analysis jobs stuck in `queued` | Worker not running — start `app.worker.runner` |
| Cache stale after pricebook change | TTL expires in ≤5 min; or `redis-cli DEL cache:pricebooks:list:{org_id}` |
| Redis unavailable | App and worker fail open — all features degrade gracefully, no crash |
