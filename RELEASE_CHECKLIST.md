# NOVU Builder — Release Readiness Checklist

**Applies to:** v0.8.6 release candidate  
**Alembic HEAD:** `20261003_0056`

Use this checklist for the final staging acceptance before tagging a release.

---

## 0. Source and CI

| # | Check | Required |
|---|---|---|
| 0.1 | Exact release commit identified | MUST |
| 0.2 | Working tree clean | MUST |
| 0.3 | PR CI green | MUST |
| 0.4 | Repo Guard green | MUST |
| 0.5 | Final push CI on `master` green | MUST |
| 0.6 | `postgresql-migrations` job green | MUST |
| 0.7 | `deployment-config` job green | MUST |

---

## 1. Environment and images

| # | Check | Required |
|---|---|---|
| 1.1 | Root `.env.production` rendered from local sources | MUST |
| 1.2 | No `CHANGE_ME`, `REPLACE_WITH` or empty required secrets | MUST |
| 1.3 | `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET`, `METRICS_AUTH_TOKEN` are unique strong values | MUST |
| 1.4 | `AI_ANALYSIS_PROVIDER` explicitly selected | MUST |
| 1.5 | `MINIO_SERVER_IMAGE` is an approved pinned tag/digest, not `:latest` | MUST |
| 1.6 | `MINIO_MC_IMAGE` is an approved pinned tag/digest, not `:latest` | MUST |
| 1.7 | Exact image references successfully pull in staging | MUST |
| 1.8 | TLS certificate exists and is valid for the staging host | MUST |

---

## 2. Database and migrations

| # | Check | Required |
|---|---|---|
| 2.1 | PostgreSQL 16 is healthy before migration | MUST |
| 2.2 | Backup exists before upgrading a non-empty environment | MUST |
| 2.3 | Backend and worker are stopped before upgrade migration | MUST |
| 2.4 | Migration is run explicitly with `--entrypoint alembic` | MUST |
| 2.5 | `alembic current` = `20261003_0056` | MUST |
| 2.6 | `alembic heads` = one head, `20261003_0056` | MUST |
| 2.7 | `revoked_tokens` exists | MUST |
| 2.8 | `users.is_superadmin` is `BOOLEAN NOT NULL` | MUST |
| 2.9 | Re-running `alembic upgrade head` is a no-op | MUST |

The backend container must **not** apply migrations automatically on startup.

---

## 3. Infrastructure services

| # | Check | Required |
|---|---|---|
| 3.1 | Redis healthy and authentication enforced | MUST |
| 3.2 | S3-compatible storage healthy | MUST |
| 3.3 | `minio-setup`/bucket bootstrap exits successfully when local MinIO is used | MUST |
| 3.4 | Required bucket exists | MUST |
| 3.5 | Backend can read/write the configured storage backend | MUST |

---

## 4. Backend and worker

| # | Check | Required |
|---|---|---|
| 4.1 | Backend starts without ERROR/CRITICAL | MUST |
| 4.2 | Worker starts and remains healthy | MUST |
| 4.3 | `GET /api/v1/alive` returns HTTP 200 with `{"status":"alive"}` | MUST |
| 4.4 | `/api/v1/health` passes semantic operational validation | MUST |
| 4.5 | `/api/v1/ready` reports service ready | MUST |
| 4.6 | `/api/v1/ready/processing?strict=1` passes with real worker | MUST |

Use `scripts/verify_deploy.py` as the authoritative probe bundle rather than
checking obsolete exact health payload examples.

---

## 5. Authentication and business flow

| # | Check | Required |
|---|---|---|
| 5.1 | Login with staging acceptance account succeeds | MUST |
| 5.2 | Authenticated core API smoke passes | MUST |
| 5.3 | Create case succeeds | MUST |
| 5.4 | Trigger analysis job succeeds | MUST |
| 5.5 | Worker reaches terminal successful job state | MUST |
| 5.6 | Latest analysis is available on the case | MUST |
| 5.7 | Test case cleanup/archive succeeds | MUST |
| 5.8 | SSE/event delivery verified separately | MUST |

Run:

```bash
python scripts/verify_deploy.py --base-url https://<host> \
  --auth-email <email> --auth-password "<password>" --require-auth

python scripts/test-business-flow.py --url https://<host>
```

The business-flow script does not certify SSE.

---

## 6. Security boundary

| # | Check | Required |
|---|---|---|
| 6.1 | Backend port 8000 is not publicly exposed | MUST |
| 6.2 | HTTP redirects to HTTPS | MUST |
| 6.3 | Metrics endpoint is not publicly accessible without intended protection | MUST |
| 6.4 | Internal health endpoint is restricted by nginx/network policy | MUST |
| 6.5 | CORS has no wildcard in strict deployment | MUST |
| 6.6 | No real production secrets appear in logs or CI output | MUST |

---

## 7. Backup and restore

| # | Check | Required |
|---|---|---|
| 7.1 | Database backup completes successfully | MUST |
| 7.2 | Backup integrity verification passes | MUST |
| 7.3 | Restore drill performed into a disposable environment | MUST |
| 7.4 | Restored DB reaches expected Alembic revision | MUST |
| 7.5 | Post-deploy verifier passes after restore | MUST |

See `BACKUP_RESTORE.md`.

---

## 8. Rollback readiness

| # | Check | Required |
|---|---|---|
| 8.1 | Previous application commit/image is available | MUST |
| 8.2 | Pre-upgrade backup is accessible | MUST |
| 8.3 | Operator understands that downgrade `0056 -> 0055` drops `users.is_superadmin` values | MUST |
| 8.4 | Code-only rollback path has been reviewed | MUST |

Prefer code rollback over schema downgrade when compatible.

---

## Go / No-Go

**GO** only when every MUST item is complete and no unresolved blocker remains.

For v0.8.6 specifically, do not tag or publish the release until:

- final `master` CI is green,
- fresh PostgreSQL migration coverage is green,
- deployment-config coverage is green,
- full staging acceptance passes,
- backup/restore drill passes.

If any one of those is missing, the release remains **NO-GO**.
