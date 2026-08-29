# Changelog

All notable changes to this project will be documented in this file.

## v0.8.4 — 2026-08-29

Milestone **M2 — AI Offer Contract Review**. Backend and governance only; no UI,
no pricing-engine and no schema changes.

### AI offer contract — measurements only

- **Full price separation** (Constitution Art. 2 & 3): the offer agent returns measured
  quantities, units, surface condition and confidence — **never prices**. Prices stay the
  pricing engine's job; `parsed_output` carries `pricing_status: "pending"`
- **Strict tool use** replaces free-text JSON parsing — two tools express the branch in the
  offer state machine (`submit_measurements` / `request_more_info`), with `tool_choice: any`
  forcing exactly one
- Validation layer reworked from `line_items`/prices to `measurements`: `RawMeasurementItem`,
  `ValidatedMeasurements`, plus `surface_condition` and `recommended_scope` enum checks
- `stop_reason: "refusal"` is now mapped to a non-retryable `ProviderRequestError`

### Fail-closed AI boundary (Art. 6 & 9)

- `offer_runner._resolve_ai_inputs()` raises `_AiInputResolutionError` when the work-type
  catalog cannot be resolved — the job fails instead of validating model output against a
  missing whitelist. The broad `except` now logs `offer_runner.catalog_resolution_failed`
  before re-raising (Art. 10)
- `OfferOutputValidator` rejects a `None` whitelist outright; an empty whitelist means
  "reject every code" — fail-closed on both paths
- Fixed input plumbing: the provider was receiving **photo IDs where presigned URLs were
  expected** and an empty `work_type_definition`; both are now resolved before the AI call

### Configuration

- `AI_OFFER_PROVIDER` selects the offer provider (`mock` / `claude`)
- `CLAUDE_VISION_MODEL` / `CLAUDE_OFFER_MODEL` are the single source of truth for model IDs
  (previously read via `os.getenv` inside the provider); defaults moved to the current
  generation, `claude-opus-5`

### Fixes

- `POST /measurements/{id}/confirm` wrote an outbox row with `organization_id=None` in a
  superadmin context, violating the NOT NULL constraint — it now falls back to the project's
  own tenant and skips the event (with a warning) if no tenant can be determined
- Idempotent offer-submit replay returns 200 via `response.status_code` instead of a bare
  `JSONResponse`, so the declared response model matches the wire contract (contract unchanged)

### Release gate repairs

`master` was red before this milestone; both linters are now clean over all of `app/`:

- `ruff` 18 → 0 — unused imports, `AiBudgetReservation` missing from `app.models.__all__`,
  module-level import ordering, undefined `datetime` in an annotation
- `mypy` 18 → 0 — `rowcount` via the repository `getattr` idiom, `Row[...]` → tuple unpacking,
  `event_id` narrowing in case-workflow effects, list concatenation, and `app.worker.offer_queue`
  added to the existing redis-stub override

### Tests

- New `tests/test_offer_ai_contract.py` — pins the measurements-only contract, both fail-closed
  paths (validator and runner), strict tool schemas, and tool-output extraction
- `conftest.py` emulates PostgreSQL's DB-managed `outbox_events.seq` on SQLite
- Repaired stale expectations in the analysis-route, case-transition and export-consistency tests

### Governance

- The M1 governance framework is now under version control: Constitution, Engineering Handbook,
  Change Control, Roadmap, Glossary, AI engineering standard, development standards and
  ADR-0001…0005
- `.gitignore` now excludes generated artifacts (product-book PDF and its intermediate HTML,
  Qt packaging output); the build script itself stays versioned

## v0.8.3 — 2026-05-28

### Proposal archive

- **Immutable `proposal-archive-zip`** generated at finalization: `proposal_snapshot.json`, `timeline.json`, `pricing_snapshot.json`, `manifest.json`
- **Signed manifest** — SHA-256 hash per file; tamper detection on open
- **Deterministic ZIP** — sorted filenames + ZIP-epoch timestamps; byte-identical rebuilds
- **`archiveSchemaVersion: 1`** in every JSON file — stable reader contract for future viewers

### Measurement lineage

- **`analysis_result_id` FK** on `project_final_proposals` (migration 0055) — full audit chain: proposal → analysis result
- **`inputVersions` snapshot** frozen at finalization: `analysisProfileCode/Version`, `catalogPricingProfileCode/Version`, `pricingProfileId`, full pricing rates (hourlyRate, margins, VAT, currency)
- **`measurement.confirmed` outbox event** emitted on `POST /measurements/{id}/confirm`
- **`GET /cases/{id}/timeline`** backed by real outbox query (replaced stub)

### Web UI

- **`CaseEstimatesPage`** — measurement timeline with filter chips (Vše / AI / Ceník / Uživatel / Systém) and `ProposalProvenancePanel` showing frozen input versions
- **`PhotoViewerPage`** — hydrates polygon selection from `latestAnalysis.selectedRepairPolygon` on mount (fixes "Confirmed ✓ disappears on refresh")
- **`/archive-viewer`** — offline archive viewer: drag-and-drop ZIP, `fflate` client-side parsing, Web Crypto SHA-256 manifest verification, integrity badge, offline timeline + provenance

### Tooling

- **`scripts/check_archive_integrity.py`** — offline CLI validator; exit 0 / 1 / 2 (OK / warning / error); checks required files, schema version, timeline envelope, lineage consistency, manifest hashes

### Pilot ops

- `scripts/Generate-PilotCert.ps1` / `Trust-PilotCert.ps1` — self-signed TLS for internal pilot
- `scripts/Build-ComposeEnv.ps1`, `python-backend/scripts/create_pilot_admin.py`
- `desktop-qt/scripts/Package-Pilot.ps1`
- `python-backend/.env.production.example`

### Qt desktop (audit steps 3–10)

