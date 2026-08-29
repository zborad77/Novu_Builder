# ADR-0004 — AI offer contract returns measurements only

**Status:** Accepted — implementation in `v0.8.4` (milestone M2)

## Context
Applies [ADR-0001](ADR-0001-ai-pricing.md) to the offer pipeline. The offer AI previously returned priced
line items parsed from free-form text — a second pricing source and a fragile, unvalidated contract.

## Decision
The offer AI returns a **measurements-only** contract: quantities, units, surface condition, confidence,
and clarification questions — never prices. Output is produced via **strict tool use** (guaranteed schema),
not prose parsing, and is untrusted until the validation layer accepts it (whitelisted work-type codes,
bounded values). Prices are computed server-side by the Pricing Engine (ADR-0001); until that bridge lands,
`pricing_status = "pending"`.
(Constitution Art. 2, 3 & 9; Invariants INV-002, INV-004, INV-015. See the first [AI Decision Log](../ai/AI_DECISION_LOG.md) entry.)

## Consequences
- **+** No AI-generated money values; guaranteed-valid JSON; validation is a hard security boundary.
- **−** The offer is unpriced until the Pricing Engine bridge lands (ROADMAP v0.8.7, milestone M4).

## Alternatives considered
- **Keep AI prices as "advisory"** — rejected: still a second pricing authority, violating ADR-0001.
