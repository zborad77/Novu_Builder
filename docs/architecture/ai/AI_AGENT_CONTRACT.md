# AI Agent Contract

## Purpose

Every agent registered in NOVU must declare an explicit, versioned contract. No agent receives implicit authority from its name, model or placement in a workflow.

## Required manifest

```yaml
agent_id: string
agent_version: semver
purpose: string
domain: string
capabilities: [capability_id@version]

input_schema: schema-ref
output_schema: schema-ref

evidence_requirements: []
uncertainty_contract: schema-ref

allowed_tools: []
read_permissions: []
write_permissions: []
prohibited_actions: []

risk_level: low|medium|high|critical

model_requirements: []
model_policy:
  minimum_quality: number|null
  privacy_class: string|null
  champion_required: boolean

timeout_seconds: number
retry_policy: policy-ref|null
fallback: agent-or-capability-ref|null

verifier: capability-ref|null
auditor_required: boolean
human_escalation_rules: []

event_requirements: []
logging_policy: policy-ref
evaluation_suite: benchmark-ref
benchmark_requirements: []

lifecycle_state: draft|challenger|champion|deprecated|disabled
compatibility:
  min_kernel_contract: string
  max_kernel_contract: string|null
```

## Invariants

- Inputs and outputs are schema validated.
- The agent cannot grant itself tools or permissions.
- A tool not declared is denied.
- Writes outside declared scope are denied.
- Critical outputs require a verification route defined by risk policy.
- Missing mandatory evidence produces an explicit insufficient-evidence state.
- Retry does not erase the failed attempt; each attempt has its own run/event lineage.
- Model/provider changes do not change `agent_id`; behaviorally relevant changes require `agent_version` or declared model/prompt version change.
- Prompt/model/adapter versions used in production are recorded.
- An agent cannot silently convert assumptions into facts.
- Human correction creates a new traceable result rather than overwriting the original.

## Role constraints

A specialist produces only its contracted result. A verifier attempts to invalidate or confirm a result; it does not silently replace it. An auditor checks the integrity of the control process. Objectives/constraints define context. Optimizer recommends. Decision/policy selects or blocks according to policy.

## Risk examples

- **low:** formatting/summarization that cannot change authoritative data.
- **medium:** non-authoritative classifications or suggestions.
- **high:** measurement, diagnosis, pricing inputs, recovery recommendation.
- **critical:** final decisions affecting safety, destructive operations, security or irreversible customer data.

Risk classification is a policy input, not a model opinion.

## Champion / Challenger

Champion state means approved for the declared capability/risk scope. Challenger runs only in explicitly allowed evaluation/shadow contexts. Promotion requires benchmark and, where applicable, shadow evidence.
