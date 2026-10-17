# AI Event Contract

## Purpose

Define a universal event envelope for immutable AI/business decision history across all intelligence domains. This is conceptually distinct from metrics/logs/traces and from a transport outbox.

## Identity and scope vocabulary

`ScopeRef` is a verified `{kind: TENANT|PLATFORM, scope_id, security_classification}`. TENANT identifies one tenant. PLATFORM is an explicitly authorized platform scope, not a wildcard tenant. References, reads, replay and writes must retain that scope; cross-scope access requires a separate explicit Policy authorization.

| Identity | Meaning |
|---|---|
| `execution_id` | Root logical execution and global budget in the Workflow Contract |
| `workflow_run_id` | One version-bound workflow instance, including nested instances |
| `node_run_id` | One admitted node activation |
| `agent_run_id` | An agent invocation associated with a node activation; absent for non-agent nodes |
| `logical_operation_id` | Stable operation identity across retries/redeliveries |
| `attempt_id` | One admitted execution attempt; never aliases the workflow or agent run |
| `provider_call_id` / `model_call_id` | One physical inference call and its model invocation, including fallback/retry calls |
| `tool_call_id` | One admitted tool invocation |
| `policy_decision_id` | A deterministic policy outcome/authorization record |
| `human_action_id` | An attributed, revision-bound human intervention |
| `event_id` | One immutable semantic event |
| `transport_event_id` | Outbox/delivery identity that carries a semantic `event_id`; publication state is transport-only |

`ArtifactRef` carries identity, exact revision/version, schema version and immutable object/integrity reference. IDs alone or a mutable "latest" URL are not version-bound references. Decision artifacts are defined in the Workflow Contract; assertion/evidence references in the Evidence Model.

## Envelope

```yaml
event_id: uuid
event_type: string
schema_version: semver
occurred_at: timestamp
recorded_at: timestamp
scope: ScopeRef
aggregate:
  type: string
  id: string
  revision: integer
producer_id: trusted-producer-ref
producer_idempotency_key: string

case_id: string|null
incident_id: string|null
execution_id: string|null
workflow_run_id: string|null
workflow_ref: exact-version-ref|null
node_run_id: string|null
agent_run_id: string|null
logical_operation_id: string|null
attempt_id: string|null
provider_call_id: string|null
model_call_id: string|null
tool_call_id: string|null
parent_execution_id: string|null
parent_workflow_run_id: string|null
parent_node_run_id: string|null
parent_agent_run_id: string|null
parent_attempt_id: string|null
fencing_epoch: integer|null
correlation_id: string
causation_id: string|null
parent_event_id: string|null

source:
  type: agent|human|policy|tool|system
  id: string
  version: string|null

target:
  type: string|null
  id: string|null

model:
  provider: string|null
  id: string|null
  version_or_build: string|null
prompt_version: string|null
adapter_ref: exact-version-ref|null
version_bindings_ref: immutable-ref|null

status: string
payload_reference: object-ref|null
evidence_references: []
assertion_references: []
candidate_decision_references: []
policy_decision_references: []
human_action_references: []
uncertainty: object|null
warnings: []

usage: object|null
latency_ms: integer|null
estimated_cost: object|null
billing_references: []

security_classification: string
redaction_status: unreviewed|redacted|not_required|blocked
```

## Lineage rules

- `correlation_id` groups one logical case/incident execution.
- `causation_id` identifies the event that caused this event.
- `parent_event_id` may express structural nesting but must not replace causation.
- Important payloads/evidence use immutable/versioned references.
- AI interpretations never replace raw evidence.
- Corrections create new events and point back to the corrected event.
- Final decision events reference the candidate, optimization, policy and human events that justify them.

Workflow events require `execution_id`, `workflow_run_id`, bound workflow/version set and current fencing context. Node/agent/attempt/call events require the applicable identities above. Intake or administrative events before a workflow exists may omit run identity, but still require scope, aggregate, producer and correlation. `case_id`/`incident_id` are optional domain references, not Kernel branches or substitutes for aggregate identity. Unqualified legacy `run_id` is not a canonical identity.

## Ordering, idempotency and replay

- Authoritative state and semantic history are owned by trusted application components, not agent-authored event payloads. The semantic Ledger append boundary assigns a strictly increasing, contiguous committed revision **within one scoped aggregate**. Append uses compare-and-set against expected revision; stale writers are rejected.
- An aggregate can emit several events for one business transition, each with its own next committed revision, in the same transaction. There is no promised global total order between aggregates. `occurred_at` is source/event time, not an ordering or concurrency token; `recorded_at` is append time. Parent/causation references express cross-aggregate dependencies.
- A producer key is unique within `(scope, producer_id, aggregate identity)`. Retrying the same semantic append returns the original event ID/revision; changing payload under the same key is rejected. IDs and integrity references survive transport retries.
- Consumers durably deduplicate by `(consumer identity, scope, event_id)` and apply projection state/checkpoint in one atomic operation. Out-of-order delivery is buffered or resolved by aggregate revision; a gap triggers authoritative catch-up, not assumption of success.
- Replay rebuilds projections from semantic events. It never reissues provider/tool effects or treats old authorization as a fresh grant. A separately authorized redispatch obeys the original non-terminal execution envelope, fencing and stable effect idempotency identity.
- Lease ownership carries a monotonically advancing fencing epoch. Every authoritative lifecycle/result write checks current epoch and expected aggregate revision. Late outputs may be retained as attributed, non-authoritative observations; they cannot replace accepted results, human corrections or terminal state.
- Read/replay authorization uses the event/reference scope at every hop. Joining by correlation or a supplied resource ID does not grant cross-tenant access.

## Atomic state, history and outbox relationship

The component owning an authoritative change commits its state/revision, semantic event(s), accounting changes where relevant, and outbox projection intents in the **same atomic boundary**. Failed commits expose none of them as authoritative. M2 must not create an independent state store that can succeed without its history.

Existing transactional outbox may deliver projections. A remote Ledger, if ever justified, requires an equivalent durable commit-intent protocol with reconciliation before treating the transition as committed; publishing to a bus is not an atomic substitute. M1 requires no new bus or service.

Outbox `seq` is a delivery/replay cursor, not semantic aggregate revision, event causation or commit order. At-least-once publication permits duplicates. A transport row maps to semantic event ID(s), while published flags and retry counts remain mutable transport metadata. Durable execution consumers use the semantic protocol above, not UI SSE subscription state. Subscribe/catch-up races and replay pagination must be handled by the transport projection without weakening semantic ordering.

## Versioning and retention

Each event type has a schema/version and required identity/reference rules. Breaking semantic changes require a new schema version and explicit consumer compatibility. Unknown mandatory versions fail closed or are quarantined without applying effects. Upcasters preserve original bytes/identity and record their own transformation; they do not rewrite the ledger. Active execution definition bindings follow the Workflow Contract.

Corrections, supersession and redaction/retention actions are new attributed events. Payload/evidence objects have governed retention; references carry integrity and permitted-access metadata. Required legal erasure removes or restricts protected object content under approved governance while retaining only lawfully permitted minimal history and an erasure marker. "Immutable" does not authorize indefinite PII retention.

## Transport separation

The current/outgoing transport may be PostgreSQL outbox + Redis/SSE or something else. The event contract is semantic history and must not inherit transport-specific fields such as `published` as business truth.

## Security

Events may contain references to sensitive data but should avoid copying secrets/PII into broadly accessible payloads. Redaction status is explicit before evidence is exposed to models.
