# Change Control

> What each class of change requires before it may merge or release. Derived from the
> [Constitution](NOVU_CONSTITUTION.md), [Project Invariants](ai/PROJECT_INVARIANTS.md), and the
> [development standards](development/). This file is a **checklist**, not a second rulebook —
> the linked documents remain authoritative. When a change spans classes, the strictest applies.

## Architecture change
- [ ] Design review
- [ ] Explicit approval **before** implementing (Constitution Art. 12 — AI waits for approval)
- [ ] Tests
- [ ] Decision Log entry ([ai/AI_DECISION_LOG.md](ai/AI_DECISION_LOG.md))

## Business logic change
- [ ] Regression tests that prove the change (and reproduce any fixed bug)
- [ ] No duplicated logic / no second source of truth (Art. 4)
- [ ] No pricing outside the Pricing Engine (Art. 3)
- [ ] Release gate green

## Documentation change
- [ ] Consistency check — links resolve, no contradiction with Constitution/Invariants
- [ ] No code, test, or config changes mixed in

## Security / tenant-isolation / AI-boundary change
- [ ] Constitution review
- [ ] Invariants review ([ai/PROJECT_INVARIANTS.md](ai/PROJECT_INVARIANTS.md))
- [ ] Fail-closed verified (Art. 6) — no silent fallback (Art. 9)
- [ ] Tests covering the boundary

## Release
- [ ] Green tests
- [ ] Green `mypy`
- [ ] Clean git tree
- [ ] Release notes (CHANGELOG)
- [ ] Version bump + matching tag ([development/VERSIONING.md](development/VERSIONING.md), [development/RELEASE_PROCESS.md](development/RELEASE_PROCESS.md))
