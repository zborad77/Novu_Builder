# NOVU AI Engineering Standard

This standard applies to Claude, Codex, Gemini, and any future AI assistant contributing to NOVU Builder.

Related mandatory documents:

- [NOVU Constitution](../NOVU_CONSTITUTION.md)
- [Project Invariants](PROJECT_INVARIANTS.md)

## 1. Mission

AI assistants must help build NOVU Builder as a production-ready, AI-first construction platform while preserving backend authority, deterministic pricing, tenant isolation, auditability, and enterprise quality.

## 2. Mandatory Behaviour

- Root cause first.
- Smallest safe change.
- No unrelated refactor.
- Preserve existing architecture.
- Make failures explicit.
- Report tests run and residual risk.

## 3. Architecture Rules

- Preserve Route -> Service -> Repository -> ORM layering.
- Use AI Provider abstractions for AI integration.
- Keep worker logic retry-safe, idempotent, and crash-safe.
- Keep SSE and event-driven behaviour replay-safe and auditable.
- Do not duplicate business rules across layers.
- Do not create a duplicated source of truth.

## 4. AI Safety Rules

- No AI-generated pricing.
- No invented IDs.
- No invented database records.
- No invented `work_type_code`.
- No bypassing validation.
- No bypassing tenant isolation.
- Treat AI provider outputs as untrusted until validated.

## 5. Backend Rules

- Backend remains the source of truth.
- Pricing Engine remains the only pricing authority.
- Critical paths must fail fast and fail closed.
- Transactional consistency must be preserved.
- Infrastructure failures must not be hidden.
- Audit trails must remain truthful.

## 6. Testing Rules

- Tests must reproduce the original failure.
- Tests must prove the fix.
- Use unit tests for pure logic.
- Use integration tests for route, service, database, worker, and event boundaries.
- Run `mypy` for changed Python files.
- Run relevant `pytest`.
- Do not delete or weaken tests to make the suite green.

## 7. Git Rules

- No commit before tests are green.
- No commit before `mypy` is green.
- No commit before reviewing `git diff`.
- No commit before checking `git status`.
- Commit messages must follow Conventional Commits.
- Commit only after explicit approval.

## 8. Release Rules

- Follow Semantic Versioning.
- Never release known fail-open behaviour.
- Never release known security bypasses.
- Never release unaudited critical path changes.
- Tags must match release versions.

## 9. Forbidden Actions

- No fake implementation.
- No mocked production logic.
- No hidden fallback.
- No duplicated source of truth.
- No duplicated pricing.
- No duplicated validation.
- No duplicated repositories.
- No duplicated business logic.
- No bypassing validation.
- No bypassing tenant isolation.

## 10. Required Workflow

1. Understand the request and current architecture.
2. Identify root cause in concrete files and flows.
3. Plan the smallest safe change.
4. Implement only the necessary change.
5. Add or update tests.
6. Verify with `pytest`, `mypy`, diff review, and status check.
7. Report changes, verification, and residual risk.
8. Commit only after approval.

## 11. Output Format

For implementation or review tasks, AI agents should report:

1. Root cause.
2. Risk.
3. Changes.
4. Tests.
5. Verification.
6. Residual risk.
7. Verdict.

## 12. AI Contract

AI assistants must follow this standard, the NOVU Constitution, and Project Invariants. These rules take precedence over optimization attempts that would compromise correctness, determinism, auditability, tenant isolation, pricing integrity, or production safety.
