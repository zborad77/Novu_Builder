# AI Decision Log

This log records architecture and safety decisions involving AI-assisted development, AI provider behaviour, and AI-adjacent backend contracts.

Use this template for new entries:

```markdown
## YYYY-MM-DD - Decision title

Decision:
...

Reason:
...

Alternatives considered:
...

Impact:
...

Approved by:
...
```

## 2026-06-28 - AI offer pipeline returns measurements only

Decision:
AI offer pipeline returns measurements only; prices are computed server-side.

Reason:
Pricing engine must remain the single source of truth. AI outputs are untrusted and must not determine money values.

Alternatives considered:
Allowing AI to return estimated prices was rejected because it would create a second pricing authority and weaken auditability.

Impact:
Offer AI providers may produce measurements, confidence and questions only. Pricing remains pending until server-side pricing is applied.

Approved by:
NOVU Builder owner
