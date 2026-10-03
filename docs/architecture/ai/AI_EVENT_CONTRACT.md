# AI Event Contract

## Purpose

Define a universal event envelope for immutable AI/business decision history across all intelligence domains. This is conceptually distinct from metrics/logs/traces and from a transport outbox.

## Envelope

```yaml
event_id: uuid
event_type: string
schema_version: semver
occurred_at: timestamp

case_id: string|null
incident_id: string|null
run_id: string
workflow_id: string
workflow_version: string
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

status: string
payload_reference: object-ref|null
evidence_references: []
uncertainty: object|null
warnings: []

usage: object|null
latency_ms: integer|null
estimated_cost: object|null

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

## Transport separation

The current/outgoing transport may be PostgreSQL outbox + Redis/SSE or something else. The event contract is semantic history and must not inherit transport-specific fields such as `published` as business truth.

## Security

Events may contain references to sensitive data but should avoid copying secrets/PII into broadly accessible payloads. Redaction status is explicit before evidence is exposed to models.