- Directory restructure: `src/ui/`, `src/models/`, `src/state/`, `src/core/`
- API layer split: `ApiClient`, `AuthApi`, `CasesApi`, `ImagesApi`, `AnalysisApi`, `ExportsApi`, `AdminApi`
- Cursor-based pagination, centralized `Config.h`, removed unused `LoginDto`/`LoginViewModel`

### Migrations

0045 – 0055 (outbox events, offer pipeline, AI budget, reconciler, analysis_result_id on final proposals)

---

## v0.8.001 - 2026-04-19

Case workflow and work catalog expansion: explicit project status machine, status transition actions with audit trail, phase-bound work type availability, large catalog seed expansion, and case-aware work item picker flows in the web UI.

### Case Workflow And Status Machine

- Added a dedicated backend `case_workflow` subsystem for valid transitions, action mapping, effects, and status guard logic
- Introduced Alembic migration `20260417_0044_project_status_machine.py` with expanded project status enum, audit columns, organization+status index, and immutable `project_status_history`
- Extended project domain models, schemas, repository paths, API dependencies, and service orchestration to support intake/analyzing/proposal/quote/cancel states plus transition reasons
- Added backend regression coverage for status constraints, transition effects, and case workflow API flow

### Work Catalog Expansion

- Added explicit `phase_bindings.py` registry so each work type declares allowed case states, recommended case states, and AI-vision detectability
- Expanded catalog seed data with a significantly broader set of work type parameters, pricing profiles, and granular tree-aligned intervention codes
- Extended work catalog schemas and services so effective work types expose phase binding metadata to both backend consumers and the web frontend
- Hardened work catalog API tests and core subsystem coverage around phase-aware effective configuration

### Web Case Workspace

- Added `features/cases` web module with status badge, phase indicator, workflow actions, typed case queries, and shared case workspace context owned by `CaseLayout`
- Reworked the case work-items tab around a case-aware work type picker with `WorkTree`, search, and command palette entry points sharing one selection contract
- Added command palette UX for work type creation: click-to-open trigger, keyboard shortcut, mobile full-screen presentation, and case-phase overlays for allowed/recommended items
- Added action-layer stabilization for work item creation while preserving page-owned toast feedback and layout-owned case detail ownership

### Documentation

- Extended `docs/pr-checklist.md` with additional review guardrails for query boundaries, orchestration ownership, and cross-feature drift checks

## v0.8.000 - 2026-04-17

Markers system: user and AI annotations on project photos with normalized coordinates, full CRUD API, mobile integration, and web frontend architecture documentation.

### Markers Feature

- New `Marker` ORM model with four types: `defect`, `note`, `ai_detection`, `measurement`
- Two immutability modes: `user` (operator-created, editable) and `ai` (pipeline-written, append-only)
- Normalized 0–1 coordinate system with optional bounding box (`x`, `y`, `width`, `height`)
- Indexed on `case_id`, `image_id`, and compound `(case_id, marker_type)` / `(case_id, marker_source)` for efficient filtering
- Two Alembic migrations: add markers table + add `marker_source` column
- Dedicated `MarkerRepository` with `create`, `list_by_case`, `list_by_image`, `get`, `delete`
- REST API (`GET /markers`, `POST /markers`, `DELETE /markers/:id`) with tenant scoping and rate limit (`RATE_LIMIT_MARKER_WRITE`, default 30/minute)
- Pydantic schemas with `field_validator` bounds-checking for normalized coordinates

### Mobile App — Markers Integration

- `MarkerOverlay.tsx` — SVG overlay component with normalized-to-pixel coordinate mapping
- `MarkerPhotoView.tsx` — photo view with interactive marker layer
- Marker API service and types in `api.ts` / `types/index.ts`
- Project detail page updated to display and manage markers

### Worker Cancellation Handling

- Fixed `_run_job_task` to correctly handle `asyncio.CancelledError`: logs cancellation with full job/tenant context and skips finalize-state validation for cancelled tasks

### Test Coverage Expansion

- Expanded `test_health_readiness_semantics.py`, `test_retry_system.py`, `test_worker_runner.py`, `test_chaos_failure_scenarios.py` with additional scenario coverage
- Minor assertion hardening in remaining test files

### Documentation

- `docs/web-frontend-architecture.md` — web frontend architecture document: feature structure, transport layer rules, actor API contract, cross-feature dependency matrix, query key naming, impersonation semantics, mutation ownership, implementation risk analysis, and enforcement tooling guidance

## v0.7.004 - 2026-04-11

Stabilization release focused on deterministic worker/runtime behavior, explicit retry and readiness contracts, stable Prometheus metrics, and integration hardening across security-critical routes and queue processing.

### Backend Stability And Runtime Gating

- Refactored retry and dead-letter reprocess decision flow in `analysis_service.py` so authoritative job reads, state guards, scope guards, retry ceilings, and tenant active-job limits execute in explicit deterministic order.
- Narrowed top-level readiness gating to truly critical dependencies only: startup integrity, database, storage, and queue runtime.
- Preserved fail-closed behavior for real outages while allowing clean recovery back to HTTP 200 after dependency restoration.
- Clarified worker processing readiness vs API readiness so idle state and clean shutdown are treated as degraded or stopped, not as full incidents.

### Metrics Contract Hardening

- Stabilized Prometheus metric contracts for names, HELP/TYPE metadata, label names, label order, and shared text export formatting.
- Added canonical tenant metric label normalization for `tenant_id`, including deterministic `unknown` and `superadmin` handling.
- Unified API and worker metrics export rendering so observability surfaces share one authoritative contract.

### Security And Dependency Wiring

- Removed fragile implicit framework context coupling from security-critical route flows by moving Redis and queue handles to explicit dependencies where required.
- Preserved production enforcement behavior while preventing `request.app` / `request.scope["app"]` leakage from deciding security outcomes in tests or direct-call paths.

