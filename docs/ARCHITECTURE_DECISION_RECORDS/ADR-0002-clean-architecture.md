# ADR-0002 — Route → Service → Repository → ORM layering

**Status:** Accepted

## Context
Business rules scattered across routes, workers, and clients drift and duplicate. A large multi-tenant
backend needs exactly one home per concern, with tenant isolation enforced at a single boundary.

## Decision
Enforce strict layering:
- **Route** — request validation, auth, response contract.
- **Service** — workflow orchestration, storage policy, fail-fast behaviour.
- **Repository** — tenant-safe DB access.
- **ORM** — persistence model.

Business logic lives in the service/domain layer only — never in routes, repositories, workers, clients,
or AI prompts.
(Constitution Art. 4; Invariant INV-011.)

## Consequences
- **+** One home per rule; testable boundaries; tenant isolation enforced at the repository.
- **−** Requires discipline; some indirection for trivial paths.

## Alternatives considered
- **Fat routes / active-record** — rejected: duplicated logic and tenant-isolation leaks.
