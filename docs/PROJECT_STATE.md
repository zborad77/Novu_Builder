# NOVU Builder — Project State

> Living status snapshot **and** active-work governance. **Not** architecture
> (see [NOVU_ENGINEERING_HANDBOOK.md](NOVU_ENGINEERING_HANDBOOK.md)) and **not** rules
> (see [NOVU_CONSTITUTION.md](NOVU_CONSTITUTION.md)). This file answers two questions:
> *where are we right now?* and *what is allowed right now?* Update on every merge and milestone.

**Last updated:** 2026-09-04
**Current version:** v0.8.4 — AI offer contract (measurements-only), fail-closed AI boundary
**Current branch:** master — in sync with `origin/master` (`f556816`); tag `v0.8.4` pushed.

> ⚠️ **v0.8.4 was released with the authoritative CI gate red**, and the push bypassed the
> required status check. Per [development/RELEASE_PROCESS.md](development/RELEASE_PROCESS.md)
> a release should not be tagged over a red gate. None of the failures came from M2 — they
> were older problems that had been hiding behind one another, each only visible once the one
> before it was fixed. Clearing them is what opened M3.
>
> | CI job | Original failure | Status |
> |---|---|---|
> | `Repo Guard` | `.env.production.example` matched the forbidden `.env` pattern | ✅ fixed (`f00edbb`) |
> | `lint` | `mypy no-redef` on the `slowapi` import fallback; then bandit and pip-audit, which had never run | ✅ fixed (`7a94cb6`, `69597da`, `d3f30cd`, `a59ad26`) |
> | `web-lint` | 2 TS errors; then 17 ESLint errors, which had never run | ✅ fixed (`99235ad`, `5979d47`) |
> | `test` | `ModuleNotFoundError: pytest_asyncio`; then a 66-char identifier rejected by PostgreSQL; now asyncpg/event-loop coupling | ⏳ **M3** (`f5175e4`, `f556816` landed) |
>
> Two lessons worth keeping. A locally green `mypy` is **not** equivalent to CI — the local venv
> has packages CI lacks. And a sequential CI job hides everything after its first failing step,
> so until one job runs end to end, the state of that gate is simply unknown.

---

## Current Development Focus

The **active milestone, its blocking issues, and what is forbidden until it closes** live in a
single authoritative file: **[CURRENT_MILESTONE.md](CURRENT_MILESTONE.md)** (do not duplicate them here).
Change-class requirements: **[CHANGE_CONTROL.md](CHANGE_CONTROL.md)**. Version plan: **[ROADMAP.md](ROADMAP.md)**.

**Current milestone:** M3 — Test Isolation & PostgreSQL Async Infrastructure → target `v0.8.5`

---

## Completed

- ✓ **M1 — Documentation & governance framework** — Constitution, Handbook, AI Engineering Standard, AI guides, Project Invariants, Decision Log, Prompt Library, development standards, this file, ROADMAP
- ✓ **M2 — AI measurements-only offer contract** — AI returns measurements / confidence / questions only, never prices (Art. 2 & 3). Fail-closed catalog whitelist enforced at both the runner and the validator. Closed 2026-08-29.
- ✓ Multi-tenant SaaS core, offer pipeline resilience (lease fencing, outbox, AI budget), immutable proposal archive (v0.8.3)

Released as **v0.8.4** on 2026-08-29 — see [../CHANGELOG.md](../CHANGELOG.md).

## Work streams

| Stream | Milestone | Status |
|---|---|---|
| Documentation framework | M1 | ✅ files done · ✅ under version control · ⏳ Codex close-out report |
| AI Offer Contract (measurements-only) | M2 | ✅ done — released as v0.8.4 |
| CI / release-gate stabilization | M2→M3 | ✅ `lint`, `web-lint`, `Repo Guard` green; ⏳ `test` remains |
| Test isolation & PostgreSQL async infrastructure | M3 | 🔄 **in progress** — root cause reproduced locally |
| Pricing Engine integration | M4 | ⏳ M2 dependency cleared; waits on M3 |

## Known issues (durable)

- Pricing is not yet computed in the offer pipeline — `pricing_status = "pending"`; there is no first-class `pricing_pending → priced` state yet (planned M4)

## Release gate — last measured

Measured on `master` at M2 close (2026-08-29), backend `python-backend/`:

| Check | Result |
|---|---|
| `pytest tests/` | 1429 passed, 3 skipped, **0 failed** |
| `mypy app/` | **0 errors** / 146 source files |
| `ruff check app/` | **clean** |

No release while tests are red, `mypy` is red, a known fail-open exists, or the working tree is dirty. See [development/RELEASE_PROCESS.md](development/RELEASE_PROCESS.md).