### Queue, Worker, And Test Hardening

- Fixed worker DB pool sizing so pool size, effective pool size, engine `pool_size`, and capacity all match `worker_concurrency` with `max_overflow = 0`.
- Fixed event-loop ownership issues in the D1 analysis end-to-end flow by creating async clients and related async fixtures per test loop.
- Hardened flaky timing assertions to use repeated measurements with median-based evaluation instead of single noisy samples.
- Fixed worker-runner teardown/test hangs by isolating scheduled retry promotion in unit tests that exercise invalid queue payload and background task flows.
- Expanded regression coverage around readiness, metrics, worker isolation, retry flow, upload guards, and security-critical routes.

## v0.7.003 - 2026-04-06

Observability & resilience hardening: per-tenant metrics, storage instrumentation, worker readiness invariant, multi-instance heartbeat scan, photo startup reconciliation, export sync-fallback removal, and five new Prometheus alerts.

### Prometheus Alerting (5 new rules)

- `DeadLetterQueueGrowing` — warns when jobs accumulate in dead-letter queue for >5 min.
- `RetryQueueSurge` — warns on retry rate >0.5/s over 10 min (retry storm detection).
- `HeavyQueueBacklog` — warns when heavy (export/media) queue exceeds 20 jobs for 15 min.
- `AuthFailureSpike` — warns on auth failure rate >0.5/s for 2 min (brute-force / credential stuffing).
- `RedisRuntimeDegraded` — warns when worker heartbeat falls into degraded Redis mode.

### Per-Tenant Metrics

- `novu_job_outcomes_total` and `novu_job_duration_seconds` gain a `tenant_id` label — enables per-org job analysis.
- `novu_auth_failures_total` gains a `tenant_id` label — enables per-tenant auth anomaly detection.
- `observe_job_outcome()` accepts optional `tenant_id` parameter; unknown context stored as `"unknown"`.

### Storage Instrumentation

- Added `novu_storage_operations_total` counter — tracks every storage op by `operation`, `backend`, and `outcome`.
- Added `novu_storage_operation_duration_seconds` histogram — storage latency distribution by operation, backend, outcome.
- Both local and S3 storage backends instrumented.

### Worker Readiness Invariant

- `/ready` now requires a live worker **and** a healthy queue in addition to API state — prevents routing traffic when background processing is unavailable.
- Worker-not-alive condition logs an ERROR at most once per 60 s (throttled via `_log_worker_not_alive_if_due`).
- `/ready/processing` uses `api_state` independently so worker-liveness invariant does not collapse `apiReady` in processing-readiness responses.

### Multi-Instance Heartbeat Scan (`scan_alive_workers`)

- New `scan_alive_workers(redis)` in `heartbeat.py` — scans all `worker:heartbeat:*` keys in Redis.
- Returns `(alive_count, last_seen_at_iso)`; handles legacy single-key format; returns `(-1, None)` on Redis failure.
- Enables correct liveness detection when multiple worker instances run concurrently.

### Photo Startup Reconciliation

- New `_reconcile_startup_photos()` in `runner.py` — mirrors export reconciliation for the photo variant processing lane.
- Re-enqueues photos stuck in `uploaded`/`processing` state after a Redis restart or flush — prevents silent stalls.

### Export Sync-Fallback Removal

- Removed inline synchronous DOCX/PDF generation path (`queue_enabled` branching) from `ExportService`.
- Exports now unconditionally require a running worker; returns HTTP 503 via `require_worker_capacity()` when heavy lane is disabled — eliminates hidden sync execution and unpredictable latency spikes.

### Backpressure Guard

- `require_worker_capacity(surface, *, settings)` added to `backpressure.py` — raises HTTP 503 when `worker_heavy_concurrency == 0`; records `backpressure_rejection` metric with `reason="heavy_lane_disabled"`.

### Audit Documentation

- `docs/monitoring_observability_audit_2026-04-06.md` — full monitoring & observability audit.
- `docs/chaos_failure_audit_2026-04-06.md` — chaos/failure scenario audit.
- `docs/infra_hardening_audit_2026-04-06.md` — infrastructure hardening audit.
- `docs/backup_restore_readiness_audit_2026-04-06.md` — backup & restore readiness audit.

## v0.7.002 - 2026-04-05

Security audit hardening: read-path rate limiting, per-tenant/per-user quotas, DB pool 503, page cap, AI quota fail-closed, per-org rate limit key, and worker identity logging.

### Read-Path Rate Limiting (P1 Fix)

- Added `RATE_LIMIT_READ_LIST` (120/min) and `RATE_LIMIT_READ_DETAIL` (60/min) config settings — both in `_STRICT_REQUIRED_FIELDS`, startup fails in production if not set.
- Applied `@limiter.limit` to 21 previously unprotected GET endpoints across `cases`, `pricebooks`, `suppliers`, `material_catalog`, `estimates`, `exports`, `images`, `work_catalog`, and `analysis_jobs` routes.

### Material Catalog Tenant Isolation (P2 Fix)

- Replaced `current_user.organizationId` with `resolve_org_id()` in all `material_catalog` handlers — prevents superadmin cross-tenant data leak.

### ILIKE Wildcard Injection Hardening (P2 Fix)

- Added `app/core/sql_like.py` with `escape_like()` helper.
- Applied to admin audit log search and `material_catalog_repository` (consistent with existing `project_repository` pattern).

### DB Pool Exhaustion → 503 (T1 Fix)

- Added `SQLAlchemyPoolTimeoutError` exception handler in `main.py` — returns HTTP 503 with retryable error message instead of 500.
- Increments `novu_db_pool_exhausted_total` Prometheus counter for alerting.

### Config-Driven Case List Page Cap (T3 Fix)

