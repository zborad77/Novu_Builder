# AI Policy Engine Contract

## Principle

LLM reasoning proposes and interprets. Deterministic policy enforces hard constraints.

The policy engine must be outside agent prompts and cannot be bypassed by an agent's textual argument.

The **trusted Policy Engine is the single authority for permission to perform an effect**. Decision selects/records a candidate; Optimizer recommends; the Execution Controller admits bounded work; Tool Gateway enforces and dispatches the authorized effect. None can manufacture `ALLOW`. Human approval is a required policy input where specified, not an alternate bypass.

## Policy outcomes

- ALLOW
- DENY
- REQUIRE_VERIFICATION
- REQUIRE_SECOND_OPINION
- REQUIRE_HUMAN
- BLOCK
- RETRY
- ESCALATE

## Policy input classes

- actor/agent identity and version;
- declared capability and risk;
- workflow state;
- evidence/uncertainty state;
- verifier/auditor result;
- tool/action classification;
- tenant/security context;
- data classification;
- model approval/health state;
- business/domain constraints;
- release/runbook approval state.

## Policy record

Every non-trivial outcome must produce a traceable record:

```yaml
policy_id: string
policy_version: string
policy_decision_id: string
decision: ALLOW|DENY|...
reason_codes: []
input_references: []
evaluated_at: timestamp
```

## Action-bound authorization

Only an applicable `ALLOW` outcome can yield an authorization reference. REQUIRE_* / RETRY / ESCALATE / BLOCK / DENY are not grants and do not themselves dispatch work. Policy-requested retry still needs Controller admission against the Workflow envelope.

```yaml
authorization_id: string
policy_decision_ref: immutable-ref
policy_ref: id@exact-version
actor_ref: verified-identity-and-exact-agent-version
scope: ScopeRef                       # verified tenant or explicit platform scope
execution_id: string
workflow_run_id: string
target_resource_ref: string
target_resource_revision: exact-revision|null
action: string
normalized_parameters_ref_or_hash: immutable-ref-or-integrity-hash
normalization_schema_ref: exact-version-ref
purpose: string
environment: verified-environment-ref
risk_class: low|medium|high|critical
security_classification: string
data_classification_ref: immutable-ref
candidate_ref: exact-revision-ref|null
context_ref: exact-revision-ref|null
decision_ref: exact-revision-ref|null
verification_audit_refs: []
required_human_action_refs: []
issued_at: timestamp
expires_at_or_validity_rule: bounded-validity
effect_idempotency_key: string|null
execution_fence_ref: current-revision-and-epoch
```

The binding includes the intended resource/action and normalized effect parameters, including resolved defaults; canonicalization uses the bound schema. Signatures, database references or other representations are implementation choices, but integrity and trusted ownership are mandatory. Sensitive parameters may remain in scoped immutable objects; a hash does not authorize access to their content.

An authorization is usable only while its exact bindings, required approvals, fence, deadline and resource/candidate revisions remain applicable. Changed target, parameters, purpose, environment, candidate or context require a new evaluation and, where required, new human approval. Expired, revoked, unavailable or materially mismatched authorization fails closed. Retry of the same effect keeps its effect idempotency identity but revalidates current permission/fence; it does not replay an expired approval.

## Deterministic authority and role separation

- Policy definitions, effective permissions, risk classifications and approved execution limits are trusted, version-bound configuration. Agent outputs/manifests are requests/declarations, never permission grants. Conflicting declarations cannot lower authoritative risk or broaden scope.
- Evaluation records the exact policy/input versions, reason codes and outcome. Missing required inputs, unverifiable gates or unavailable policy fail closed. Agents cannot alter policy, enlarge budgets, disable audit, remove mandatory verification or authorize their own critical outputs.
- A role name grants no authority. Required independent verification targets the exact candidate revision: producer/verifier run IDs differ, verifier cannot overwrite the candidate, and bound risk policy sets principal/implementation/context independence. Self-referencing a verifier capability is not proof of separation. Auditor checks controls/lineage; Challenger supplies an attributed alternative, neither grants effect permission.
- Only an authorized context operation may amend objectives/constraints. Optimizer cannot modify hard rules to make its recommendation feasible. Decision selection must retain evaluations, unresolved conflicts and rejected alternatives.
- Human requests are checked against verified authority and scope. Non-waivable hard policy remains binding for APPROVE/OVERRIDE/emergency actions. A permitted waiver has its own policy basis, actor, reason, scope and lineage; it never silently changes the governing policy of a run.
- Required audit evidence and authoritative state/history commit together under the Event Contract. If that atomic boundary cannot commit, the effect cannot be treated as newly authorized/committed.

## Hard privacy constraints

Tenant scope, permitted provider/tool egress, locality, retention, redaction and provider training/data-use restrictions are mandatory filters for every risk class. Privacy is not traded for cost, latency, health or quality. Authorization records the permitted recipient/environment and data classification; a fallback or external tool requires the same or stricter constraints.

Unmet/unknown required privacy assurance produces DENY/BLOCK or escalation without data egress. An approved local route may be selected only if it satisfies all other requirements; ownership of a model grants no exemption. Raw payload/log/evidence and training dataset use obey the Evidence/Observability retention and eligibility contracts.

## Examples

- critical measurement + no verifier → REQUIRE_VERIFICATION
- confidence below approved threshold → REQUIRE_SECOND_OPINION
- destructive database action → REQUIRE_HUMAN or BLOCK
- unknown catalog item in fail-closed workflow → BLOCK
- recovery command not present in approved runbook → DENY
- provider/model not approved for a critical capability → BLOCK
- sensitive evidence not redacted for external inference → DENY

## M1 boundary

This document does not choose an implementation language, rules engine or DSL. Those decisions belong after contracts and use cases are validated.
