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
parameter_normalization_schema: exact-version-ref
resource_revision_preconditions: []
supported_environments: []
data_egress_contract: privacy-policy-ref
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

## Exact-effect enforcement

Policy Engine is the sole permission authority; Gateway is the trusted enforcement/execution boundary, not another policy authorizer. Tool existence and `allowed_tools` are necessary declarations, not permission to perform an action on an arbitrary resource.

Before dispatch Gateway MUST verify the action-bound authorization defined by the Policy Contract: actor/version, verified tenant/platform scope, execution/workflow, resource/revision, verb, normalized parameters/hash, purpose, environment, risk/data classification, exact candidate/context/decision revisions, required human approvals, validity and current execution fence. It resolves defaults using the bound tool normalization schema before comparison. A materially different or stale binding, missing input or unavailable authority fails closed.

Controller admission supplies an attempt credit and cost reservation from the shared envelope. Any terminal execution state, pause/cancellation/abort/stop, expired deadline, stale lease/revision or exhausted budget denies **new** effect dispatch. Gateway checks validity and revision preconditions at effect admission, not only when the request was proposed; compare-and-set/resource preconditions or an equivalent adapter protocol close the check/use race. A tool unable to enforce required preconditions is ineligible for that effect/risk scope.

Writes, destructive and privileged effects require a stable scoped `effect_idempotency_key` and durable intent/outcome record. Retries/delivery duplicates must not create a second effect. Unknown external completion is reconciled rather than blindly resent; an adapter without safe idempotency/reconciliation cannot be automatically retried. Read tools may declare weaker idempotency only where Policy permits it. Consumer replay does not execute tools.

Already-dispatched non-cancellable effects are recorded/reconciled even after a stop, including costs, without reopening the run. Compensation is a separate authorized, bounded operation; irreversible effects cannot be promised away by a rollback field.

## Confused deputy, egress and untrusted data

Resource IDs and tenant claims supplied by a model are not trusted scope. Gateway resolves resources within the verified execution scope and checks the action's purpose/permissions. Credentials are held by the trusted adapter and are not returned to agents, prompts or event payloads.

External tool inputs/outputs follow hard privacy constraints, including recipient locality/retention/data-use restrictions and raw-output retention. Presigned URLs bind an approved object/version, recipient/purpose, least-privilege access and expiry no broader than authorized validity. URLs/credentials are not durable evidence identity; record object/integrity references and avoid logging access secrets.

Evidence, retrieved documents, logs and tool/provider outputs are untrusted data. Embedded instructions cannot change policy, tools, scope, approvals or budget. Separate trusted instructions from data, validate structured outputs and normalize parameters before authorization; schema validity alone does not grant authority. Existing direct DB/session calls may remain trusted domain implementation behind compatibility adapters, but agents must not receive those sessions or bypass this boundary.

## Safety boundary

Arbitrary shell generation/execution in production is not a tool contract. Operational automation may invoke only approved, versioned runbooks with explicit parameters and permissions. Destructive/privileged actions require stricter policy and normally human approval.

## Current-state note

Existing storage and catalog abstractions are useful seeds, but direct repository/session usage throughout the codebase is not yet a generalized Tool Gateway.
