# AI Model Router Contract

## Principle

Agents declare required model capabilities and quality/risk constraints. They do not hard-code OpenAI, Anthropic, Google, Qwen or a NOVU model.

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
```

## Routing inputs

The router may consider:

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

## Current-state note

The existing vision path already has provider selection and provider capability metadata, while offer processing has a stronger adapter abstraction. M2 should consolidate concepts rather than add a third provider system.
