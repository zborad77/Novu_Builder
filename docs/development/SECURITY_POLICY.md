# Security Policy

NOVU Builder security boundaries must be explicit, testable, and fail-closed.

## Tenant Isolation

Every tenant-scoped read and write must enforce organization boundaries. Cross-tenant access must be rejected and auditable.

## Authentication and Authorization

Authentication proves identity. Authorization proves permission. Both must be enforced before protected operations and must not be bypassed by AI, workers, tests, or fallback paths.

## Fail-closed Security

If a security precondition cannot be verified, reject the operation. Do not continue with weaker assumptions.

## Secrets

Do not commit secrets, tokens, credentials, private keys, or environment-specific secret values. Runtime secrets must remain in approved secret/configuration systems.

## Fallbacks

No silent fallback in security-sensitive paths. Fallback behaviour must be explicit, logged, tested, and safe.

## Audit Logging

Security-relevant decisions must leave truthful audit evidence. Do not hide infrastructure failures, authorization failures, validation failures, or tenant isolation failures.

## Immutable History

Where immutable history is required, preserve append-only records and do not rewrite audit facts. Corrections must be explicit.

## AI Output

AI output is untrusted input. It must be validated before use and must never bypass tenant isolation, authorization, validation, or pricing boundaries.
