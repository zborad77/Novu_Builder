# NOVU AI Architecture

Status: M1 Architecture Contracts  
Foundation: `NOVU_AI_SYSTEM_FOUNDATION.md` v0.2.1  
Release boundary: documentation-only before v0.8.6 staging acceptance.

## Purpose

This directory defines the contracts for a future NOVU AI Kernel. M1 does **not** implement an agent runtime, change production behavior, add dependencies, alter database schema, or change deployment.

The kernel is intended to coordinate capabilities rather than hard-coded agent names. Domain and operational intelligence must use the same control concepts: explicit contracts, evidence, uncertainty, verification, audit, objectives and constraints, optimization, deterministic policy, human escalation, event lineage, measurable quality, and replaceable model/provider implementations.

## Documents

- `NOVU_AI_SYSTEM_FOUNDATION.md` — architectural constitution.
- `AI_AGENT_CONTRACT.md` — minimum declaration for every agent.
- `AI_CAPABILITY_CONTRACT.md` — capability semantics independent of implementation.
- `AI_WORKFLOW_CONTRACT.md` — versioned workflow graph contract.
- `AI_EVENT_CONTRACT.md` — universal event envelope and lineage.
- `AI_EVIDENCE_MODEL.md` — facts, inference, assumptions, decisions and uncertainty.
- `AI_POLICY_ENGINE.md` — deterministic enforcement boundary.
- `AI_MODEL_ROUTER.md` — provider/model-independent routing.
- `AI_TOOL_GATEWAY.md` — audited tool access.
- `AI_HUMAN_GATEWAY.md` — human participation as a first-class workflow actor.
- `AI_OBSERVABILITY.md` — telemetry, quality and operational signals.
- `AI_OPERATIONAL_INTELLIGENCE.md` — log/incident/recovery intelligence.
- `AI_ARCHITECTURE_CURRENT_STATE_AUDIT.md` — read-only mapping of current master against the foundation.

## M1 guardrails

Until v0.8.6 has passed staging and release acceptance:

- no runtime implementation;
- no database or Alembic changes;
- no new production dependencies;
- no changes to existing providers, worker orchestration, Redis behavior, API or business logic;
- no new event bus;
- no autonomous recovery;
- no self-hosted model/GPU integration.

Findings discovered by the audit are documented, not repaired.

## Reference flows

Domain reference:

```text
Measurement Agent
→ Measurement Verifier
→ Quality Auditor
→ Objectives & Constraints
→ Optimizer
→ Decision / Policy
→ Final
```

Operational reference:

```text
Log Intake
→ Error Classifier
→ Incident Correlator
→ Root Cause Agent
→ RCA Verifier
→ Remediation
→ Objectives & Constraints
→ Optimizer
→ Recovery Decision
→ Recovery Verifier
→ Operational Auditor
```

If a future kernel requires special-case code to distinguish these flows, treat that as a design smell and reassess the contracts.
