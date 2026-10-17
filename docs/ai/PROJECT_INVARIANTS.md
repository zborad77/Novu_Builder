# Project Invariants

These invariants define mandatory NOVU Builder behaviour. They are not preferences.

1. INV-001 Backend is the source of truth.
2. INV-002 AI never generates prices.
3. INV-003 Pricing engine is the only pricing authority.
4. INV-004 Offer pipeline must not bypass validation.
5. INV-005 Tenant isolation must not be bypassed.
6. INV-006 Worker jobs must be idempotent.
7. INV-007 Retries must be safe.
8. INV-008 Audit trail must remain truthful.
9. INV-009 Critical infrastructure failures must not be hidden.
10. INV-010 No fail-open behaviour in security or AI boundaries.
11. INV-011 No duplicated business logic.
12. INV-012 No silent data loss.
13. INV-013 Every release must be reproducible.
14. INV-014 Tests must prove bug fixes.
15. INV-015 AI provider outputs are untrusted until validated.
