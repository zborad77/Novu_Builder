# CLAUDE.md

<!-- novusion-development-hygiene:start -->
## Development hygiene (MANDATORY)

Follow the Novusion Development Hygiene skill, `.claude/skills/novusion-development-hygiene/SKILL.md`, in every task. Its mandatory core:

- **One project = one repository = one working directory.** Git worktrees, second checkouts and copies of a project are forbidden, whatever the reason; versions only via branches, commits and tags. Before switching a branch, keep every uncommitted change safe.
- **Never create anything outside the repository you work in** - no file, folder, script, log, cache, scratchpad, staging, backup or copy; nothing in `J:\tmp`, `J:\temp`, on other drives or in the user profile. Helper scripts and test data go into the repository's `test/`, build work into `build/`. A tool that writes TEMP outside: point its TEMP/TMP inside the project; if that is impossible, stop and report - never create an alternative workspace.
- **One `build/`, one `test/` (test sources in `tests/`), one `build.bat` entry point, one `dist/`** (`patch/`, `runtime/`, `release/`, `previous/`). No `build_core`, `build_new`, `build_cuda13`, numbered or timestamped folders, no second build script. A repository's established deviation named in its own `CLAUDE.md` / `AGENTS.md` is used until the owner agrees a plan - never added to.
- **Every folder exists exactly once;** no loose logs or notes in the repository root.
- **Retention:** `dist/release/` Release 1 only, `dist/patch/` at most 3, `dist/previous/` at most 3; never remove the patch baseline or a rollback target.
- **Start of the task:** check the repository, `git status`, `build/`, `test/`, `build.bat`, parallel build folders and free disk space; say in a line what you found. A violation found is recorded, never added to.
- **End of the task:** remove your own leftovers, check that no new folder appeared outside the structure, check `git status` and the size; report it.
- **Never delete automatically:** source, uncommitted changes, databases, user data, active builds or test environments, other agents' work, Release 1, the latest 3 releases, unknown files. Cleanup beyond your own leftovers: tag with the NovuExplorer `Delete` badge - the owner deletes.
- **Houdini / Unreal:** one project folder / one `.uproject` and one `Content/`; never copy a project; final assets, maps, Blueprints, plugins and approved simulations are protected.
- Applies to every technology: C++, Qt, Python, .NET, web, Houdini, Unreal and the rest.
<!-- novusion-development-hygiene:end -->

<!-- novusion-authorship-standard:start -->
## Authorship (MANDATORY)

Follow the Novusion Technology Authorship Standard skill, `.claude/skills/novusion-authorship-standard/SKILL.md`, in every task. Its mandatory core:

