# NOVU Builder AI Development Guide

Mandatory shared references:

- [NOVU Constitution](../NOVU_CONSTITUTION.md)
- [NOVU AI Engineering Standard](NOVU_AI_ENGINEERING_STANDARD.md)
- [Project Invariants](PROJECT_INVARIANTS.md)

## 1. Project Mission

NOVU Builder is an AI-first construction platform designed for professional, production-grade workflows. The system uses AI to accelerate analysis, measurement extraction, documentation, and operational decisions, while the backend remains the source of truth for every durable business result.

Core mission principles:

- Build an AI-first construction platform for reliable construction workflows.
- Keep the backend as the authoritative source of truth.
- Keep pricing deterministic and server-side.
- Use a measurements-first workflow: AI may extract quantities, conditions, and confidence, but not prices.
- Maintain enterprise quality in correctness, security, testing, and observability.
- Keep the system production ready after every accepted change.

## 2. Architecture Principles

NOVU Builder follows Clean Architecture and explicit layer boundaries. Codex must preserve the established flow:

- Route -> Service -> Repository -> ORM.
- Routes own API transport concerns, dependency injection, authentication, authorization, and response models.
- Services own business workflows, domain rules, and orchestration.
- Repositories own persistence access and query structure.
- ORM models own durable database shape and relationships.
- AI Provider abstraction owns model-specific integration details.
- Worker architecture owns asynchronous jobs, leases, retries, fencing, and crash-safe processing.
- SSE and event-driven flows must remain replay-safe, deduplicated, and auditable.
- Do not duplicate business logic between layers.
- Keep a single source of truth for every domain rule.

## 3. Coding Rules

Codex must implement from root cause, not from surface symptoms.

Required coding behaviour:

- Identify root cause before editing.
- Make the smallest safe change with the highest corrective effect.
- Do not redesign unless it is required to remove a concrete risk.
- Do not introduce hidden side effects.
- Do not add temporary hacks.
- Do not leave TODO comments without context, owner, and reason.
- Do not leave dead code.
- Do not duplicate logic.
- Preserve backward compatibility whenever possible.
- Follow the repository's existing style, abstractions, and test patterns.

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

AI outputs must be treated as untrusted input. They require schema validation, business validation, normalization, and controlled persistence through backend-owned flows.

## 5. Backend Rules

Always preserve:

- Deterministic behaviour.
- Idempotency.
- Crash safety.
- Auditability.
- Fail-fast behaviour.
- Fail-closed behaviour.
- Transactional consistency.

Backend changes must be explicit about failure modes. Critical systems must not silently degrade in ways that hide incorrect state, bypass tenant boundaries, or weaken validation.

## 6. Testing Policy

Every change requires:

- Root cause identification.
- Regression tests for the original failure.
- Unit tests for isolated logic.
- Integration tests when persistence, workers, routes, or events are involved.
- `mypy` for changed Python code.
- `pytest` for relevant test coverage.
- No broken existing tests.

Tests must prove production behaviour. Do not add mocks that only make a test pass while leaving production logic incorrect.

## 7. Git Rules

No commit before:

- Tests are green.
- `mypy` is green.
- `git diff` has been reviewed.
- `git status` is clean.

Commit messages must follow Conventional Commits. Use precise scopes when helpful, for example:

- `fix(worker): preserve offer job fencing on validation failure`
- `test(outbox): emulate SQLite sequence for transition tests`
- `docs(ai): define Codex development rules`

Do not commit without explicit approval.

## 8. Release Policy

NOVU Builder follows Semantic Versioning:

- `patch`: backward-compatible bug fixes, test stabilisation, documentation corrections, and internal hardening.
- `minor`: backward-compatible functionality, new capabilities, or expanded supported workflows.
- `major`: breaking contract changes, migrations requiring coordinated rollout, or incompatible API changes.

Never create a release with known fail-open behaviour. A release with known pricing, validation, authorization, tenant isolation, or auditability gaps is not production ready.

## 9. Security Principles

Never:

- Catch `Exception` and ignore it.
- Hide infrastructure failures.
- Bypass tenant isolation.
- Bypass authorization.
- Bypass validation.

Always prefer fail-closed over fail-open. If a critical dependency, configuration, database operation, or validation step fails, the system must report the failure truthfully and stop the unsafe path.

## 10. AI-specific Behaviour

Codex is expected to make minimal, deterministic, production-quality code changes.

Codex-specific rules:

- Prefer minimal code changes.
- Implement deterministic behaviour.
- Produce production-quality code, not local-only workarounds.
- Execute the relevant tests whenever feasible.
- Fix root cause only.
- Never refactor unrelated code.
- Do not alter architecture unless the task or safety issue requires it.
- Keep edits scoped, reviewable, and reversible.
- Report tests run, failures found, and residual risk.

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
- No unrelated refactoring in a corrective patch.

## 12. Required Workflow

1. Understand the request, code path, and constraints.
2. Identify the root cause in concrete files and flows.
3. Plan the smallest safe change.
4. Implement only the necessary change.
5. Add or update regression, unit, or integration tests.
6. Verify with relevant `pytest`, `mypy`, and targeted checks.
7. Report changes, verification, and residual risk.
8. Commit only after explicit approval.

## AI Contract

This document defines mandatory development behaviour for AI agents contributing to NOVU Builder. These rules take precedence over optimisation attempts that would compromise correctness, determinism, auditability or production safety.
