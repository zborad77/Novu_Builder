# NOVU Builder — Project State

> Living status snapshot **and** active-work governance. **Not** architecture
> (see [NOVU_ENGINEERING_HANDBOOK.md](NOVU_ENGINEERING_HANDBOOK.md)) and **not** rules
> (see [NOVU_CONSTITUTION.md](NOVU_CONSTITUTION.md)). This file answers two questions:
> *where are we right now?* and *what is allowed right now?* Update on every merge and milestone.

**Last updated:** 2026-10-03
**Current release line:** v0.8.5 — Backend Stabilization / M3 close-out  
**M3 code baseline:** `master` at `5ce8166`; authoritative GitHub CI and Repo Guard green.

M3 repaired the release-gate debt that was still present when v0.8.4 was tagged.
The important outcome is not merely a locally green suite: PostgreSQL 16, Redis,
the live backend, a real worker, security scanning, web checks, and the aggregate
release gate now run successfully together in GitHub Actions.

The v0.8.4 release-over-red-gate event remains a historical process deviation.
v0.8.5 must be tagged only from the final close-out commit after its own
authoritative `master` CI is green.

---

## Current Development Focus

The active milestone, its blocking issues, and close-out state live in
**[CURRENT_MILESTONE.md](CURRENT_MILESTONE.md)**. Change-class requirements:
**[CHANGE_CONTROL.md](CHANGE_CONTROL.md)**. Version plan:
**[ROADMAP.md](ROADMAP.md)**.

**Current milestone:** M3 — Test Isolation & PostgreSQL Async Infrastructure — **CLOSED**  
**Release target:** `v0.8.5`  
**Active hotfix target:** `v0.8.6` — Fresh Install / Alembic Hotfix (**unreleased**).
The released `v0.8.5` tag remains immutable; a fresh empty PostgreSQL installation
fails because revision 0001 creates later migration objects from live metadata.
The hotfix freezes that baseline, versions `users.is_superadmin` at `20261003_0056`,
and adds a required independent PostgreSQL migration check.
**Next planned feature release:** `v0.8.7` — Catalog Validation Hardening; not opened yet.

---

## Completed

- ✓ **M1 — Documentation & governance framework** — Constitution, Handbook, AI Engineering Standard, AI guides, Project Invariants, Decision Log, Prompt Library, development standards, this file, ROADMAP
- ✓ **M2 — AI measurements-only offer contract** — AI returns measurements / confidence / questions only, never prices. Fail-closed catalog whitelist enforced at both runner and validator. Closed 2026-08-29; released as v0.8.4.
- ✓ **M3 — Test Isolation & PostgreSQL Async Infrastructure** — PostgreSQL test isolation, asyncpg loop-safety, CI portability, release-gate hardening, worker-backed operational verification. Closed 2026-10-02; release target v0.8.5.
- ✓ Multi-tenant SaaS core, offer pipeline resilience (lease fencing, outbox, AI budget), immutable proposal archive (v0.8.3)

## Work streams

| Stream | Milestone | Status |
|---|---|---|
| Documentation framework | M1 | ✅ complete |
| AI Offer Contract (measurements-only) | M2 | ✅ released as v0.8.4 |
| CI / release-gate stabilization | M2→M3 | ✅ Repo Guard + all CI jobs green |
| Test isolation & PostgreSQL async infrastructure | M3 | ✅ closed 2026-10-02 |
| Fresh-install / Alembic hotfix | v0.8.6 | in progress; unreleased |
| Catalog validation hardening | v0.8.7 | ⏳ planned; not opened |
| Pricing Engine integration | M4 / v0.8.8 | ⏳ waits on v0.8.7 |

## Known issues (durable)

- Pricing is not yet computed in the offer pipeline — `pricing_status = "pending"`; there is no first-class `pricing_pending → priced` state yet (planned M4).
- `ck_catalog_pricing_profile_material_assumptions_quantity_source` is exactly 63 characters and has no PostgreSQL identifier headroom.
- API/OpenAPI `app_version` is not synchronized with repository releases.

## Release gate — last measured

Authoritative GitHub Actions run on `master`, commit
`5ce81669eb8354537c0a98b842cb4263dab3705e` (2026-10-02):

| Check | Result |
|---|---|
| PostgreSQL 16 `pytest tests/` | **1452 passed, 0 failed**, 1 warning; coverage 73.62% |
| `ruff check app/` | ✅ pass |
| `mypy app/` | ✅ pass |
| `bandit -r app/ -ll -ii` | ✅ pass |
| `pip-audit -r requirements.txt` | ✅ pass |
| Web typecheck / ESLint / dependency-cruiser | ✅ pass |
| Post-deploy verification | ✅ pass |
| API / auth / business-flow smoke | ✅ pass |
| `orchestration-release-gate` | ✅ pass |
| Repo Guard | ✅ pass |

No release while tests are red, `mypy` is red, a known fail-open exists, a
security gate is red, or the working tree/release commit is not reproducible.
See [development/RELEASE_PROCESS.md](development/RELEASE_PROCESS.md).
