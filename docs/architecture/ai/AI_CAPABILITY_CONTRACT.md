# AI Capability Contract

## Principle

A capability describes **what NOVU needs**, not which agent currently performs it.

The orchestrator requests `measure_facade_area`, never `call_facade_measurement_agent_v3`.

## Required declaration

```yaml
capability_id: string
capability_version: semver
semantic_purpose: string
accepted_input_schema: schema-ref
output_contract: schema-ref
minimum_evidence: []
minimum_quality:
  benchmark: benchmark-id
  threshold: number
supported_domains: []
risk_class: low|medium|high|critical
verifier_requirements: []
compatible_agent_contract: string
deprecation:
  status: active|deprecated|retired
  replacement: capability-ref|null
compatibility: {}
```

## Resolution

Capability resolution is expected to consider:

1. semantic/input compatibility;
2. risk policy;
3. evidence availability;
4. approved Champion implementations;
5. model/provider health;
6. quality thresholds;
7. privacy/security constraints;
8. latency and cost only after required quality/risk thresholds are satisfied.

## Versioning

Breaking semantic/input/output changes require a new capability version. Multiple versions may coexist while workflows migrate. Deprecation must be explicit and observable.

## Extension property

Future implementations such as vision LLM, geometry engine, drone photogrammetry or a NOVU fine-tuned model may provide the same capability without changing the calling workflow.
