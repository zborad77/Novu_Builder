# Changelog

All notable changes to this project will be documented in this file.

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