- **The author is Pavel Dostál, Novusion** (https://novusion.com, info@novusion.com).
- **Every new source file starts with the Novusion standard header**, exactly this, in its language's comment syntax (`#` lines for Python, PowerShell, CMake; `rem` for batch; `<!-- -->` for HTML/XML):

```
/*
 * Copyright (c) 2026 Novusion
 * Website: https://novusion.com
 * Contact: info@novusion.com
 *
 * Author: Pavel Dostál
 * Project: [Project Name]
 * Module: [Module Name]
 * Description: [Brief description]
 * Created: [YYYY-MM-DD]
 */
```

  `Created` is the day the file was created and never changes. Existing files keep their own headers - never rewrite historical information; vendored code keeps its own licence.
- **Claude or any other AI is never named as author, co-author or creator** - not in code, comments, metadata, UI, file names, documentation, package manifests or commit messages (no `Co-Authored-By:` AI lines, no "Generated with" lines).
- Binary assets (Unreal assets, geometry, textures) and JSON files need no header; their source code, scripts and shaders do.
- Before finishing a task: check the new files have the header, Novusion and Pavel Dostál are named correctly, and no AI is named as an author.
<!-- novusion-authorship-standard:end -->

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product

NOVU Builder (formerly FotoNabidka) is a SaaS product for rapidly building construction price quotes from field photos. The workflow: capture photos in the field → AI vision analysis + measurement → calculation → review/edit/send the quote from an office client.

Most code comments, docs, and commit messages are in **Czech**. Match that when editing existing files.

## Repository Layout

- `src/backend/` — **the backend** (FastAPI + SQLAlchemy 2.x async + Alembic + Pydantic v2). PostgreSQL/Redis/S3 in prod, SQLite/local-storage in dev. This is where almost all work happens.
- `src/desktop/` — **primary client**: C++/Qt6 Widgets office desktop app. Talks to the backend over HTTP at `http://127.0.0.1:8000/api/v1`.
- `src/frontend/` — React/Vite/TS. Admin portal only (browser); **not** the main client. UI, presentation state and API clients only — no business logic.
- `src/contracts/` — shared API contracts generated by the backend (OpenAPI, route order snapshot); a change here is a public API change.
- `novu-mobile/` — **FROZEN** (to be replaced by Qt for Mobile). Don't invest here.
- `scripts/` — repo-root PowerShell/Python dev, bootstrap, smoke, and verification scripts.
- `docs/` — architecture, blueprints, subsystem specs, audits, runbooks.
- `storage/` — local DEV-ONLY storage for images/exports.

Per `ARCHITECTURE.md`: **local storage is DEV ONLY**. In production, file reads/writes go through the active S3 backend; DB rows store storage *keys*, never public URLs; the API returns only time-limited signed URLs.

## Commands

### Backend (run from `src/backend/`)

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
lint-imports                         # module boundaries (layers, no cycles)
python -m scripts.export_contracts --check   # API/route/middleware/security baselines
pip-audit -r requirements.txt --progress-spinner=off
```

mypy must stay at **0 errors over all of `app/`** (per-module suppressions live in `pyproject.toml`; don't broaden them casually). Coverage gate in CI is `--cov-fail-under=40`.

### Desktop (run from `src/desktop/`, Windows + MSVC + Qt 6.x)

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

### Modular monolith (enforced)

The backend package `app` is a modular monolith — see `docs/architecture/MODULAR_ARCHITECTURE.md` (rules, how to add a module).

```
app/main.py, app/worker/, app/composition/   composition roots: router, wiring (ports), ORM model registry, bootstrap
app/modules/<module>/                        admin > offers > exports > workflow > quoting > analysis > catalog > media > cases > identity > audit
app/platform/                                shared core: config, http (exposure/gateway/client IP/limiter), db, jobs, events/outbox, storage
```

- Dependencies only point **down** that list; `lint-imports` (`[tool.importlinter]` in `src/backend/pyproject.toml`) enforces it, no cycles.
- Other modules, composition and worker import a module **only via `app.modules.<module>.public`**; no private names across modules (`tests/architecture/test_module_boundaries.py`).
- Calls "upward" go through ports wired in `app/composition/wiring.py::init_modules()`; every entrypoint (API, worker, scripts, tests) calls it. ORM relations across modules are string-declared; type-only imports under `TYPE_CHECKING`.
- Inside a module the old layering still applies: `api/` (routes, `deps.py`) → services → repositories → `models.py`.
- API contract, route order (exposure guard matches the first template), middleware order and the security surface are frozen in `src/contracts/` and `src/backend/tests/architecture/baseline/` (`python -m scripts.export_contracts --check`). Changing them = approved API change.

API is mounted under `settings.api_v1_prefix` (`/api/v1`). The **canonical** surface is `cases / images / analysis-jobs / measurements / estimates / pricebooks` (see `app/composition/router.py`); legacy `/projects/*` aliases are gone — wire new routes through `router.py` (append, never reorder). All routers except `system` and `auth` require a valid JWT (`Depends(get_current_user)`).

### Key subsystems (each has a spec in `docs/`)

- **Work catalog** (`app/modules/catalog/work_catalog/`, `app/modules/catalog/work_catalog/models.py`) — first-class subsystem with explicit boundaries: global catalog → tenant work-type settings → project work items → vision detections. Sparse tenant overrides; seed data + caching live here.
- **Vision pipeline** (`app/modules/analysis/ai/`) — `PipelineOrchestrator` runs either a **staged** provider (`detect`/`extract`/`map_to_catalog`, implementing `StagedVisionPipeline`) or wraps a legacy single-shot provider via `LegacyProviderAdapter`. Routing is explicit by attribute presence; all current providers (mock/claude) use the legacy path until upgraded. Provider selected by `AI_ANALYSIS_PROVIDER` (`mock` in CI/dev).
- **Case workflow** — state machine and effect registry in `app/modules/cases/` (`transitions.py`, `effects.py`); orchestration in `app/modules/workflow/` (`case_actions.py`, `action_effects.py`); export effects in `app/modules/exports/case_effects.py`. Send is guarded (e.g. `send` before final proposal → 409).
- **Offer processing** (`app/modules/offers/`) — budget/outbox/reconciler/snapshot for offer requests; has its own worker (`app/worker/offer_runner.py`, `offer_queue.py`).
- **Worker** (`app/worker/runner.py`) — Redis-backed job queue (`app/platform/jobs/queue.py`), separate **heavy export/media lane** (`heavy_queue.py`) with its own concurrency/semaphore and lease reaper, plus heartbeat (`heartbeat.py`). The backend logs an ERROR and is not READY until a worker registers a fresh heartbeat. Workers follow the same storage rules as services (no local FS in prod).
- **Storage consistency** (`app/modules/exports/storage_consistency_service.py`) — orphan scan comparing DB photo/export refs against storage keys; `cleanup_orphans()` runs safe-mode by default and logs every action.

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
- `lint` — ruff + mypy + bandit + `lint-imports` (module boundaries) + pip-audit on `src/backend`
- `web-lint` — typecheck + ESLint boundaries + dependency-cruiser architecture gate + `check:contracts` + build on `src/frontend`
- `test` — pytest (Postgres service) + live backend probes (`scripts/verify_deploy.py`, `test-api-contracts.py`, `test-auth-validation.py`, `test-business-flow.py`)

This repo enforces orchestration safety via the release gate, protected-core-file review discipline, and recovery rehearsal scenarios. Branch is `master`; commit/push only when asked.
