# AI Human Gateway Contract

## Principle

Human participation is a first-class workflow actor, not an exception outside the system.

## Request/outcome vocabulary

These are human request/outcome labels, not substitutes for the Workflow Contract's execution lifecycle:

- HELP_REQUIRED
- ADDITIONAL_INPUT_REQUIRED
- HUMAN_REVIEW_REQUIRED
- EXPERT_REVIEW_REQUIRED
- HUMAN_APPROVED
- HUMAN_REJECTED
- HUMAN_CORRECTION
- DECISION_BLOCKED

## Request

A human request records:

- reason code;
- requested expertise/role;
- decision/input required;
- relevant evidence and uncertainty;
- candidate outputs;
- deadline/priority where relevant;
- security/tenant scope.

## Response

A human response records:

- actor identity;
- action/state;
- structured decision or correction;
- evidence/comment reference;
- timestamp;
- mandatory reason codes.

Every accepted action uses the normative record below; reason and verified authority are mandatory, not optional. Human Gateway is the single trusted boundary for accepting human interventions. It verifies identity/authority/scope and coordinates with Policy and the Execution Controller; it does not independently overwrite workflow state.

## General actions

| Action | Normative effect within verified authority |
|---|---|
| APPROVE | Approve only the named candidate/decision revision and context; satisfy a human gate, not grant effect permission by itself |
| REJECT | Reject the named candidate/decision revision; block dependent finalization, without implying cancellation of unrelated work |
| AMEND | Create a new attributed candidate/context/assertion revision; invalidate approvals/gates whose inputs materially changed |
| REQUEST_MORE_EVIDENCE | Record missing evidence and enter a declared bounded evidence/human wait; no fabricated certainty |
| PAUSE | Controller pauses the targeted non-terminal run and fences new dispatch; original deadline and budget continue to apply |
| RESUME | Resume a paused non-terminal run after current-state/Policy checks, with preserved identity, bindings, deadline and consumption |
| ABORT | Terminally abort the targeted execution through Controller; invalidate pending dispatch/approvals |
| OVERRIDE | Record an explicitly permitted authoritative replacement or waivable exception with scope/reason; non-waivable policy still applies |
| EMERGENCY_STOP | Immediately install the permitted stop fence for the explicitly authorized execution/resource scope; record actor and bounded emergency authority |

```yaml
human_action_id: string
action: APPROVE|REJECT|AMEND|REQUEST_MORE_EVIDENCE|PAUSE|RESUME|ABORT|OVERRIDE|EMERGENCY_STOP
actor_ref: verified-human-identity
authority_ref: verified-role-grant-and-version
scope: ScopeRef
reason: string
target:
  execution_id: string
  workflow_run_id: string
  node_or_agent_run_ref: string|null
  candidate_ref: exact-revision-ref|null
  context_ref: exact-revision-ref|null
  decision_ref: exact-revision-ref|null
target_revision: exact-revision
expected_current_revision: integer
expected_current_state: string
previous_state: string
resulting_state: string
timestamp: timestamp
evidence_context_refs: []
authorization_ref: action-bound-ref|null
producer_idempotency_key: string
```

Verified authority covers tenant/platform scope, target, permitted action, environment and validity; a claimed role name is not proof. Effectful state changes require the corresponding Policy authorization. Ordinary approval cannot change governing risk, execution limits, audit requirements or non-waivable hard rules. Emergency authority may use a pre-approved constrained stop permission when normal dependencies are impaired, but it must be verifiable, attributed and cannot grant new destructive capabilities.

## Concurrency, transitions and precedence

Human requests bind exact candidate/context/decision revisions and expire no later than the applicable execution/gate deadline. A stale approval cannot be applied to a newer revision or changed evidence/parameters. Re-evaluation creates a new request/action; no silent retargeting is allowed.

Accept actions using compare-and-set on expected authoritative state/revision and current execution fence. Record the actual previous/resulting states with the action, semantic history and projection intent atomically. A concurrent conflict returns rejection/current-state information and records the rejected attempt; it never overwrites the winning action. Duplicate submission returns the original action/outcome, not another transition.

The Controller alone commits execution lifecycle transitions. PAUSE/RESUME apply only to compatible non-terminal states; deadline/budget exhaustion still terminates waits. ABORT/EMERGENCY_STOP are terminal for the targeted execution and cannot be resumed. An accepted stop fences new effects before acknowledgement and propagates according to the Workflow Contract; previously dispatched effects are tracked/reconciled rather than assumed undone.

An accepted AMEND/OVERRIDE/correction installs an authoritative revision/fence for the affected artifact. A late agent result may be retained as a non-authoritative observation but cannot supersede that correction, stop or override. Replacing an authoritative human decision requires a separately authorized, explicit supersession referencing that exact human action and checking current authority/revision. A new agent run is not sufficient authority.

Human statements retain their evidence/assertion class and source trust; accepting a correction as authoritative for the workflow does not turn every human assertion into an independently verified FACT. Non-waivable hard policy remains binding on humans as well as agents.

## Lineage

Human actions use the same correlation/run/workflow lineage as agent and policy actions. Corrections do not overwrite AI history.

## Escalation policy examples

Human/expert review is appropriate when:

- evidence is materially insufficient;
- verifier and worker disagree above allowed threshold;
- a critical unknown affects safety or contractual outcome;
- policy requires approval;
- a destructive/privileged operational action is proposed;
- no approved model/agent meets the required quality threshold.

## Learning

Confirmed/corrected human results are candidates for benchmark and training datasets only after dataset governance/quality checks; a single correction does not automatically retrain production.
