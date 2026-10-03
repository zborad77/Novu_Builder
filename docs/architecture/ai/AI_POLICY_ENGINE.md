# AI Policy Engine Contract

## Principle

LLM reasoning proposes and interprets. Deterministic policy enforces hard constraints.

The policy engine must be outside agent prompts and cannot be bypassed by an agent's textual argument.

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
decision: ALLOW|DENY|...
reason_codes: []
input_references: []
evaluated_at: timestamp
```

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
