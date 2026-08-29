# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product

NOVU Builder (formerly FotoNabidka) is a SaaS product for rapidly building construction price quotes from field photos. The workflow: capture photos in the field → AI vision analysis + measurement → calculation → review/edit/send the quote from an office client.

Most code comments, docs, and commit messages are in **Czech**. Match that when editing existing files.

## Repository Layout

- `python-backend/` — **the backend** (FastAPI + SQLAlchemy 2.x async + Alembic + Pydantic v2). PostgreSQL/Redis/S3 in prod, SQLite/local-storage in dev. This is where almost all work happens.
- `desktop-qt/` — **primary client**: C++/Qt6 Widgets office desktop app. Talks to the backend over HTTP at `http://127.0.0.1:8000/api/v1`.
- `web/` — React/Vite/TS. Admin portal only (browser); **not** the main client.
- `novu-mobile/` — **FROZEN** (to be replaced by Qt for Mobile). Don't invest here.
- `scripts/` — repo-root PowerShell/Python dev, bootstrap, smoke, and verification scripts.
- `docs/` — architecture, blueprints, subsystem specs, audits, runbooks.
- `storage/` — local DEV-ONLY storage for images/exports.

Per `ARCHITECTURE.md`: **local storage is DEV ONLY**. In production, file reads/writes go through the active S3 backend; DB rows store storage *keys*, never public URLs; the API returns only time-limited signed URLs.

## Commands

### Backend (run from `python-backend/`)

```powershell
# Dev server (also available from repo root as: npm run api:dev)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Migrations
alembic upgrade head
alembic revision --autogenerate -m "popis_zmeny"

# Tests (defaults to a throwaway SQLite DB; conftest sets all required env)
python -m pytest tests/ -v
python -m pytest tests/test_d1_e2e_analysis_flow.py -v          # single file
python -m pytest tests/test_d1_e2e_analysis_flow.py::test_name  # single test
# Run tests against Postgres: set TEST_DATABASE_URL before invoking pytest

# Lint / type / SAST (tools in requirements-dev.txt) — must pass in CI
ruff check app/
mypy app/
bandit -r app/ -ll -ii
pip-audit -r requirements.txt --progress-spinner=off
```

