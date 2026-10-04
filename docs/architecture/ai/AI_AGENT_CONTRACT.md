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

An invocation also receives the Controller-issued execution context, exact definition binding, scope, node/agent/logical-operation/attempt IDs and immutable input/candidate references. These are trusted invocation metadata, not agent-editable manifest fields. `timeout_seconds` is an upper bound within the remaining absolute workflow deadline; it does not create another wall-clock budget.

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
- Manifest tools/permissions/risk are declarations checked against trusted Policy, never self-issued grants. An agent cannot change governing policy, its effective risk, required verification/audit, human authority or execution limits.
- Every retry/fallback/subcall is admitted by the Workflow execution envelope. The agent cannot reset counters or start an automatic child with a fresh budget. Cancellation/stop propagates to its work; late results remain non-authoritative after a fence.
- Active invocations use the immutable workflow-start binding set, including permitted model/prompt/adapter alternatives. Availability never authorizes silent rebinding.
- Outputs link exact assertion/evidence transformations and the domain-neutral Candidate/Decision artifacts where applicable; missing freshness/completeness is explicit.
- Provider/tool egress and fallback satisfy hard privacy/locality/retention/data-use constraints. Untrusted evidence cannot gain instruction or permission authority.

## Role constraints

A specialist produces only its contracted result. A verifier attempts to invalidate or confirm an exact candidate revision; it does not silently replace it. An independent challenge supplies an alternative/adversarial assessment, not effect authority. An auditor checks the integrity of the control process. Objectives/constraints define an authorized, versioned context. Optimizer recommends. The trusted Decision operation selects/records; Policy authorizes/blocks; Gateway/executor performs an effect. Role names grant no permissions. Independence and mandatory gates follow bound risk Policy, with separate producer/verifier runs and no verifier candidate-write authority.

## Risk examples

- **low:** formatting/summarization that cannot change authoritative data.
- **medium:** non-authoritative classifications or suggestions.
- **high:** measurement, diagnosis, pricing inputs, recovery recommendation.
- **critical:** final decisions affecting safety, destructive operations, security or irreversible customer data.

Risk classification is a policy input, not a model opinion.

## Champion / Challenger

Champion state means approved for the declared capability/risk scope. Challenger runs only in explicitly allowed evaluation/shadow contexts. Promotion requires benchmark and, where applicable, shadow evidence.

Model lifecycle Challenger and a decision's independent challenge are distinct concepts. Evaluation context has explicit evidence-sharing and effect permissions; "shadow" is not a tool permission grant. Approval is represented per capability/risk scope, not inferred globally from one lifecycle label. Both contexts consume the same applicable execution/accounting envelope and retain version/lineage.
