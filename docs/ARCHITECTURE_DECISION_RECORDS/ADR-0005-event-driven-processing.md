# ADR-0005 — Event-driven processing via the outbox pattern

**Status:** Accepted

## Context
State changes (status transitions, measurement confirmations, agent runs) must reach downstream consumers
(timeline projection, reconciler, live updates) reliably — without a dual-write race between the database
and a message broker, and without losing events on crash.

## Decision
Domain events are written to an **outbox** table in the **same transaction** as the state change, then
relayed by a consumer. Events carry a monotonic `seq`; delivery is at-least-once and all consumers are
idempotent. The case/offer timeline is a **projection over real outbox events**, not a stub.
(Constitution Art. 5; Invariants INV-008, INV-012.)

## Consequences
- **+** Atomic state+event write; truthful, auditable timeline; no lost events on crash.
- **−** Consumers must be idempotent; the `seq` column is DB-managed, which needs care under SQLite tests
  (see the backlog item on the session-scoped seq emulation).

## Alternatives considered
- **Publish directly to a broker after commit** — rejected: dual-write; events lost if publish fails
  after the commit succeeds.
