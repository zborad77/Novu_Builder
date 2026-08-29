# NOVU Builder AI Development Guide

Mandatory shared references:

- [NOVU Constitution](../NOVU_CONSTITUTION.md)
- [NOVU AI Engineering Standard](NOVU_AI_ENGINEERING_STANDARD.md)
- [Project Invariants](PROJECT_INVARIANTS.md)

## 1. Project Mission

NOVU Builder is an AI-first construction platform built for professional construction workflows, enterprise reliability, and production safety. AI assists with analysis, measurements, documentation, review, and risk detection, while the backend remains the source of truth.

Core mission principles:

- Build an AI-first construction platform with reliable operational workflows.
- Keep the backend as the authoritative source of truth.
- Keep pricing deterministic and server-side.
- Use a measurements-first workflow: AI may extract quantities, conditions, and confidence, but not prices.
- Maintain enterprise quality in architecture, security, testing, documentation, and release discipline.
- Keep every accepted change production ready.

## 2. Architecture Principles

NOVU Builder follows Clean Architecture and explicit layer ownership. Gemini must validate that changes preserve the established flow:

- Route -> Service -> Repository -> ORM.
- Routes handle API transport, authentication, authorization, dependency injection, and response shaping.
- Services handle business workflow and policy.
- Repositories handle persistence queries.
- ORM models represent durable database state.
- AI Provider abstraction separates model-specific integration from business logic.
- Worker architecture handles asynchronous, retryable, fenced, and crash-safe jobs.
- SSE and event-driven flows must remain ordered, replay-safe, deduplicated, and auditable.
- Business logic must not be duplicated across layers.
- Every durable rule must have a single source of truth.

## 3. Coding Rules

Gemini must review from root cause and system impact, not from isolated code appearance.

Required coding behaviour:

- Identify root cause before recommending implementation.
- Prefer the smallest safe change that resolves the actual problem.
- Do not recommend redesign unless it is required by a concrete architectural, safety, or correctness issue.
- Do not accept hidden side effects.
- Do not accept temporary hacks.
- Do not accept TODO comments without reason, owner, and safety context.
- Do not accept dead code.
- Do not accept duplicated logic.
- Preserve backward compatibility whenever possible.
- Validate consistency with existing architecture and contracts.

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

AI outputs must be reviewed as untrusted inputs. Any flow that persists AI output must prove validation, normalization, auditability, and backend ownership.

## 5. Backend Rules

Always preserve:

- Deterministic behaviour.
- Idempotency.
- Crash safety.
- Auditability.
- Fail-fast behaviour.
- Fail-closed behaviour.
- Transactional consistency.

Gemini must flag any change that weakens these properties, especially in workers, pricing, tenant isolation, authentication, authorization, event replay, or persistence.

## 6. Testing Policy

Every change requires:

- Root cause identification.
- Regression tests for the original failure.
- Unit tests for isolated logic.
- Integration tests when persistence, routes, workers, SSE, or external providers are affected.
- `mypy` for changed Python code.
- `pytest` for relevant test coverage.
- No broken existing tests.

Testing review must verify that tests prove the real production contract and not merely a mocked implementation detail.

## 7. Git Rules

No commit before:

- Tests are green.
- `mypy` is green.
- `git diff` has been reviewed.
- `git status` is clean.

Commit messages must follow Conventional Commits. Use precise scopes when helpful, for example:

- `fix(auth): reject cross-tenant measurement updates`
- `test(sse): verify durable outbox sequence replay`
- `docs(ai): define Gemini review standards`

Do not commit without explicit approval.

## 8. Release Policy

NOVU Builder follows Semantic Versioning:

- `patch`: backward-compatible bug fixes, test stabilisation, documentation corrections, and internal hardening.
- `minor`: backward-compatible functionality, new capabilities, or expanded supported workflows.
- `major`: breaking contract changes, migrations requiring coordinated rollout, or incompatible API changes.

Never create a release with known fail-open behaviour. Release readiness requires a truthful view of known risks, test status, migration status, operational impact, and security posture.

## 9. Security Principles

Never:

- Catch `Exception` and ignore it.
- Hide infrastructure failures.
- Bypass tenant isolation.
- Bypass authorization.
- Bypass validation.

Always prefer fail-closed over fail-open. Gemini must flag any implementation that silently continues after a critical failure or weakens a security boundary.

## 10. AI-specific Behaviour

Gemini is expected to focus on architecture review, audit quality, consistency, and risk analysis.

Gemini-specific rules:

- Perform architecture review against NOVU Builder's established boundaries.
- Perform code audit for correctness, safety, and hidden regressions.
- Review documentation for accuracy, completeness, and consistency.
- Validate design choices against project constraints.
- Identify risk, blast radius, and missing tests.
- Check consistency between implementation, tests, docs, and release notes.
- Prefer clear findings over broad implementation proposals.
- Avoid recommending unrelated refactors.

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
- No approval of known fail-open behaviour.

## 12. Required Workflow

1. Understand the request, system context, and architectural boundary.
2. Identify the root cause or review target in concrete files and flows.
3. Plan the smallest safe recommendation or change.
4. Implement only when explicitly asked, and keep changes scoped.
5. Require tests that prove the intended behaviour.
6. Verify with relevant `pytest`, `mypy`, and review checks.
7. Report findings, risk, verification, and residual uncertainty.
8. Commit only after explicit approval.

## AI Contract

This document defines mandatory development behaviour for AI agents contributing to NOVU Builder. These rules take precedence over optimisation attempts that would compromise correctness, determinism, auditability or production safety.
