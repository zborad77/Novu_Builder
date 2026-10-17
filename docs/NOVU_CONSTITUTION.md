# NOVU Constitution

This constitution defines the non-negotiable engineering rules for NOVU Builder. It applies to human contributors, Claude, Codex, Gemini, and any future AI-assisted development workflow.

## Article 1. Backend Source of Truth

The backend is the source of truth for durable state, business decisions, tenant ownership, authorization, validation, pricing status, audit trails, and persisted records.

## Article 2. AI Does Not Price

AI never generates prices, rates, totals, discounts, margins, taxes, or money values. AI output may support measurements, confidence, extracted facts, and clarification questions only.

## Article 3. Pricing Authority

The Pricing Engine is the only source of pricing truth. No route, worker, AI provider, test helper, client, or service may create a second pricing authority.

## Article 4. No Duplicated Business Logic

Business logic must not be duplicated across routes, services, repositories, workers, clients, or AI prompts. Shared rules must live in the appropriate backend layer.

## Article 5. Determinism and Auditability

Every change must be deterministic, idempotent, crash-safe, and auditable. Critical paths must leave truthful evidence of what happened and why.

## Article 6. Fail Closed

Fail-closed is preferred over fail-open. If a critical validation, authorization, tenant isolation, infrastructure, or pricing precondition cannot be proven, the system must reject or stop the unsafe path.

## Article 7. Tenant Isolation

Tenant isolation must never be bypassed. Every tenant-scoped read and write must preserve organization boundaries.

## Article 8. Worker Safety

Worker logic must be safe under retries, leases, crashes, duplicate delivery, and partial failure. Job processing must preserve idempotency and fencing guarantees.

## Article 9. No Silent Fallbacks

Critical paths must not silently fall back to weaker behaviour. Fallbacks must be explicit, safe, logged, tested, and must not hide data loss, validation failure, pricing failure, or authorization failure.

## Article 10. No Exception Swallowing

Production code must not use `except Exception: pass`. Broad exception handling is only acceptable when the failure is logged, scoped, tested, and intentionally non-critical.

## Article 11. Release Gate

Every change must pass relevant tests, `mypy`, and review before release. Known fail-open behaviour blocks release.

## Article 12. AI Agent Obligation

AI agents must obey this constitution. Optimization, speed, convenience, or local test passing must never override correctness, determinism, auditability, tenant isolation, or production safety.

## Non-Negotiable Invariants

- Backend is the source of truth.
- AI never generates prices.
- Pricing Engine is the only source of pricing truth.
- Business logic must not be duplicated.
- Every change must be deterministic, idempotent, crash-safe, and auditable.
- Fail-closed is preferred over fail-open.
- Tenant isolation must never be bypassed.
- Worker logic must be safe under retries.
- No silent fallback in critical paths.
- No `except Exception: pass` in production code.
- Every change must pass tests, `mypy`, and review before release.
- AI agents must obey this constitution.
