# NOVU Builder — Technical Roadmap

> Engineering roadmap, **not** marketing. Each version lists concrete scope and its release gate.
> Tags must match releases (see [development/VERSIONING.md](development/VERSIONING.md)).
> Milestone (Mx) tags map to [PROJECT_STATE.md](PROJECT_STATE.md).

**Released:** `v0.8.5` — Backend Stabilization / PostgreSQL test & CI hardening *(current)*

## Released

### v0.8.5 — Backend Stabilization · M3 — 2026-10-02
- PostgreSQL-first test baseline with guarded `NullPool` test profile and shared session factory
- Removed asyncpg/event-loop coupling and test-local engine drift
- CI uses real PostgreSQL 16 + Redis and starts a real worker for strict processing-readiness checks
- Fixed the final PostgreSQL-only CI failures without weakening or skipping tests
- Health/readiness verification aligned to `/alive`, rich runtime integrity payloads, and strict worker readiness
- `PyJWT` upgraded to 2.15.0; `pip-audit`, Bandit, Ruff and mypy green
- **Authoritative gate met:** 1452 passed / 0 failed, web checks green, post-deploy/API/auth/business-flow smoke green, `orchestration-release-gate` green

### v0.8.4 — AI Offer Contract (measurements-only) · M2 — 2026-08-29
- AI returns measurements / confidence / questions only; never prices (Constitution Art. 2 & 3)
- Strict tool use (guaranteed JSON), photos to the offer agent, model from config
- Fixed fail-open whitelist (Art. 6 & 9) + logging on the broad `except` (Art. 10)
- **Local gate met:** 1429 passed / 3 skipped / 0 failed, `mypy` 0 errors, `ruff` clean, no fail-open
- ⚠️ **CI gate was red at release time** due to pre-existing failures; M3 was opened to eliminate that debt

### v0.8.3 — proposal archive, measurement lineage, offline viewer — 2026-05-28

---

## Planned

### v0.8.6 — Fresh Install / Alembic Hotfix (unreleased)
- Frozen historical Alembic baseline; later revisions own their schema objects
- Forward `users.is_superadmin` migration; new head `20261003_0056`
- Required PostgreSQL 16 empty-database and existing-installation migration regressions
- `v0.8.5` remains immutable; its fresh-install migration blocker prevents empty-database deployment

### v0.8.7 — Catalog Validation Hardening
- Effective work-type whitelist as a first-class, **fail-closed** input to the offer validator
- Surface work-type parameter schema to improve measurement quality

### v0.8.8 — Pricing Engine Integration · M4
- Bridge AI measurements → catalog Pricing Engine (`calculate_project_work_item`) via a valid `ProjectWorkItem`
- Introduce first-class `pricing_pending → priced` state
- **Invariant:** Pricing Engine remains the only pricing authority (Art. 3); no second pricing path

### v0.8.9 — Proposal Generator
- Priced offer → proposal draft → immutable archive, end to end

### v0.9.0 — Complete AI Offer Pipeline
- Lead → photos → measurements → pricing → proposal, fully wired, audited, tenant-safe

### v0.9.5 — Frontend Feature Complete
- Qt desktop + web admin surfaces covering the full pipeline

### v1.0.0 — Production Release
- Production hardening, observability/SLOs, security sign-off (Constitution Art. 11)

---

## Documentation follow-ups

- Draft `docs/REPOSITORY_CHARTER.md` when the documentation workstream is reopened.
- Reconcile the older `development/VERSIONING.md` example that places Pricing Engine
  integration at v0.9.0; the current roadmap schedules it at **v0.8.8**, with v0.9.0
  reserved for the complete AI offer pipeline.
