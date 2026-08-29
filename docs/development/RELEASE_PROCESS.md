# Release Process

NOVU Builder releases must be reproducible, reviewed, and safe.

## Release Blockers

A release must not be created if:

- Tests are not green.
- `mypy` is not green.
- Known fail-open behaviour exists.
- A security bypass exists.
- An unaudited change exists in a critical flow.
- `git status` is not clean.

## Required Procedure

1. Review diff.
2. Run tests.
3. Run `mypy`.
4. Verify version bump.
5. Commit.
6. Tag.
7. Push.
8. Verify clean tree.

## Critical Flow Review

Critical flows include authentication, authorization, tenant isolation, pricing, AI output validation, worker execution, SSE/event replay, migrations, and audit logging. Any change in these areas requires explicit review and relevant tests.
