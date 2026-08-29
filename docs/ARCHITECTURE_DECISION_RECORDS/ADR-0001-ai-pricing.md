# ADR-0001 — AI does not generate prices

**Status:** Accepted

## Context
Construction estimation is money-critical. If an AI model produces prices, rates, margins, or totals,
those values enter a commercial offer without deterministic control, and the model becomes a second
pricing authority alongside the catalog Pricing Engine. AI output is non-deterministic and untrusted
until validated.

## Decision
AI never generates prices, rates, totals, discounts, margins, or taxes. The **Pricing Engine is the only
source of pricing truth**. AI output is limited to measurements, confidence, extracted facts, and
clarification questions.
(Constitution Art. 2 & 3; Invariants INV-002, INV-003.)

## Consequences
- **+** Deterministic, auditable pricing with a single authority.
- **+** AI providers/models can be swapped or upgraded without touching pricing.
- **−** Requires a server-side bridge from measurements to the Pricing Engine (see ADR-0004, ROADMAP v0.8.7).

## Alternatives considered
- **AI emits prices, server "checks" them** — rejected: still a second pricing source; invites drift and
  disagreement with the catalog engine.
