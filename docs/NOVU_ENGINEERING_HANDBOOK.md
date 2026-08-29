# NOVU Engineering Handbook

This handbook is the entry point for NOVU Builder engineering standards. It defines how the project should be developed, reviewed, tested, released, and maintained across human contributors and AI assistants.

## Project Purpose

NOVU Builder is an AI-first construction platform. AI assists with measurement extraction, analysis, documentation, review, and operational decision support. The backend remains the source of truth for durable business state, pricing, validation, tenant boundaries, and audit records.

## Engineering Philosophy

NOVU Builder prioritizes correctness, determinism, auditability, and production safety over speed or convenience. Every change should solve a real root cause with the smallest safe modification.

## Architecture Principles

- Preserve Clean Architecture boundaries.
- Use Route -> Service -> Repository -> ORM layering.
- Keep AI provider integration behind provider abstractions.
- Keep worker jobs idempotent, fenced, retry-safe, and crash-safe.
- Keep SSE and event-driven flows replay-safe and auditable.
- Do not duplicate business logic.
- Keep a single source of truth for domain rules.

## AI Development Rules

AI agents must follow the shared AI engineering standard, the project constitution, and the project invariants. AI outputs are untrusted until validated. AI may never create prices or durable state outside backend-controlled flows.

## Backend Source-of-Truth Principle

The backend owns business truth. Clients, prompts, AI providers, tests, scripts, and local workflows may not become alternate sources of truth for pricing, tenant ownership, validation, authorization, or persisted state.

## Testing and Release Gates

Before release:

- Review the diff.
- Run relevant `pytest`.
- Run `mypy` for changed Python files.
- Verify no known fail-open behaviour remains.
- Verify no security bypass exists.
- Verify critical path changes are audited.
- Verify the working tree is clean after commit and tag.

## Git and Versioning Rules

Use small logical commits. Do not mix unrelated concerns. Commit messages must follow Conventional Commits. Releases follow Semantic Versioning, with `v0.x.y` used during the pilot phase.

## Security Principles

Security boundaries must fail closed. Tenant isolation, authentication, authorization, validation, audit logging, and AI output validation must never be bypassed. Critical infrastructure failures must be visible and truthful.

## Documentation Map

Core project standards:

- [NOVU Constitution](NOVU_CONSTITUTION.md)
- [NOVU Engineering Handbook](NOVU_ENGINEERING_HANDBOOK.md)

AI standards:

- [NOVU AI Engineering Standard](ai/NOVU_AI_ENGINEERING_STANDARD.md)
- [NOVU Claude Guide](ai/NOVU_CLAUDE_GUIDE.md)
- [NOVU Codex Guide](ai/NOVU_CODEX_GUIDE.md)
- [NOVU Gemini Guide](ai/NOVU_GEMINI_GUIDE.md)
- [Project Invariants](ai/PROJECT_INVARIANTS.md)
- [AI Decision Log](ai/AI_DECISION_LOG.md)
- [Prompt Library](ai/PROMPT_LIBRARY.md)

Development standards:

- [Release Process](development/RELEASE_PROCESS.md)
- [Versioning](development/VERSIONING.md)
- [Git Workflow](development/GIT_WORKFLOW.md)
- [Testing Policy](development/TESTING_POLICY.md)
- [Coding Standard](development/CODING_STANDARD.md)
- [Security Policy](development/SECURITY_POLICY.md)
