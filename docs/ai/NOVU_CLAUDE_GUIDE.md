# NOVU Builder AI Development Guide

Mandatory shared references:

- [NOVU Constitution](../NOVU_CONSTITUTION.md)
- [NOVU AI Engineering Standard](NOVU_AI_ENGINEERING_STANDARD.md)
- [Project Invariants](PROJECT_INVARIANTS.md)

## 1. Project Mission

NOVU Builder is an AI-first construction platform designed for professional, production-grade workflows. The system uses AI to assist with analysis, measurements, documentation, and decision support, but the backend remains the source of truth for all durable business state.

Core mission principles:

- Build an AI-first construction platform that improves speed, consistency, and operational quality.
- Keep the backend as the authoritative source of truth.
- Keep pricing deterministic and server-side.
- Use a measurements-first workflow: AI may extract quantities, conditions, and confidence, but not prices.
- Maintain enterprise quality in architecture, security, auditability, and test coverage.
- Keep every change production ready, not merely locally convenient.

## 2. Architecture Principles

NOVU Builder follows Clean Architecture and clear ownership boundaries. Changes must preserve the existing flow:

- Route -> Service -> Repository -> ORM.
- Routes handle transport, authentication, authorization, request parsing, and response shaping.
- Services own business workflows and policy decisions.
- Repositories own persistence queries and database access.
- ORM models describe durable state and database relationships.
- AI providers are accessed through provider abstractions, not directly from routes or business logic.
- Worker architecture owns asynchronous, retryable, and long-running jobs.
- SSE and event-driven flows must remain replay-safe, ordered, deduplicated, and auditable.
- Business rules must not be duplicated across layers.
- Every domain concept must have a single source of truth.

## 3. Coding Rules

Claude must work from root cause first. Do not patch symptoms when the underlying failure can be identified.

Required coding behaviour:

- Identify the root cause before implementation.
- Make the smallest safe change that solves the root cause.
- Do not redesign unless redesign is required to remove a concrete risk.
- Do not introduce hidden side effects.
- Do not add temporary hacks.
- Do not leave TODO comments without a clear reason, owner, and safety note.
- Do not leave dead code.
- Do not duplicate logic.
- Preserve backward compatibility whenever possible.
- Prefer existing patterns, helpers, services, repositories, and domain boundaries.

## 4. AI Safety Rules

AI must never:

- Invent prices.
- Invent IDs.
- Invent database records.
- Bypass the pricing engine.
- Bypass validation.
- Silently ignore failures.
- Disable security checks.
- Invent `work_type_code`.
- Create a second source of truth.

AI-generated outputs must be validated before persistence. AI may assist with measurement extraction and reasoning, but deterministic backend systems own durable state, pricing, authorization, tenant isolation, and audit records.

## 5. Backend Rules

Always preserve:

- Deterministic behaviour.
- Idempotency.
- Crash safety.
- Auditability.
- Fail-fast behaviour.
- Fail-closed behaviour.
- Transactional consistency.

Critical backend flows must make failures explicit. Infrastructure failures, dependency failures, validation failures, and authorization failures must not be hidden behind silent fallbacks.

## 6. Testing Policy

Every change requires:

- Root cause identification.
- Regression tests for the original failure.
- Unit tests for isolated logic.
- Integration tests when multiple layers or persistence flows are affected.
- `mypy` for changed Python code.
- `pytest` for relevant test coverage.
- No broken existing tests.

Tests must prove the intended contract, not merely satisfy a fragile assertion. Avoid mock-only fixes when the production contract is wrong.

## 7. Git Rules

No commit before:

- Tests are green.
- `mypy` is green.
- `git diff` has been reviewed.
- `git status` is clean.

Commit messages must follow Conventional Commits. Use precise scopes when helpful, for example:

- `fix(offer): enforce measurements-only AI output`
- `test(outbox): emulate SQLite sequence for replay tests`
- `docs(ai): add assistant development standards`

Do not commit without explicit approval.

## 8. Release Policy

NOVU Builder follows Semantic Versioning:

- `patch`: backward-compatible bug fixes, test stabilisation, documentation corrections, and internal hardening.
- `minor`: backward-compatible functionality, new capabilities, or expanded supported workflows.
- `major`: breaking contract changes, migrations requiring coordinated rollout, or incompatible API changes.

Never create a release with known fail-open behaviour. Known security, validation, tenant isolation, pricing, or auditability gaps must be resolved or explicitly blocked before release.

## 9. Security Principles

Never:

- Catch `Exception` and ignore it.
- Hide infrastructure failures.
- Bypass tenant isolation.
- Bypass authorization.
- Bypass validation.

Always prefer fail-closed over fail-open. Security checks must be explicit, testable, and auditable. If the system cannot prove an operation is authorized and valid, it must reject the operation.

## 10. AI-specific Behaviour

Claude is expected to provide deep architectural analysis while preserving NOVU Builder's existing architecture.

Claude-specific rules:

- Prefer deep architectural analysis before proposing code changes.
- Explain reasoning clearly, especially when identifying root cause or risk.
- Propose refactoring only when there is a concrete justification.
- Preserve existing architecture unless a change is required for correctness, safety, or maintainability.
- Focus on correctness, consistency, and long-term production safety.
- Make tradeoffs explicit.
- Do not turn architectural analysis into broad rewrites.
- Keep implementation proposals grounded in current code and tests.

## 11. Forbidden Actions

Forbidden actions:

- No fake implementations.
- No mocked production logic.
- No silent fallback.
- No duplicated pricing.
- No duplicated validation.
- No duplicated repositories.
- No duplicated business logic.
- No bypassing service, repository, or ORM ownership.
- No manual price calculation outside the server-side pricing engine.
- No changing security-critical behaviour without tests.

## 12. Required Workflow

1. Understand the request, current code, and existing architecture.
2. Identify the root cause in concrete files and flows.
3. Plan the smallest safe change.
4. Implement only the necessary change.
5. Add or update tests that prove the fix.
6. Verify with relevant `pytest`, `mypy`, and targeted checks.
7. Report what changed, what was verified, and what residual risk remains.
8. Commit only after explicit approval.

## AI Contract

This document defines mandatory development behaviour for AI agents contributing to NOVU Builder. These rules take precedence over optimisation attempts that would compromise correctness, determinism, auditability or production safety.
