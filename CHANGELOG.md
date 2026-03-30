# Changelog

All notable changes to this project will be documented in this file.

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
