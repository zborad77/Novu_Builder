# Current Milestone

> **Single source of truth** for "what is being worked on right now". One milestone at a time.
> Every AI agent and contributor MUST read this before starting work, and MUST NOT start work
> outside it. Update this file when a milestone opens or closes.

**Milestone:** M3 — Test Isolation & PostgreSQL Async Infrastructure
**Status:** IN PROGRESS
**Version target:** v0.8.5 — see [ROADMAP.md](ROADMAP.md)
**Opened:** 2026-09-04

## Goal

Establish a trustworthy PostgreSQL test baseline and make the authoritative
`orchestration-release-gate` fully green without weakening test isolation.

## In scope

- Make the pytest suite reliable against PostgreSQL.
- Remove asyncpg/event-loop coupling in the test infrastructure.
- Resolve already documented subset/order fragility where it belongs to
  shared test infrastructure.
- Confirm the complete required CI pipeline against PostgreSQL 16.

## Blocking issues

- [ ] asyncpg connections are pooled on the session-scoped loop and reused from
      per-test loops → `attached to a different loop` /
      `another operation is in progress`.

      Reproduced locally on PostgreSQL 17.9 using an isolated test schema.
      Even a single test can fail. Root cause is the module-level
      `_test_engine` combined with session-scoped `_setup_test_db` and
      function-scoped test loops.

- [ ] Evaluate `NullPool` for the test engine as the smallest isolation-preserving
      solution. Accept it as the permanent solution only if PostgreSQL tests show
      that it removes the asyncpg failures without introducing state leakage,
      unacceptable performance regression, or new failures.

- [ ] If `NullPool` is insufficient, redesign test engine/resource lifetime so
      async DB resources belong to the event-loop scope that uses them.

- [ ] Resolve documented subset/order fragility in shared test infrastructure.

- [ ] Full required CI green on PostgreSQL 16.

## Known follow-ups — not M3 blockers

- `ck_catalog_pricing_profile_material_assumptions_quantity_source` is exactly
  63 characters and has no PostgreSQL identifier headroom.
- `.coverage` is generated locally but is not currently ignored.
- API/OpenAPI `app_version` is not synchronized with repository releases.
- Remote release/tag history before v0.8.4 requires separate review.

## Forbidden until M3 closes

- New product features
- UI redesign
- Pricing Engine feature work
- Unrelated schema redesign
- Tagging v0.8.5 before the authoritative CI release gate is fully green

---

## Previous milestone — M2, closed 2026-08-29

**M2 — AI Offer Contract Review**, released as `v0.8.4`. All five blocking issues
cleared: fail-closed catalog whitelist enforced at both the runner and the validator,
exception logging restored, the red analysis-route test fixed, out-of-scope test
changes triaged as *keep*, and the local release gate green.

Released over a red CI gate — that deviation, and the four pre-existing failures
behind it, are recorded in [PROJECT_STATE.md](PROJECT_STATE.md). Clearing them is
what opened M3.
