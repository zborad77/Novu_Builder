# AI Observability Contract

## Separation of concerns

NOVU must keep these distinct:

1. **Telemetry** — metrics, logs, traces used for operations and performance.
2. **Immutable AI/business event history** — semantic lineage and decisions.
3. **Evidence** — source material supporting assertions.
4. **Audit/security trail** — who/what performed sensitive actions.

A log line is not automatically an event ledger record; an event ledger is not a metrics store.

## Dimensions

Observe by workflow, agent, agent version, capability, model/provider/build, verifier, auditor, tool, decision and incident where cardinality/security constraints allow.

## Core measures

- latency;
- cost/token usage;
- success/error/timeout rates;
- retry rate;
- human correction rate;
- verifier disagreement rate;
- audit failure rate;
- insufficient-evidence rate;
- false-confidence rate;
- benchmark/quality score;
- model/provider health;
- queue/worker health;
- event publish/replay lag.

## Correlation

Operational telemetry should carry or be joinable by canonical correlation/execution/run identities and optional workflow/case/incident references while avoiding sensitive/high-cardinality leakage into metric labels.

Canonical join identities are `execution_id`, `workflow_run_id`, `node_run_id`, `agent_run_id`, `attempt_id`, provider/model/tool call IDs and policy/human/decision refs from the Event Contract. Legacy `run_id` must be mapped explicitly rather than treated as a universal identity. Traces/logs carry scoped references; metric labels remain bounded and cannot grant cross-scope access.

## Execution and accounting signals

Observe admission rejection/exhaustion, deadline remaining, consumed/held budgets, retry/fallback/redelivery/recovery attempts, cancellation propagation, stale-writer rejection and late non-authoritative results. Telemetry observes these states; it does not own counters, reset budgets or drive unauthenticated recovery. Controller is the execution owner; the shared Cost Accounting port is the settlement owner.

Usage records identify scope, execution/workflow/node/agent/attempt/call, capability/role, selected/observed model/prompt/adapter/tool versions and valuation policy. Separate actual measured usage (tokens or declared non-token units), estimated monetary valuation and confirmed billing/reconciliation. Record currency/unit/rate identity, reservations and uncertain pending charges; zero/unknown usage or estimated cost is not proof of free inference. Idempotent settlement keys prevent duplicate accounting under replay. Root ceilings include verifier/challenger/auditor/tools and recovery, not only the primary model call.

## Privacy

Secrets, credentials and unnecessary customer PII must be redacted before log/evidence exposure to external models. Redaction failures are observable security events.

Apply verified tenant/platform scope, classification, recipient egress/locality, retention and provider data-use constraints before log/model/tool exposure. Avoid storing presigned URL credentials or raw sensitive payloads in labels/events. Raw provider output has explicit scoped access/retention; curated assertions are separate. Training/benchmark eligibility requires Evidence Model governance, not automatic reuse of corrections/logs. Untrusted telemetry content cannot modify Policy, instructions, approvals or execution limits. Retention/erasure actions preserve lawful minimal lineage without making immutability an indefinite-retention requirement.

## Existing foundations

Current master already has structlog, HTTP/job/queue/storage/catalog metrics, worker heartbeat, outbox/SSE metrics and readiness endpoints. M2/M3 should extend these patterns rather than duplicate them.
