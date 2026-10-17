# Current Milestone

> **Single source of truth** for "what is being worked on right now". One milestone at a time.
> Every AI agent and contributor MUST read this before starting work, and MUST NOT start work
> outside it. Update this file when a milestone opens or closes.

**Milestone:** M3 — Test Isolation & PostgreSQL Async Infrastructure  
**Status:** CLOSED  
**Version target:** v0.8.5 — see [ROADMAP.md](ROADMAP.md)  
**Opened:** 2026-09-04  
**Closed:** 2026-10-02

## Goal

Establish a trustworthy PostgreSQL test baseline and make the authoritative
`orchestration-release-gate` fully green without weakening test isolation.

## Close-out evidence

- PostgreSQL test infrastructure uses the guarded non-strict test engine profile
  with `NullPool`, plus one shared session factory for integration tests.
- The asyncpg cross-event-loop failure class was eliminated:
  no `attached to a different loop`, `another operation is in progress`,
  `InterfaceError`, or pooled-connection leakage remains in the authoritative run.
- The remaining PostgreSQL-only failures were corrected at their actual test/fixture
  boundaries: deterministic backup-manifest selection, SQLAlchemy-safe JSONB casting,
  and a valid audit-user FK in the work-catalog inconsistency test.
- CI now supplies the real Redis dependency required by the queue path and runs a real
  worker before strict processing-readiness verification.
- Health/readiness verification follows the current runtime contract:
  `/alive` for process liveness, rich `/health` / `/ready` integrity payloads,
  and `/ready/processing?strict=1` for the worker-backed processing path.
- `PyJWT` was raised from 2.13.0 to 2.15.0; the production dependency
  `pip-audit` check passes without suppressions.
- Authoritative GitHub Actions on `master` commit
  `5ce81669eb8354537c0a98b842cb4263dab3705e`:
  - `1452 passed, 0 failed`, 73.62% coverage
  - `ruff`, `mypy`, `bandit`, `pip-audit` — PASS
  - web typecheck, ESLint, dependency-cruiser — PASS
  - post-deploy verification, API/auth/business-flow smoke — PASS
  - `orchestration-release-gate` — PASS
  - Repo Guard — PASS

## Delivered in M3

- PostgreSQL-first, CI-faithful test baseline.
- Test engine isolation that preserves production/staging pooling behavior.
- Removal of test-local engines and hidden environment/path dependencies.
- CI Redis dependency and worker-backed post-deploy verification.
- Final repair of the five previously exposed PostgreSQL CI failures.
- Security/dependency gate restored to green.
- Verification scripts aligned with the implemented liveness/readiness architecture.

## Known follow-ups — not M3 blockers

- `ck_catalog_pricing_profile_material_assumptions_quantity_source` is exactly
  63 characters and has no PostgreSQL identifier headroom.
- `.coverage` is generated locally but is not currently ignored.
- API/OpenAPI `app_version` is not synchronized with repository releases.
- Remote release/tag history before v0.8.4 requires separate review.

## Release state

M3 is closed. The v0.8.5 release close-out follows the normal release process:
merge this documentation/config cleanup, require the authoritative CI gate to
remain green on `master`, then tag that exact commit as `v0.8.5`.

M3 remains closed. The active stabilization target is **v0.8.6 — Fresh Install /
Alembic Hotfix (unreleased)**: freeze the historical baseline, migrate
`users.is_superadmin`, and require independent PostgreSQL migration regressions.
The next feature release is v0.8.7 — Catalog Validation Hardening; not opened yet.

---

## Previous milestone — M2, closed 2026-08-29

**M2 — AI Offer Contract Review**, released as `v0.8.4`. M2 established the
measurements-only AI offer contract and fail-closed catalog boundary. The
pre-existing red CI gate that remained after M2 is what opened M3.
