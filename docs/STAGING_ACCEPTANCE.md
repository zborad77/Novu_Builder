# NOVU Builder — Staging Acceptance

Use this document for the final acceptance of a release candidate on a
production-like, disposable staging host.

The staging result is evidence for release; it is not replaced by local tests or
by GitHub CI.

## Acceptance identity

Record before starting:

| Field | Value |
|---|---|
| Release candidate | |
| Commit SHA | |
| Date/time | |
| Host | |
| Operator | |
| Storage image/provider | |

The checked-out commit must be exact and the working tree clean.

---

## Phase A — Environment and infrastructure

1. Render `.env.production` with `scripts/Build-ComposeEnv.ps1 -Write`.
2. Confirm no placeholders remain.
3. Confirm MinIO server/client image references are pinned and not `:latest`.
4. Verify the exact image references pull successfully.
5. Build `backend` and `worker`.
6. Start only `db redis minio minio-setup`.
7. Require PostgreSQL, Redis and MinIO healthy; `minio-setup` must exit 0.

Result:

| Check | PASS/FAIL | Evidence |
|---|---|---|
| Compose config | | |
| Image pulls | | |
| PostgreSQL | | |
| Redis | | |
| S3/MinIO | | |
| Bucket bootstrap | | |

---

## Phase B — Database migration

Apply migrations explicitly:

```bash
docker compose --env-file .env.production run --rm --no-deps --entrypoint alembic backend upgrade head
docker compose --env-file .env.production run --rm --no-deps --entrypoint alembic backend current
docker compose --env-file .env.production run --rm --no-deps --entrypoint alembic backend heads
```

For v0.8.6, expected revision:

```text
20261003_0056
```

Verify directly:

```sql
SELECT version_num FROM alembic_version;
SELECT to_regclass('public.revoked_tokens');
```

Also verify `users.is_superadmin` is `BOOLEAN NOT NULL`.

Re-run `alembic upgrade head`; it must complete as a no-op.

Result:

| Check | PASS/FAIL | Evidence |
|---|---|---|
| Fresh/upgrade migration | | |
| Single Alembic head | | |
| Current revision 0056 | | |
| revoked_tokens | | |
| users.is_superadmin | | |
| Repeat upgrade no-op | | |

---

## Phase C — Runtime

On a fresh database, create the acceptance admin using
`scripts/create_pilot_admin.py`.

Start:

```bash
docker compose --env-file .env.production up -d backend worker nginx
docker compose --env-file .env.production ps
```

Run:

```bash
python scripts/verify_deploy.py --base-url https://<host> \
  --auth-email <email> --auth-password "<password>" --require-auth
```

Require strict processing readiness with a real worker.

Result:

| Check | PASS/FAIL | Evidence |
|---|---|---|
| Backend healthy | | |
| Worker healthy | | |
| /alive | | |
| /health | | |
| /ready | | |
| strict processing readiness | | |
| Authenticated API smoke | | |

---

## Phase D — Business flow

Run the repository business-flow smoke with the acceptance credentials.

It must cover:

1. login,
2. create case,
3. fetch case,
4. trigger analysis job,
5. worker processing,
6. terminal successful job state,
7. latest analysis available,
8. cleanup/archive.

The script does not certify SSE.

Result:

| Check | PASS/FAIL | Evidence |
|---|---|---|
| Business flow | | |
| Cleanup | | |

---

## Phase E — SSE/event delivery

Verify the current event/SSE client path separately while a test case produces
events. Record the endpoint/client used, at least one expected event, and proof
that the client receives it without polling-only fallback.

Result:

| Check | PASS/FAIL | Evidence |
|---|---|---|
| SSE connection | | |
| Expected event delivered | | |
| Tenant/auth boundary respected | | |

---

## Phase F — Backup and restore

Follow `BACKUP_RESTORE.md`.

1. Create backup.
2. Verify backup integrity.
3. Restore into a separate disposable target.
4. Verify restored Alembic revision.
5. Start the restored application.
6. Re-run `verify_deploy.py`.

Never perform the drill against the only copy of staging data.

Result:

| Check | PASS/FAIL | Evidence |
|---|---|---|
| Backup | | |
| Integrity verification | | |
| Restore | | |
| Restored revision | | |
| Post-restore deploy verification | | |

---

## Final decision

Release acceptance is **PASS** only if every phase above passes and no open
release blocker remains.

| Final | Value |
|---|---|
| Acceptance | PASS / FAIL |
| Blocking findings | |
| Follow-up PRs | |
| Approved release commit | |

After PASS, merge any release-closeout documentation, require final push CI on
`master`, then tag that exact commit. Never move an existing release tag.