- Added `CASES_PAGE_LIMIT_MAX` setting (default 200, max 500).
- Applied `min(requested_limit, hard_limit)` in `list_cases` handler — prevents memory spikes at scale as an independent layer from the query validator.

### Per-User Rate Limiting (S4 Fix)

- `limiter.py` key function extracts JWT `sub` claim from `Authorization` header — authenticated requests bucketed per user ID, not per IP.
- Multiple users behind shared NAT/proxy get independent quotas.
- Falls back to remote IP for unauthenticated endpoints; JWT signature not verified in key function (rate limit bucket only).

### Per-Tenant Rate Limiting (Bod 2)

- JWT access tokens now include an `org` claim (`organization_id`) for all non-superadmin users.
- `_rate_limit_key()` prefers `org:<org_id>` over `user:<sub>` — rate limits enforced at tenant level matching billing semantics. Superadmins fall back to `user:<sub>`.

### Daily AI Analysis Quota per Tenant (B2 Fix)

- Added `AI_ANALYSIS_DAILY_QUOTA_PER_TENANT` setting (default 0 = unlimited).
- Redis counter key: `ai-daily-quota:{org_id}:{YYYY-MM-DD UTC}`, TTL 25 h.
- Quota check runs before `_enforce_queue_precheck` in `_create_analysis_job`.
- **Fail-closed in production/staging**: when Redis is unavailable, returns HTTP 503 instead of silently bypassing quota — prevents unbounded AI spend.
- Retries and dead-letter re-enqueues are exempt (not new AI calls).

### Worker Instance Identity (Bod 3)

- `worker.started` log now includes `hostname`, `pid`, and `worker_instance_count` explicitly.
- `multi_instance_safe=True` documented — lease/heartbeat system is already safe for concurrent instances.

### Repo Hygiene & CI Gates

- `.gitignore`: added `**/.env` and `**/.env.*` subdirectory-level guards.
- `scripts/ci-check-no-secrets.sh`: CI gate that blocks tracked `.env` files.
- `scripts/hooks/pre-commit`: pre-commit hook blocking `.env` commits and secret patterns.

### SLO Subsystem

- Added `app/core/slo.py` and `ops/alerting/slo-rules.yml` — SLO tracking layer with Prometheus rules.
- Added `docs/production-slo-system.md` and `docs/incident-rehearsal-scenare.md`.

### Security Audit Documentation

- Added `docs/23_security_audit_2026-04-05.md` — binding security audit document covering all P0/P1/P2 findings and their resolution status.

### Tests

- 145 tests pass; new coverage added for CORS hardening, CSP hardening, seed password detection, material catalog tenant resolution, query hardening, SLO, retry system, and startup fail-fast messages.

---

## v0.7.001 - 2026-04-02

Backpressure subsystem, fail-closed auth throttle, timing oracle hardening, worker startup reconciliation, and expanded system health readiness endpoint.

### Backpressure Subsystem

- Added `app/core/backpressure.py` — global backpressure control layer across both analysis and heavy worker lanes:
  - `BackpressureSnapshot` (frozen dataclass) aggregates queue depths, processing counts, retry inflight, and configured limits into a single decision surface.
  - `ensure_analysis_intake_capacity()` and `ensure_heavy_intake_capacity()` raise HTTP 429/503 before a job is enqueued when the lane or global queue is full.
  - `ensure_retry_budget()` prevents retry storms by enforcing a configurable concurrent-retry ceiling.
  - Job priority routing: `quote_recalculation` → `PRIORITY_CRITICAL` (LPUSH), `export_generate` → `PRIORITY_CRITICAL`; all others → `PRIORITY_STANDARD` (RPUSH).
- Added `BACKPRESSURE_MAX_CONCURRENT_JOBS`, `BACKPRESSURE_MAX_QUEUED_JOBS`, `BACKPRESSURE_MAX_RETRY_INFLIGHT` config fields with derived property defaults and cross-field validation guards (startup fails if limits are inconsistent with worker slot configuration).
- Wired backpressure snapshot into `AnalysisService.create_analysis_job()` and retry path; both raise structured 429/503 responses with `record_backpressure_rejection()` metrics.

### Fail-Closed Auth Throttle (P0-2 Fix)

- Reworked `app/core/account_limiter.py` to fail-closed: when the Redis backend is unavailable, `AccountThrottleBackendUnavailableError` is raised instead of falling back to a per-process in-memory counter.
- Added `_raise_backend_unavailable()` helper that logs `account_limiter.backend_unavailable` and raises the error, ensuring the auth layer propagates 503 rather than silently degrading to pod-local state.
- Eliminates multi-instance brute-force bypass: no in-memory fallback means throttle truth is always shared-store or denied.

### Timing Oracle Hardening

- Added `app/core/tenant_timing.py` with `enforce_timing_floor()` — async helper that pads response time to a minimum floor (`TENANT_SENSITIVE_TIMING_FLOOR_SECONDS = 0.012 s`, `CACHE_ACCESS_TIMING_FLOOR_SECONDS = 0.004 s`) on cross-tenant sensitive operations.
- Applied to tenant-effective resolution and cache-miss paths to eliminate timing side channels that could allow cross-tenant resource enumeration via response-time measurement.
- Added `test_tenant_timing_hardening.py` covering floor enforcement, no-op for fast paths, and async correctness.

### Worker Queue Hardening

- Extracted shared `_QUEUE_CAPACITY_GUARD_LUA` Lua helper used by `_ENQUEUE_WITH_LIMIT_SCRIPT`, `_FINALIZE_EXPIRED_LEASE_SCRIPT`, and heavy queue equivalents — capacity guard logic is now a single canonical implementation.
- `_ENQUEUE_WITH_LIMIT_SCRIPT` extended with global queued-jobs check in addition to per-lane depth check; returns `-2` for global capacity exhaustion (distinct from `-1` lane-full).
- `_LEASE_JOB_SCRIPT` checks `max_concurrent_jobs` before dequeuing — workers stop pulling jobs when global concurrency ceiling is reached, preventing over-scheduling during backpressure events.
- Priority-aware push: critical jobs use `LPUSH` (head of queue), standard jobs use `RPUSH` (tail), implemented atomically inside the Lua guard script.