mypy must stay at **0 errors over all of `app/`** (per-module suppressions live in `pyproject.toml`; don't broaden them casually). Coverage gate in CI is `--cov-fail-under=40`.

### Desktop (run from `desktop-qt/`, Windows + MSVC + Qt 6.x)

Build first in Qt Creator (creates the `build/Desktop_Qt_6_10_2_MSVC2022_64bit-Debug` kit dir), then:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-debug.ps1       # build, logs status JSON
powershell -ExecutionPolicy Bypass -File scripts\smoke-check.ps1        # backend health + exe + last build
powershell -ExecutionPolicy Bypass -File scripts\smoke-workflow.ps1     # reference case → duplicate → cleanup
powershell -ExecutionPolicy Bypass -File scripts\smoke-final-proposal.ps1
powershell -ExecutionPolicy Bypass -File scripts\smoke-draft-send-guard.ps1
```

The Qt target/exe is `NovuBuilder` (CMake `project(NovuBuilder)`). Some docs/scripts still reference the old `FotoNabidkaDesktop` name.

### Repo-root onboarding / ops (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap-dev.ps1          # venv, deps, .env, migrate
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1              # start backend (-DryRun to verify)
powershell -ExecutionPolicy Bypass -File scripts\switch-backend-db.ps1 -Target postgres -RunMigrations
python scripts\smoke_check_live.py                                          # live pilot smoke check
```

### Full stack

`docker compose up` brings up `db` (postgres:16), `redis`, `minio` (+`minio-setup`), `backend`, `worker`, `nginx`. The worker entrypoint is `python -m app.worker.runner`. Production compose requires a filled `.env.production` — see the long required-vars list in `README.md`.

## Backend Architecture

### Layering (enforced)

```
Route (app/api/routes/*)  → request validation, auth, response contract
Service (app/services/*)  → workflow orchestration, storage policy, fail-fast
Repository (app/repositories/*) → DB access
ORM (app/models/*)        → persistence model
```

API is mounted under `settings.api_v1_prefix` (`/api/v1`). The **canonical** surface is `cases / images / analysis-jobs / measurements / estimates / pricebooks` (see `app/api/router.py`); legacy `/projects/*` aliases are gone — wire new routes through `router.py`. All routers except `system` and `auth` require a valid JWT (`Depends(get_current_user)`).

### Key subsystems (each has a spec in `docs/`)

- **Work catalog** (`app/work_catalog/`, `app/models/work_catalog.py`) — first-class subsystem with explicit boundaries: global catalog → tenant work-type settings → project work items → vision detections. Sparse tenant overrides; seed data + caching live here.
- **Vision pipeline** (`app/ai/`) — `PipelineOrchestrator` runs either a **staged** provider (`detect`/`extract`/`map_to_catalog`, implementing `StagedVisionPipeline`) or wraps a legacy single-shot provider via `LegacyProviderAdapter`. Routing is explicit by attribute presence; all current providers (mock/claude) use the legacy path until upgraded. Provider selected by `AI_ANALYSIS_PROVIDER` (`mock` in CI/dev).
- **Case workflow** (`app/case_workflow/`) — state machine: `transitions.py`, `case_actions.py`, `action_effects.py`. Send is guarded (e.g. `send` before final proposal → 409).
- **Offer processing** (`app/offer_processing/`) — budget/outbox/reconciler/snapshot for offer requests; has its own worker (`app/worker/offer_runner.py`, `offer_queue.py`).
- **Worker** (`app/worker/`) — Redis-backed job queue (`queue.py`), separate **heavy export/media lane** (`heavy_queue.py`) with its own concurrency/semaphore and lease reaper, plus heartbeat (`heartbeat.py`). The backend logs an ERROR and is not READY until a worker registers a fresh heartbeat. Workers follow the same storage rules as services (no local FS in prod).
- **Storage consistency** (`app/services/storage_consistency_service.py`) — orphan scan comparing DB photo/export refs against storage keys; `cleanup_orphans()` runs safe-mode by default and logs every action.

### Session factory routing (important)

`AsyncSessionFactory` is for **HTTP-originated** operations; `WorkerAsyncSessionFactory` is for the **background runner only**. Don't cross them.

### Startup behavior

`app/main.py` `lifespan` does fail-fast checks: DB connectivity, schema (in non-auto-create envs it asserts the DB is at the Alembic **head revision**, else refuses to start), storage health, and seed-credential audit (logs `CRITICAL SECURITY_EVENT` if a seed account still has its default password outside dev/test). Strict envs (anything not `development`/`test`) also fail-fast if prometheus_client / slowapi / configured Sentry are missing.

### Database modes

- Dev default: SQLite, `DB_AUTO_CREATE_SCHEMA=true`, `DB_SEED_ON_STARTUP=true`.
- Production-like: PostgreSQL, both `false`, schema via `alembic upgrade head`.
- New model changes go through **Alembic** even in dev. `DATABASE_URL` is async (app); `DATABASE_URL_SYNC` is sync (Alembic).

## CI & Governance

`.github/workflows/ci.yml` runs three parallel jobs aggregated by the required **`orchestration-release-gate`** status check (fails if any dependency failed *or was skipped*):
- `lint` — ruff + mypy + bandit + pip-audit on `python-backend`
- `web-lint` — typecheck + ESLint boundaries + dependency-cruiser architecture gate on `web`
- `test` — pytest (Postgres service) + live backend probes (`scripts/verify_deploy.py`, `test-api-contracts.py`, `test-auth-validation.py`, `test-business-flow.py`)

This repo enforces orchestration safety via the release gate, protected-core-file review discipline, and recovery rehearsal scenarios. Branch is `master`; commit/push only when asked.
