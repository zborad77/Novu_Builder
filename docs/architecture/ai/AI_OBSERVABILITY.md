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

Operational telemetry should carry or be joinable by `correlation_id`, `run_id`, workflow/case/incident identifiers while avoiding sensitive/high-cardinality leakage into metric labels.

## Privacy

Secrets, credentials and unnecessary customer PII must be redacted before log/evidence exposure to external models. Redaction failures are observable security events.

## Existing foundations

Current master already has structlog, HTTP/job/queue/storage/catalog metrics, worker heartbeat, outbox/SSE metrics and readiness endpoints. M2/M3 should extend these patterns rather than duplicate them.
