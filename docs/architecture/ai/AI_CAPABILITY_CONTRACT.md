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

The logical Capability Resolver within the Workflow Orchestrator is the single owner of implementation resolution using trusted registry entries and Policy constraints. Registry data declares candidates; neither an agent nor a provider independently grants capability/risk approval. Provider/model selection is delegated to the Model Router port, not duplicated here.

Capability resolution is expected to consider:

1. semantic/input compatibility;
2. risk policy;
3. evidence availability;
4. approved Champion implementations;
5. model/provider health;
6. quality thresholds;
7. privacy/security constraints;
8. latency and cost only after required quality/risk thresholds are satisfied.

Privacy/tenant/locality/retention/data-use constraints are mandatory eligibility filters for all risk classes, never optional scoring terms. Failed or unknown required assurance blocks/escalates without data exposure. Resolution binds exact capability/agent definitions at workflow start and records quality/evidence/approval reasons; unavailable bound implementations do not silently upgrade. Fallback/retry requires Controller admission under the same execution envelope.

## Versioning

Breaking semantic/input/output changes require a new capability version. Multiple versions may coexist while workflows migrate. Deprecation must be explicit and observable.

Compatibility cannot rebind an active run to another version. Explicitly authorized migration/new execution retains original definitions and causal lineage. Minimum-evidence evaluation references exact requirement versions, source freshness/trust/completeness and candidate revision; a high confidence value does not satisfy missing required evidence.

## Extension property

Future implementations such as vision LLM, geometry engine, drone photogrammetry or a NOVU fine-tuned model may provide the same capability without changing the calling workflow.
