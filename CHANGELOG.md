# Changelog

All notable changes to this project will be documented in this file.

## v0.6.001 - 2026-03-30

Current release snapshot of the repository state prepared for GitHub versioning.

### Worker And Queue Hardening

- Added durable lease ownership with `lease_token` and `worker_id` verification during job processing.
- Hardened analysis execution for duplicate delivery, ACK-after-commit safety, and stale lease recovery.
- Added queue depth limits, per-tenant active job limits, and configurable worker concurrency.
- Expanded duplicate execution, stale job recovery, and concurrency test coverage.

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
