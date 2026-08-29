# Testing Policy

Tests protect NOVU Builder's production contracts.

## Required Test Behaviour

- A test must reproduce the original failure.
- A test must prove the fix.
- Use unit tests for pure logic.
- Use integration tests for route, service, database, worker, and event boundaries.
- Add regression tests for every bug fix.
- Run `mypy` for changed Python files.
- Run relevant `pytest`.
- Do not delete tests to make the suite green.

## Test Quality

Tests must prove real behaviour, not merely mocks. Mocking is acceptable for boundaries, but not as a substitute for fixing production logic.

## Critical Coverage Areas

- Tenant isolation.
- Authorization.
- Pricing engine boundaries.
- AI output validation.
- Worker idempotency and retries.
- SSE replay and deduplication.
- Database transaction consistency.
