# NOVU Builder — Project State

> Living status snapshot **and** active-work governance. **Not** architecture
> (see [NOVU_ENGINEERING_HANDBOOK.md](NOVU_ENGINEERING_HANDBOOK.md)) and **not** rules
> (see [NOVU_CONSTITUTION.md](NOVU_CONSTITUTION.md)). This file answers two questions:
> *where are we right now?* and *what is allowed right now?* Update on every merge and milestone.

**Last updated:** 2026-08-29
**Current version:** v0.8.3 — the `v0.8.4` work is committed but **not released** (CHANGELOG, version bump and tag still open)
**Current branch:** master — **5 commits ahead of `origin/master`, nothing pushed.** `origin/master` is still at `d53efdc`, so it does not yet have the v0.8.3 release either.

---

## Current Development Focus

The **active milestone, its blocking issues, and what is forbidden until it closes** live in a
single authoritative file: **[CURRENT_MILESTONE.md](CURRENT_MILESTONE.md)** (do not duplicate them here).
Change-class requirements: **[CHANGE_CONTROL.md](CHANGE_CONTROL.md)**. Version plan: **[ROADMAP.md](ROADMAP.md)**.

**Current milestone:** none open — M2 closed 2026-08-29; M3 not yet opened

---

## Completed

- ✓ **M1 — Documentation & governance framework** — Constitution, Handbook, AI Engineering Standard, AI guides, Project Invariants, Decision Log, Prompt Library, development standards, this file, ROADMAP
- ✓ **M2 — AI measurements-only offer contract** — AI returns measurements / confidence / questions only, never prices (Art. 2 & 3). Fail-closed catalog whitelist enforced at both the runner and the validator. Closed 2026-08-29.
- ✓ Multi-tenant SaaS core, offer pipeline resilience (lease fencing, outbox, AI budget), immutable proposal archive (v0.8.3)

## Work streams

| Stream | Milestone | Status |
|---|---|---|
| Documentation framework | M1 | ✅ files done · ✅ under version control · ⏳ Codex close-out report |
| AI Offer Contract (measurements-only) | M2 | ✅ done — reviewed, blockers cleared, gate green, committed locally |
| Backend stabilization | M3 | ⏳ planned, not opened |
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
