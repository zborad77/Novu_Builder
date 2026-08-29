# Architecture Decision Records (ADR)

Durable records of significant **architectural** decisions for NOVU Builder, in the format popularised
by Michael Nygard. ADRs are immutable once **Accepted** — a decision is changed by adding a *new* ADR
that supersedes the old one, never by editing history.

**ADR vs Decision Log:** the [AI Decision Log](../ai/AI_DECISION_LOG.md) is a lightweight running log
(often AI-workflow decisions); ADRs are the fixed-structure, long-lived record of architectural choices.

## Format
`Status` · `Context` · `Decision` · `Consequences` · `Alternatives considered`.
Status ∈ `Proposed` | `Accepted` | `Superseded by ADR-XXXX` | `Deprecated`.

## Index
- [ADR-0001](ADR-0001-ai-pricing.md) — AI does not generate prices
- [ADR-0002](ADR-0002-clean-architecture.md) — Route → Service → Repository → ORM layering
- [ADR-0003](ADR-0003-worker-design.md) — Worker design: isolated lanes, fencing, idempotency
- [ADR-0004](ADR-0004-measurements-only.md) — AI offer contract returns measurements only
- [ADR-0005](ADR-0005-event-driven-processing.md) — Event-driven processing via the outbox pattern
