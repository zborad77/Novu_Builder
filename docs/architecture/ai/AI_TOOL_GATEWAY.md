# AI Tool Gateway Contract

## Principle

Agents do not receive unrestricted direct access to databases, storage, shell, deployment systems, customer data or external APIs. They request approved tool capabilities through an audited gateway.

## Tool declaration

```yaml
tool_id: string
tool_version: string
purpose: string
action_class: read|write|destructive|privileged
input_schema: schema-ref
output_schema: schema-ref
required_permissions: []
security_classification: string
idempotency: none|supported|required
audit_required: true
```

## Initial tool families

- database read/query surfaces;
- approved catalog access;
- object storage;
- deterministic calculator;
- search/retrieval;
- external API adapters;
- future CAD/BIM;
- deployment/operations;
- approved recovery runbooks.

## Enforcement

Gateway checks:

- agent identity/version;
- declared `allowed_tools`;
- tenant/resource scope;
- action class;
- workflow/policy authorization;
- data classification/redaction;
- idempotency requirement;
- rate/cost constraints.

Every call records request metadata, authorization decision, result status, latency and correlation/causation IDs.

## Safety boundary

Arbitrary shell generation/execution in production is not a tool contract. Operational automation may invoke only approved, versioned runbooks with explicit parameters and permissions. Destructive/privileged actions require stricter policy and normally human approval.

## Current-state note

Existing storage and catalog abstractions are useful seeds, but direct repository/session usage throughout the codebase is not yet a generalized Tool Gateway.
