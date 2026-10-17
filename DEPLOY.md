# NOVU Builder — Deployment & Rollback

**Applies to:** v0.8.6 release candidate and later unless superseded.

**Runtime stack:** Docker Compose with PostgreSQL 16, Redis 7, S3-compatible storage, backend, worker and nginx.

## Deployment invariant: migrations are explicit

Database schema changes are a deployment step. The backend container **must not**
run Alembic automatically on startup.

The application performs a schema-version guard and fails fast if the database is
not at the expected Alembic head. For v0.8.6 the expected head is:

```text
20261003_0056
```

Use the explicit Compose entrypoint override shown below. Do not rely on the
backend image entrypoint to migrate the database.

---

## 1. Checkout and verify the release commit

For a release deployment, deploy an exact tag or commit rather than a moving branch.

```bash
git fetch --tags
git checkout <release-tag-or-commit>
git status --short
git rev-parse HEAD
```

The working tree must be clean.

---

## 2. Prepare deployment environment

The backend template is:

```text
python-backend/.env.production.example
```

Create the two local source files used by the Compose env builder:

- `python-backend/.env.production` — application secrets and strict-runtime overrides
- root `.env` — infrastructure values such as `POSTGRES_PASSWORD` and `REDIS_PASSWORD`

Then render root `.env.production`:

```powershell
.\scripts\Build-ComposeEnv.ps1
.\scripts\Build-ComposeEnv.ps1 -Write
```

Before deployment, the dry-run must report no missing or `CHANGE_ME` /
`REPLACE_WITH` values.

### Required MinIO image policy

`docker-compose.yml` intentionally has no mutable MinIO defaults. Set:

```text
MINIO_SERVER_IMAGE=<approved pinned tag or digest>
MINIO_MC_IMAGE=<approved pinned tag or digest>
```

Do **not** use `:latest`.

The historical MinIO Community Docker Hub repositories are archived. Treat image
selection as an operator decision: use a vetted immutable image or an approved
external S3-compatible service. Validate the exact image in staging before release.

For a disposable internal rehearsal, archived community images may be used only
after explicit risk acceptance; do not silently promote them to production.

---

## 3. TLS certificates

The nginx service requires:

```text
nginx/certs/cert.pem
nginx/certs/key.pem
```

For an internal staging host, use the repository helper:

```powershell
.\scripts\Generate-PilotCert.ps1
```

or the shell equivalent:

```bash
./scripts/generate-pilot-cert.sh
```

Use a CA-issued certificate for an internet-facing production deployment.

---

## 4. Build application images

```bash
docker compose --env-file .env.production build backend worker
```

A build failure is a deployment blocker.

---

## 5. Start infrastructure only

```bash
docker compose --env-file .env.production up -d db redis minio minio-setup
docker compose --env-file .env.production ps -a
```

Required state before migration:

- PostgreSQL: healthy
- Redis: healthy
- MinIO: healthy
- `minio-setup`: exited successfully

Do not start backend, worker or nginx yet.

---

## 6. Apply Alembic migrations explicitly

```bash
docker compose --env-file .env.production run --rm --no-deps --entrypoint alembic backend upgrade head
docker compose --env-file .env.production run --rm --no-deps --entrypoint alembic backend current
docker compose --env-file .env.production run --rm --no-deps --entrypoint alembic backend heads
```

For v0.8.6, both `current` and `heads` must report:

```text
20261003_0056
```

Verify the database directly:

```bash
docker compose --env-file .env.production exec db \
  psql -U novu -d novu_builder -c "SELECT version_num FROM alembic_version;"

docker compose --env-file .env.production exec db \
  psql -U novu -d novu_builder -c "SELECT to_regclass('public.revoked_tokens');"

docker compose --env-file .env.production exec db \
  psql -U novu -d novu_builder -c "\d+ users"
```

Expected:

- `alembic_version.version_num = 20261003_0056`
- `revoked_tokens` exists
- `users.is_superadmin` exists and is `BOOLEAN NOT NULL`

Never use `alembic stamp` to bypass a failed migration during a normal deploy.

---

## 7. Create the first staging/pilot admin on a fresh database

Only for a genuinely new environment:

```bash
docker compose --env-file .env.production run --rm --no-deps --entrypoint python backend \
  -m scripts.create_pilot_admin \
  --email <admin-email> \
  --full-name "Staging Admin" \
  --password "<strong-disposable-or-production-password>"
```

Do not recreate the first admin on an existing environment.

---

## 8. Start application services

```bash
docker compose --env-file .env.production up -d backend worker nginx
docker compose --env-file .env.production ps
```

The backend startup guard must fail if the schema is not at Alembic head.
A healthy backend therefore proves that the explicit migration step completed.

---

## 9. Post-deploy verification

Run the authoritative deployment verifier:

```bash
python scripts/verify_deploy.py \
  --base-url https://<host> \
  --auth-email <email> \
  --auth-password "<password>" \
  --require-auth
```

This verifies:

- `/api/v1/alive`
- operational `/api/v1/health`
- `/api/v1/ready`
- strict processing readiness through a real worker
- authenticated API smoke when credentials are supplied

Then run the end-to-end business flow:

```bash
python scripts/test-business-flow.py --url https://<host>
```

Supply `NOVU_TEST_EMAIL` and `NOVU_TEST_PASSWORD` in the environment.

The business-flow script does **not** certify SSE delivery. SSE/event delivery must
be verified separately during staging acceptance.

---

## 10. Backup and restore acceptance

Before any upgrade of an environment containing real data, create a backup using
the repository backup procedure in `BACKUP_RESTORE.md`.

A release candidate is not considered staging-accepted until a restore drill has
been completed in a disposable environment and the restored application passes
the post-deploy verifier.

Restore operations are destructive. Never run them against the only copy of
staging or production data.

---

# Upgrade procedure

1. Create a fresh backup.
2. Fetch and checkout the exact target tag/commit.
3. Build `backend` and `worker`.
4. Stop application writers:
   ```bash
   docker compose --env-file .env.production stop backend worker
   ```
5. Apply the explicit Alembic migration command from section 6.
6. Start backend and worker:
   ```bash
   docker compose --env-file .env.production up -d backend worker
   ```
7. Run `verify_deploy.py` with authentication.
8. Run the business-flow smoke.
9. Review backend and worker logs for `ERROR` / `CRITICAL`.

Do not downgrade the database as the first rollback action.

---

# Rollback

## Preferred rollback: application code only

If the new schema is backward-compatible with the previous application version:

1. stop backend and worker,
2. deploy the previous application image/commit,
3. start backend and worker,
4. run post-deploy verification.

## Schema downgrade

Schema downgrade is a last resort and requires a verified backup.

Revision `20261003_0056` drops `users.is_superadmin` on downgrade. Existing
superadmin assignments are therefore lost by that downgrade and cannot be
reconstructed automatically on a later upgrade.

Never downgrade this revision casually.

---

# Release acceptance rule

Do not tag a release until all of the following are true:

1. PR CI and Repo Guard are green.
2. Push CI on the final `master` commit is green.
3. `postgresql-migrations` passes from an empty PostgreSQL 16 database.
4. `deployment-config` passes.
5. Staging uses the exact release commit.
6. Explicit Alembic migration reaches the expected head.
7. Backend + worker readiness passes.
8. Authenticated deploy verification passes.
9. Business flow passes.
10. SSE/event delivery is checked separately.
11. Backup/restore drill passes.

Only then create the version tag and GitHub release.
