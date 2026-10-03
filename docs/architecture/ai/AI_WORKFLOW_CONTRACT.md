# AI Workflow Contract

## Principle

Workflows are versioned definitions, not hard-coded Python if/else trees. A workflow composes capabilities, gates and transitions. The kernel must not contain domain-specific branches.

## Required declaration

```yaml
workflow_id: string
workflow_version: semver
trigger: trigger-contract
required_capabilities: []
optional_capabilities: []
nodes: []
transitions: []
conditions: []
retry_rules: []
fallback_rules: []
verification_gates: []
audit_gates: []
objectives_constraints_stage: node-ref|null
optimizer_stage: node-ref|null
policy_stage: node-ref|null
human_gates: []
completion_states: []
failure_states: []
rollback_compatibility: {}
```

## Node contract

Each node references a capability, deterministic operation, policy gate, human gate or aggregation step. Nodes do not embed provider/model identity.

Each transition records the event/condition that caused it.

## Required states

Workflows must be able to represent success, controlled failure, insufficient evidence, disagreement, retry, blocked decision and human escalation.

## Reference workflow A — domain

```text
Measurement capability
→ Measurement verification
→ Quality audit
→ Objectives & Constraints
→ Optimizer
→ Decision / Policy
→ Final
```

## Reference workflow B — operations

```text
Log Intake
→ Error Classification
→ Incident Correlation
→ Root Cause
→ RCA Verification
→ Remediation
→ Objectives & Constraints
→ Optimizer
→ Recovery Decision
→ Recovery Verification
→ Operational Audit
```

Both must run on the same generic workflow contract. A kernel special-case for one of these is a design smell.

## Expected domain coverage

Facade, Roofing, Waterproofing, Concrete, Masonry, Flooring, HVAC, Plumbing, Electrical, Window/Door, Painting and Operational Intelligence are known domains. The contract must also accept unknown future domains without kernel redesign.

## Compatibility

A persisted run references the exact workflow version. A workflow update never rewrites the historical graph for an existing completed run.
