# NOVU Builder — Technical Roadmap

> Engineering roadmap, **not** marketing. Each version lists concrete scope and its release gate.
> Tags must match releases (see [development/VERSIONING.md](development/VERSIONING.md)).
> Only **v0.8.3** is released; everything below is **planned** and may be reordered.
> Milestone (Mx) tags map to [PROJECT_STATE.md](PROJECT_STATE.md).

**Released:** `v0.8.3` — proposal archive, measurement lineage, offline viewer *(current)*

---

## Planned

### v0.8.4 — AI Offer Contract (measurements-only) · M2
- AI returns measurements / confidence / questions only; never prices (Constitution Art. 2 & 3)
- Strict tool use (guaranteed JSON), photos to the offer agent, model from config
- Fix fail-open whitelist (Art. 6 & 9) + add logging to broad `except` (Art. 10)
- **Gate:** offer + full regression green, `mypy` green, no fail-open

> **Checkpoint after v0.8.4 — v0.8 Architecture Review.** Before opening M3, confirm the architecture
> still matches the Product Book vision after the AI-contract and governance changes. Not a bug hunt —
> a directional confirmation and the baseline for M3 + Pricing Engine integration.
> Also planned here (post-M2, not before): draft `docs/REPOSITORY_CHARTER.md` — the repository "contract"
> (purpose, architecture ownership, how changes/reviews/architectural decisions/releases happen).

### v0.8.5 — Backend Stabilization · M3
- Close the `ANALYSIS_STALE` guard test gap; triage out-of-scope working-tree test changes
- Test-isolation hardening (session-scoped SQLite `outbox_events.seq` emulation is order-fragile)
- **Gate:** full regression green and non-flaky across runs

### v0.8.6 — Catalog Validation Hardening
- Effective work-type whitelist as a first-class, **fail-closed** input to the offer validator
- Surface work-type parameter schema to improve measurement quality

### v0.8.7 — Pricing Engine Integration · M4
- Bridge AI measurements → catalog Pricing Engine (`calculate_project_work_item`) via a valid `ProjectWorkItem`
- Introduce first-class `pricing_pending → priced` state
- **Invariant:** Pricing Engine remains the only pricing authority (Art. 3); no second pricing path

### v0.8.8 — Proposal Generator
- Priced offer → proposal draft → immutable archive, end to end

### v0.9.0 — Complete AI Offer Pipeline
- Lead → photos → measurements → pricing → proposal, fully wired, audited, tenant-safe

### v0.9.5 — Frontend Feature Complete
- Qt desktop + web admin surfaces covering the full pipeline

### v1.0.0 — Production Release
- Production hardening, observability/SLOs, security sign-off (Constitution Art. 11)

---

## Reconcile with VERSIONING.md

`development/VERSIONING.md` (authored in M1) lists *"v0.9.0 pricing engine integration milestone"*.
This roadmap schedules pricing earlier, at **v0.8.7**, with v0.9.0 = *complete* AI offer pipeline.
Align `VERSIONING.md` when the documentation branch is reopened — **do not edit it mid-close-out** (keep the doc task clean).