### Worker Startup Reconciliation

- Added `_reconcile_startup_analysis_jobs()` in `runner.py` — on worker startup, reconciles Redis queue state against DB active jobs:
  - Orphaned queue entries (present in Redis but absent from DB) are purged via `purge_analysis_job_transport()`.
  - Orphaned retry ZSET entries are similarly cleaned up.
  - Prevents ghost jobs from stale Redis state after crash/restart from blocking worker slots.

### Deterministic Retry Backoff Jitter

- Added `_retry_backoff_jitter_seconds()` in `analysis_service.py` using `hashlib.blake2s(f"{job_id}:{attempt_count}")` to produce deterministic, job-stable jitter — same job always gets same jitter offset, eliminating thundering-herd retry collisions without randomness.
- Added `_retry_backoff_jitter_window_seconds()` to scale jitter window proportionally to backoff delay up to `_MAX_RETRY_JITTER_SECONDS = 30`.

### Expanded System Health Endpoint

- Reworked `GET /system/health` response in `app/api/routes/system.py` into a structured `_SystemStateSnapshot` covering: `startup_state`, `api_state`, `processing_state`, `redis_state`, `db_state`, `storage_state`, `queue_state`, `worker_state`, `auth_protection`, `operational`, `job_processing`.
- Added `_AuthProtectionSnapshot` — reports whether brute-force protection is enforced and its source.
- Added backpressure metrics to health response: current concurrent/queued/retry-inflight vs. configured maximums.
- New Prometheus metrics: `BACKPRESSURE_CURRENT_CONCURRENT`, `BACKPRESSURE_CURRENT_QUEUED`, `BACKPRESSURE_CURRENT_RETRY_INFLIGHT`, `BACKPRESSURE_MAX_*`, `HEAVY_QUEUE_LENGTH`, `HEAVY_PROCESSING_JOBS`, `REDIS_RUNTIME_AVAILABLE`, `REDIS_RUNTIME_DEGRADED`, `STORAGE_READY`, `AUTH_PROTECTION_ENFORCED`.

### Second Pilot Deployment Audit

- Added `AUDIT_PILOT_2026-04-02_v2.md` — full risk audit against v0.7.000 codebase identifying 5 P0 and 4 P1 risks including missing CSP header, invalid finalize_action fallback, tenant filter enforcement, hardcoded seed passwords, and metrics auth guard.

### Tests

- Added `test_tenant_timing_hardening.py` for timing floor enforcement.
- Extended `test_r08_account_throttle.py` with fail-closed Redis scenarios.
- Extended `test_r19_job_queue.py` with backpressure snapshot and priority routing coverage.
- Extended `test_retry_system.py` with deterministic jitter and retry budget enforcement tests.
- Extended `test_worker_runner.py` with startup reconciliation and capacity-blocked reaper tests.
- Extended `test_health_readiness_semantics.py` with full system state snapshot assertions.
- Extended `test_r32_cache.py` with timing floor integration.

### Notes

- No new Alembic migrations in this release — all changes are application-layer only.
- `BACKPRESSURE_MAX_*` config fields default to `0` (auto-derived from worker concurrency and queue depth settings); explicit values override the derivation.
- Fail-closed auth throttle is a breaking behavioral change: Redis unavailability now returns HTTP 503 on auth endpoints instead of silently allowing requests through.

## v0.7.000 - 2026-04-02

Pilot readiness hardening: per-session token revocation, worker healthcheck, analysis job payload offload, JSONB audit logs, deterministic token invalidation, and pre-pilot operational rehearsal tooling.

### Session Management And Token Revocation

- Added `user_sessions` table (migration `20260401_0037`) with per-session lifecycle tracking: `access_jti`, `refresh_jti`, `revoked_at`, and device metadata columns with CASCADE delete on user removal.
- Added `users.token_version` counter (migration `20260401_0040`) for deterministic global token invalidation — incrementing the counter invalidates all existing tokens for a user without touching the `revoked_tokens` table.
- Extended `AuthService` with session creation, per-session revocation, and active session listing.
- Added `GET /auth/sessions` and `DELETE /auth/sessions/{session_id}` routes for user-facing session management (force-logout from specific devices).
- Updated `TokenRepository` to cross-reference session table during JTI validation.

### Analysis Job Payload Offload

- Added `analysis_jobs.input_payload_storage_key` column (migration `20260401_0038`) to offload large input payloads from the main `analysis_jobs` table row into object storage.
- Reduces hot-row size for high-photo-count analysis jobs; payload is fetched lazily by the worker only when execution begins.
- Added `test_analysis_payload_offload.py` covering round-trip offload and fallback to inline payload for backward compatibility.

### JSONB Audit Logs

- Migrated `audit_logs.detail` column from `TEXT` to `JSONB` (migration `20260401_0039`) on PostgreSQL; SQLite remains TEXT for dev/test environments.
- Enables structured GIN-indexed queries on audit detail payloads without application-side JSON parsing overhead.
- Migration is safe on existing data: performs in-place `USING detail::jsonb` cast with NULL passthrough.

### Worker Healthcheck

- Added `app/worker/healthcheck.py` as a lightweight Docker healthcheck entrypoint; checks whether the local heartbeat file is fresh and exits 0 (healthy) or 1 (stale/missing).
- Wired into `docker-compose.yml` worker service: `interval: 30s`, `timeout: 10s`, `retries: 3`, `start_period: 30s`.
- Worker process is now restartable by the Docker orchestrator on zombie/stuck detection without manual intervention.

