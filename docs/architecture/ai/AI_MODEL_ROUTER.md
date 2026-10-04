# AI Model Router Contract

## Principle

Agents declare required model capabilities and quality/risk constraints. They do not hard-code OpenAI, Anthropic, Google, Qwen or a NOVU model.

The trusted **Model Router port is the single selection authority** among the workflow-start bound provider/model/adapter alternatives. In the compatibility phase it delegates to existing selection/adapter code; it is not a third parallel provider runtime. Policy defines eligibility, Controller admits bounded work, and provider adapters execute the selected calls.

## Request contract

```yaml
required_capabilities:
  - high_accuracy_multimodal_reasoning
quality_threshold: number
risk_class: low|medium|high|critical
privacy_class: string
latency_budget_ms: integer|null
context_requirements: {}
tool_requirements: []
allow_challenger: boolean
execution_context_ref: controller-issued-ref
version_bindings_ref: immutable-ref
scope: ScopeRef
data_constraints_ref: immutable-ref
```

## Routing inputs

The router MUST first enforce Policy eligibility and hard tenant/privacy/locality/retention/provider-data-use constraints. It may then compare eligible candidates using:

1. benchmark quality for the exact capability/task;
2. Champion/Challenger state;
3. risk;
4. evidence sensitivity/privacy;
5. model/provider availability and health;
6. context/image/tool support;
7. latency;
8. cost.

For critical NOVU tasks, **accuracy and risk thresholds are hard gates**. Cost is optimized only among candidates that satisfy the required quality/risk threshold.

## Outputs

```yaml
selected_provider: string
selected_model: string
selected_build: string|null
selected_adapter_ref: exact-version-ref
selected_binding_ref: immutable-ref
routing_policy_version: string
selection_reason_codes: []
fallback_chain: []
```

## Rules

- Model changes are observable and versioned.
- A fallback cannot lower quality/risk below policy minimum without explicit escalation.
- Challenger traffic is shadow/evaluation-only unless promoted for the capability/risk class.
- Model health may remove a candidate, but must not silently change the semantic contract.
- Self-hosted NOVU models are first-class candidates, not privileged by ownership.
- Provider retries and every fallback call require Controller-issued attempt credit and cost admission under the same root execution. Router cannot reset/increase budget, deadline or cancellation state.
- Fallback never weakens privacy, locality, retention, redaction or provider training/data-use restrictions, for any risk class. If no eligible bound route remains, block/escalate without sending data; a permitted local route must still satisfy quality/risk constraints.
- Routing records selected and actually observed provider/model/adapter identity per physical call. Prompt identity follows the immutable binding set; aliases/unknown builds explicitly carry assurance limitations and cannot be described as verified immutable artifacts.
- Active runs cannot adopt newly registered definitions or fallback identities. Health may remove a bound candidate but cannot silently replace it. Changed definitions require an authorized new run/migration and lineage.

## Data exposure contract

Data constraints identify verified scope, classification, allowed recipient/environment, permitted egress, locality, retention, provider training/data-use restrictions and redaction requirements. Required assurances must be verifiable; uncertainty is not permission. Provider-specific API representation, local inference inputs and multimodal conversion belong in adapters, not business contracts or domain branches in Kernel.

Raw provider output uses scoped retention/access policy independently of parsed assertions. Presigned URLs bind object/version, purpose/recipient and expiry; they are access credentials, not permanent evidence identity. Evidence content is untrusted data and cannot change instructions, tool authority or routing constraints. Reuse for benchmark/training/RAG requires separate dataset eligibility approval, not mere successful inference.

## Current-state note

The existing vision path already has provider selection and provider capability metadata, while offer processing has a stronger adapter abstraction. M2 should consolidate concepts rather than add a third provider system.