### Deterministic Seed IDs

- Added `app/work_catalog/seed_ids.py` with stable, hard-coded UUIDs for all 43 work catalog seed entries.
- Eliminates non-determinism in bootstrap across fresh environments and test fixtures; seed UUIDs are now constants referenced across tests and migrations.
- Added `test_seed_id_hardening.py` asserting UUID format, uniqueness, and registry completeness.
- Added `app/db/seed_runtime.py` for runtime seed data population decoupled from migration-time seeding.
- Added `test_seed_runtime.py` covering idempotent upsert behaviour and conflict resolution.

### Pilot Operational Rehearsal

- Added `docs/pilot-load-rehearsal.md` — step-by-step pilot load rehearsal procedure covering auth flow, case/photo flow, analysis queue orchestration, worker drain, and operational visibility checkpoints.
- Added `docs/pilot-operational-resilience-drill.md` — resilience drill scenarios: Redis restart, worker crash, DB connection spike, storage slowdown.
- Added `docs/operational-load-rehearsal.md` — larger operational load rehearsal guide for post-pilot scaling readiness.
- Added `scripts/run-pilot-load-rehearsal.py` and `scripts/run-operational-load-rehearsal.py` as executable rehearsal drivers using the mock AI provider.
- Added `test_operational_load_rehearsal.py` and `test_operational_resilience_drill.py` covering rehearsal smoke assertions and drill scenario setup/teardown.

### Pre-Pilot Security Audit

- Added `AUDIT_2026-03-31.md` — comprehensive security and operational audit covering authentication, multi-tenancy, storage, worker, and monitoring gaps.
- Added `AUDIT_PILOT_2026-04-02.md` — risk-focused pilot deployment audit with P0/P1/P2 classification, deployment checklist, and go/no-go verdict.

### Notes

- Four new Alembic migrations (0037–0040); apply in order before starting the application.
- `users.token_version` column defaults to `0` for existing rows — no data migration required.
- Worker healthcheck depends on `app.worker.heartbeat.local_worker_heartbeat_is_fresh()`; ensure `WORKER_HEARTBEAT_PATH` is writable in the container.

## v0.6.003 - 2026-03-31

Heavy workload lane separation, multi-pipeline Vision layer, and full-state DR operator documentation pack.

### Heavy Workload Lane Separation (Step 12)

- Added `app/worker/heavy_queue.py` — dedicated Redis-backed queue for export generation and photo variant processing, fully isolated from the analysis queue (`heavy:*` namespace vs `analysis:*`).
- Extended `WorkerRuntime` with a separate `heavy_concurrency_limiter` semaphore, independent lease timeout (`WORKER_HEAVY_JOB_LEASE_TIMEOUT_SECONDS`, default 1800 s), reap interval, and inflight task set.
- Added `HeavyWorkerJobExecutor` and `_run_heavy_job_task` in `runner.py` with the same lease-renewal and ack discipline as the analysis lane.
- Added `_run_heavy_lease_reaper_if_due` — independent reaper for expired heavy leases with requeue/drop semantics.
- Heavy lane is opt-in via `WORKER_HEAVY_CONCURRENCY` (default 0); setting it > 0 enables the lane without touching the analysis flow.
- Added `TestHeavyWorkerJobExecutor`, `TestRunHeavyJobTask`, `TestRunHeavyLeaseReaper`, and `TestHeavyWorkerLaneSeparation` test classes (38 tests total).

### Multi-Pipeline Vision Layer (Step 15)

- Added `app/ai/pipeline_contracts.py` with three frozen inter-stage data contracts: `DetectionStageResult`, `ExtractionStageResult`, `WorkCatalogMappingResult`, and the aggregating `PipelineRunResult` with `to_legacy_dict()` for backward compatibility.
- Added `app/ai/pipeline.py` with `StagedVisionPipeline` (`@runtime_checkable` Protocol), `LegacyProviderAdapter` (wraps existing providers), and `PipelineOrchestrator` with explicit routing: staged path for new providers, legacy path for mock/claude.
- Updated `app/ai/analysis_service.run_project_analysis()` to run through `PipelineOrchestrator`; downstream code (AnalysisService, repository) is unchanged — output dict is identical.
- Added `tests/test_vision_pipeline.py` with 39 integration tests covering contract immutability, decomposition safety defaults, routing, end-to-end legacy path with MockVisionProvider, synthetic staged provider path, and `run_project_analysis()` backward compatibility.

### Disaster Recovery Documentation

- Added `docs/18_full_state_dr_operator_runbook_2026-03-31.md` with the detailed operator procedure.
- Added `docs/19_full_state_dr_incident_checklist_2026-03-31.md` as the 1-page incident checklist.
- Added `docs/20_full_state_dr_copy_paste_playbook_2026-03-31.md` with exact command sequences.
- Added `docs/21_full_state_dr_handoff_template_2026-03-31.md` as the operator handoff record template.
- Added `docs/22_full_state_dr_approval_packet_2026-03-31.md` as the formal audit/compliance approval record.
- Updated `docs/BACKUP_RESTORE.md` to distinguish `db-only` and `db-plus-s3-media-manifest`.

## v0.6.002 - 2026-03-30

Work catalog subsystem expansion: analysis profile, pricing profile, tenant override, and runtime workflow subsystems fully wired and hardened.

### Analysis Profile Subsystem

- Added first-class versioned analysis profile subsystem with migration `20260331_0032`.
- Introduced structured target objects, extraction rules, validation guards, confidence thresholds, fallback behavior, and output mappings tied to analyzable work types.
- Added `analysis_profile_service.py` and `analysis_profile_seed_data.py` with profiles for all supported work types.
- Wired analysis jobs to carry work type plus resolved profile/version audit snapshots.
- Extended analysis results with generic quantity/unit fields for non-area work types.
- Updated AI vision providers (Claude, OpenAI, Mock) to consume catalog-driven analysis profiles.

### Pricing Profile Subsystem

- Added first-class versioned pricing profile subsystem with migration `20260331_0033`.
- Introduced structured required inputs, base rules, adjustment rules, labor assumptions, and material assumptions for all 43 seeded work types.
- Added `pricing_profile_service.py` and `pricing_profile_seed_data.py`.
- Added catalog-driven pricing execution service resolving effective pricing from work type + tenant override + runtime snapshot, validating required inputs, and returning explainable priced line items.
- Reworked quote variant recalculation to prefer runtime work items and catalog pricing rules, persisting pricing-rule audit metadata on quote items and pricing execution summaries on quote variants.

### Tenant Work Type Override Subsystem

- Added tenant-level work type settings and extra parameter override subsystem with migration `20260331_0034`.
- Added `TenantWorkTypeResolutionService` composing effective work type reads, runtime work item validation, analysis profile resolution, and pricing profile resolution from a single service.
- Added controlled tenant extra parameters with explicit definitions and option tables using `tenant.*` machine-readable codes to avoid collisions with the global catalog.
- Added runtime one-of binding so `project_work_item_values` can reference either a global parameter or a tenant extra parameter without ambiguity.
- Materialized tenant defaults into runtime value rows with normalized `source_type = default` semantics.
- Added tenant override subsystem documentation and new tests for tenant isolation, global fallback resolution, extra-parameter defaults, and collision guards.

### Runtime Workflow States

- Added migration `20260331_0035` for runtime workflow state tracking on project work items.
- Extended runtime rows with confirmation audit fields and source-detection linkage for pricing and downstream workflows.
- Added normalized runtime read/write operations: work item detail fetch, partial value update, value merge, and operator confirmation.
- Expanded runtime work item workflow with value-level source tracking, confidence, confirmation state, operator correction flow, and detection-backed merge semantics.

### Work Catalog Hot Path Hardening

- Added migration `20260331_0036` with dedicated global work type sort index and hot path composite indexes.
- Added `work_catalog/cache.py` with versioned shared cache keys, longer-lived Redis payload caches for stable catalog reads, and explicit tenant-effective invalidation helpers.
- Added in-process memoization for tenant-effective, analysis profile, and pricing profile resolution so repeated workflow reads do not rebuild the same catalog graph multiple times.
- Removed duplicated eager-load pressure from tenant setting resolution queries.
- Added work catalog cache hit/miss/error instrumentation plus resolution timing and validation failure metrics for Prometheus.

### Analysis Job Retry And DLQ

- Added migration `20260330_0027` for analysis job retry attempts and dead-letter queue status.
- Hardened worker runner and queue for DLQ routing, retry backoff, and dead job isolation.

### API And Route Expansion

- Added first-class global catalog read APIs for categories, work type list/detail, and parameter schema detail.
- Added project-scoped effective configuration API returning effective work type plus explicit vision and pricing dependency surfaces for workflow bootstrap.
- Reworked project work item detail API to return runtime snapshot, current effective configuration, and derived workflow hints.
- Added route-level cache coverage for global catalog reads and tenant-effective workflow bootstrap reads.
- Added `deps.py` dependency wiring for all new services.

### Documentation

- Added `docs/analysis_profile_subsystem.md` — architecture and contract reference.
- Added `docs/pricing_profile_subsystem.md` — pricing rule structure and extension guide.
- Added `docs/tenant_override_subsystem.md` — sparse delta model, collision guard rules.
- Added `docs/runtime_workflow_subsystem.md` — value lifecycle, source types, and confirmation flow.

### Tests

- Added `test_analysis_profile_subsystem.py`, `test_pricing_profile_subsystem.py` integration tests.
- Added `test_work_catalog_api_flow.py` for route/service API flow coverage.
- Added `test_work_catalog_operational_hardening.py` for seed bootstrap smoke, hot path resolution, and tenant cache invalidation.
- Added `test_retry_system.py` for DLQ routing and retry backoff behaviour.
- Updated existing queue, cache, and metrics tests for new service wiring.

### Notes

- All new subsystems are backwards compatible with the v0.6.001 work catalog foundation.
- Six new Alembic migrations (0027, 0032–0036) extend the schema; apply in order.

## v0.6.001 - 2026-03-30

Current release snapshot of the repository state prepared for GitHub versioning.

### Worker And Queue Hardening

- Added durable lease ownership with `lease_token` and `worker_id` verification during job processing.
- Hardened analysis execution for duplicate delivery, ACK-after-commit safety, and stale lease recovery.
- Added queue depth limits, per-tenant active job limits, and configurable worker concurrency.
- Expanded duplicate execution, stale job recovery, and concurrency test coverage.

### Work Catalog Core Subsystem

- Added a new `work_catalog` core domain module with explicit global catalog, tenant override, runtime work item, and vision detection boundaries.
- Introduced first-class entities for work categories, work types, typed parameters with options, analysis profiles, catalog pricing profiles, tenant work type settings, tenant work type parameter overrides, project work items, project work item values, and vision detections.
- Designed tenant override layer as a sparse delta model — tenant rows are only created when a setting differs from the global default, avoiding per-tenant catalog duplication at any scale.
- Added effective resolution logic, tenant-safe APIs, and cache-aware hot read paths for effective work type catalog access with explicit cache invalidation on settings write.
- Added centralized typed value validation in `work_catalog/domain.py` to eliminate `if/elif` work-type branching from routes and services.
- Added two Alembic migrations: `20260330_0028` for the core subsystem tables and `20260330_0029` for tenant parameter overrides and scaling indexes.
- Expanded the catalog into a full parametric schema system for all 43 seeded work types, with realistic per-type parameters across `dimensions`, `materials`, `condition_or_damage`, `access_and_complexity`, `quantity_scope`, and `optional_notes`.
- Added grouped `parameterSections` API output plus richer parameter metadata including bounds, enum options, vision extractability, and manual override flags for API/UI/mobile/vision/pricing/operator consumers.
- Added import-time guards for schema section coverage, parameter definition integrity, and enum completeness, plus DB-level integrity constraints for parameter defaults and runtime typed-value shape in `20260330_0031`.
- Made global catalog seeding canonical and idempotent by upserting source-of-truth catalog rows instead of inserting only missing definitions.
- Added subsystem integration tests and architecture documentation for long-term maintainability.
- Added a first-class versioned analysis profile subsystem with structured target objects, extraction rules, validation guards, confidence thresholds, fallback behavior, and output mappings tied to analyzable work types.
- Wired analysis jobs to carry work type plus resolved profile/version audit snapshots, and extended analysis results with generic quantity/unit fields for non-area work types.
- Added catalog-driven analysis profile resolution and output validation/mapping so vision orchestration can consume work type contracts without per-type branching in the service layer.
- Expanded catalog pricing into a first-class versioned pricing profile subsystem with structured required inputs, base rules, adjustment rules, labor assumptions, and material assumptions for all 43 seeded work types.
- Added a catalog-driven pricing execution service that resolves effective pricing configuration from work type + tenant override + runtime work item snapshot, validates required inputs, and returns explainable priced line items.
- Reworked quote variant recalculation to prefer runtime work items and catalog pricing rules, persisting pricing-rule audit metadata on quote items and pricing execution summaries on quote variants.
- Added a central `TenantWorkTypeResolutionService` so effective work type reads, runtime work item validation, analysis profile resolution, and pricing profile resolution all compose the same tenant-effective configuration.
- Added controlled tenant extra parameters with explicit definitions and option tables, using `tenant.*` machine-readable codes to avoid collisions with the global catalog.
- Added runtime one-of binding so `project_work_item_values` can reference either a global parameter definition or a tenant extra parameter definition without ambiguity.
- Materialized tenant defaults into runtime value rows with normalized `source_type = default` semantics, keeping backward-compatible alias handling for legacy `system` values.
- Added tenant override subsystem documentation and new tests for tenant isolation, global fallback resolution, extra-parameter defaults, and collision guards.
- Expanded runtime work item workflow with value-level source tracking, confidence, confirmation state, operator correction flow, and detection-backed merge semantics.
- Added normalized runtime read/write operations for work item detail fetch, partial value update, value merge, and operator confirmation.
- Extended runtime rows with confirmation audit fields and source-detection linkage so pricing and downstream workflows can consume stable normalized work item facts.
- Added first-class global catalog read APIs for categories, work type list/detail, and parameter schema detail so backend, mobile, and operator clients can consume the source-of-truth model directly.
- Added project-scoped effective configuration API that returns effective work type plus explicit vision and pricing dependency surfaces for workflow bootstrap.
- Reworked project work item detail API to return runtime snapshot, current effective configuration, and derived workflow hints instead of a flat runtime row only.
- Added route-level cache coverage for global catalog reads and tenant-effective workflow bootstrap reads, while keeping runtime work item reads uncached for correctness.
- Added route/service API flow tests for global catalog reads, effective configuration bootstrap, runtime create/detail/confirm flow, and tenant isolation on the new endpoints.
- Hardened work catalog hot paths with versioned shared cache keys, longer-lived Redis payload caches for stable catalog reads, and explicit tenant-effective invalidation helpers.
- Added in-process memoization for tenant-effective, analysis profile, and pricing profile resolution so repeated workflow reads do not rebuild the same catalog graph multiple times.
- Removed duplicated eager-load pressure from tenant setting resolution queries and added a dedicated global work type sort index in `20260331_0036`.
- Added work catalog cache hit/miss/error instrumentation plus resolution timing and validation failure metrics for Prometheus.
- Added operational hardening tests for seed bootstrap smoke, repeated resolution hot paths, and tenant cache invalidation.

### Observability And Operations

- Added Prometheus job metrics for queue depth, processing load, duration, fail rate, reaper requeues, and prevented duplicates.
- Enriched worker job logs with `job_id`, `tenant_id`, `worker_id`, `status`, and duration fields.
- Extended `/metrics` and internal health diagnostics with real-time job and queue visibility.
- Updated alert rules for queue backlog, elevated fail rate, and stuck job detection.

### Storage, Export, And Restore Hardening

- Continued hardening backup, restore, export TTL, and storage consistency flows.
- Improved backend storage services and validation scripts for safer operational recovery.

### Notes

- This version captures the current integrated project state on branch `master`.

## v0.2.0 - 2026-03-23

Current milestone based on commit `4e29351`.

### Desktop Qt

- Added first-run server setup dialog and persisted configurable backend URL.
- Expanded the workspace shell with welcome, help, troubleshooting, and navigation improvements.
- Improved case browser, case detail workflow, and desktop-first case creation flow.
- Continued polishing image handling, overlay workflow, and general desktop UX.

### Python Backend

- Added superadmin-protected admin API for company and user management.
- Added company schemas and service layer for organization and admin-user operations.
- Extended auth read model to include superadmin capability.
- Updated project/backend flow to align with newer desktop workflow needs.

### Notes

- This version builds on the earlier desktop workflow and backend hardening release tagged as `v0.1.0`.

## v0.1.0 - 2026-03-21

Baseline tagged milestone based on commit `5430077`.

### Highlights

- Major desktop UI overhaul and workflow hardening.
- Initial source-aware workflow support.
- Backend stabilization for project, auth, and pricing flow.
- Dev onboarding and local startup scripts prepared for faster setup.
