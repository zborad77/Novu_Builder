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
execution_limits: approved-policy-ref
version_bindings: immutable-binding-set-ref
completion_states: []
failure_states: []
rollback_compatibility: {}
```

## Node contract

Each node references a capability, deterministic operation, policy gate, human gate or aggregation step. Nodes do not embed provider/model identity.

Each transition records the event/condition that caused it.

Every effectful node requires action-bound Policy authorization and Tool Gateway enforcement, even when no separate `policy_stage` is drawn. A nullable stage is not a permission bypass. Risk policy determines mandatory verification, audit and human gates for the exact candidate revision.

## Normative execution envelope

The **trusted Execution Controller, a logical responsibility of the Workflow Orchestrator**, is the sole owner of admission, execution counters, lifecycle transitions and cancellation fences. It applies approved Policy limits; agents, adapters, Router, queues and Operational Intelligence cannot issue themselves a new envelope or raise/reset its limits. This does not require a separate service.

```yaml
execution_id: string                 # root logical execution and shared budget
workflow_run_id: string              # this workflow instance
parent_workflow_run_id: string|null
workflow_ref: id@exact-version
version_bindings_ref: immutable-ref
scope: ScopeRef                      # Event Contract: tenant or explicit platform scope
started_at: timestamp
absolute_deadline: timestamp
limits:
  maximum_workflow_depth: positive-integer
  cycle_policy: reject|bounded
  bounded_cycle_limits: []           # approved finite traversal limits, when allowed
  maximum_fan_out: positive-integer
  maximum_total_node_runs: positive-integer
  maximum_total_agent_runs: positive-integer
  maximum_concurrency: positive-integer
  shared_attempt_budget: positive-integer
  cost_ceiling:                      # all inference, tools and recovery
    amount: non-negative-number
    unit: string
    currency: string|null
    valuation_policy_ref: exact-version-ref
consumption_ref: authoritative-accounting-ref
state: workflow-state
revision: integer
fencing_epoch: integer
cancellation:
  state: NONE|REQUESTED|CANCELLED|ABORTED|EMERGENCY_STOPPED
  action_ref: human-or-system-action-ref|null
  accepted_at: timestamp|null
```

All limits MUST be finite, validated before admission and supplied by approved configuration; M1 assigns no production numeric defaults. Graph validation rejects unbounded cycles, unknown/unbounded nested workflows and fan-out that cannot satisfy the envelope. Bounded cycles declare their traversal counter and exhaustion outcome. Verification and meta-audit are not exemptions from depth/run limits.

Child workflows share the root `execution_id`, deadline and consumption ledger. Their limits may only tighten the parent's remaining limits. `workflow_run_id` is not a license to start a fresh budget.

Depth measures nested workflow/node/agent parentage, including verification/audit invocations; bounded cycle traversal and total runs separately limit repeated sequential work. Fan-out counts admitted children of a node activation; concurrency counts in-flight admitted work across the entire root execution, not per worker.

### Attempts, retries and cost admission

- A logical operation keeps its identity across retries. Each new execution attempt has a distinct `attempt_id`, optional parent attempt and one idempotently recorded admission debit. Node attempts and their provider/tool sub-attempts are distinguishable; no work is hidden inside an unmetered parent attempt.
- Every initial attempt, workflow retry, provider retry, Router fallback, queue redelivery admitted for re-execution, and recovery attempt consumes the **same shared attempt budget**. Only the Controller can grant an attempt credit. A transport duplicate acknowledged without redispatch creates no work and cannot issue an extra credit.
- Provider-local retry is mechanical transport handling by the execution adapter, using Controller-issued credits. SDK retries MUST be exposed/accounted or conservatively bounded and charged at admission; unbounded or unaccounted retry is not compliant. Router selection never grants retry authority.
- Admission atomically checks remaining attempts, depth, run counts, concurrency, deadline, cancellation and cost. Concurrent children cannot each reserve the same remaining capacity.
- Each potentially billable call reserves a conservative cost bound before dispatch. Pending/uncertain charges remain held; unknown unbounded cost blocks admission. Actual usage, estimated valuation and confirmed billing are distinct accounting records. Unused cost reservations may be released once; spent attempts are never refunded or reset.
- Retries preserve failed-attempt history. At-least-once redelivery uses a new admitted attempt when re-execution is necessary, a fresh fencing epoch where ownership changes, and the same logical-operation/effect idempotency key.
- Restart, pause/resume, lease recovery and Operational recovery preserve execution identity, original deadline and consumed/held budgets. They cannot manufacture another root execution as an automatic retry. An independently authorized new request is explicitly linked to its predecessor and is not an exemption from parent limits when it is a child.

### Cancellation, terminal states and partial results

Non-terminal states are `CREATED`, `RUNNING`, `WAITING_FOR_EVIDENCE`, `WAITING_FOR_HUMAN` and `PAUSED`. Waiting and pause consume the original wall-clock window; they do not extend the deadline.

Terminal states are `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`, `INSUFFICIENT_EVIDENCE`, `BLOCKED`, `BUDGET_EXHAUSTED`, `DEADLINE_EXCEEDED`, `CANCELLED`, `ABORTED` and `EMERGENCY_STOPPED`. Only the Controller commits lifecycle transitions using the current revision/fence. Terminal states cannot resume or accept a late authoritative result.

Accepted cancellation/abort/stop installs a durable stop fence before acknowledging the action, denies new dispatch and propagates to children, queues, providers and tools. Gateway checks the fence at effect admission. Already-dispatched, non-cancellable external effects are tracked as in-flight/uncertain and reconciled; no contract promises to undo an irreversible effect. Their late outputs and costs are recorded, but cannot reopen or supersede the stopped run. Compensation requires its own authorized, bounded recovery execution.

Budget/deadline exhaustion terminates admission with the corresponding terminal state. Transport DLQ retains failed delivery/work references, not permission to restart a terminal execution. Reprocessing requires explicit authorization and preserves the original envelope when continuing a non-terminal run; a terminal predecessor requires a separately authorized, causally linked request.

Partial completion is permitted only by declared workflow/risk policy: expose completed, failed, skipped and unresolved nodes plus evidence gaps; never label a failed mandatory gate as success. Missing mandatory evidence or failed verification blocks final selection. The workflow may enter bounded `WAITING_FOR_EVIDENCE`/`WAITING_FOR_HUMAN`, or terminate `INSUFFICIENT_EVIDENCE`/`BLOCKED`; expiration still produces `DEADLINE_EXCEEDED`. No missing evidence is replaced by confidence.

## Minimal domain-neutral decision artifacts

All artifacts have an immutable/versioned `ArtifactRef` (identity, exact revision, schema version and integrity reference), verified `ScopeRef` and creation event. Evidence references use the Evidence Model. Domain schemas supply values/units and evaluators; these artifacts do not prescribe a universal optimization algorithm.

```yaml
CANDIDATE:
  candidate_id: string
  candidate_version: exact-version
  proposed_output_ref: immutable-ref
  evidence_refs: []
  assertion_refs: []
  technical_feasibility: PASS|FAIL|UNKNOWN
  feasibility_evaluation_ref: immutable-ref
  verification_refs: []               # exact candidate revision and independence
  challenge_refs: []                  # independent alternative/adversarial assessments
  audit_refs: []

DECISION_CONTEXT:
  context_id: string
  context_version: exact-version
  hard_constraints: []                # ID/version, evaluator, inputs, waivability policy
  soft_objectives: []                 # ID/version, dimension, direction, units
  preferences: []                     # weights/priority/trade-off rules, if applicable
  context_authority_ref: immutable-ref
  evidence_refs: []

CONSTRAINT_EVALUATION:
  evaluation_id: string
  candidate_ref: exact-revision-ref
  context_ref: exact-revision-ref
  constraint_results: []              # constraint ref, PASS/FAIL/UNKNOWN, reason, evidence
  evaluator_refs: []                  # exact deterministic/policy evaluator versions
  feasible: PASS|FAIL|UNKNOWN

OPTIMIZATION_RECOMMENDATION:
  recommendation_id: string
  candidate_refs: []
  context_ref: exact-revision-ref
  constraint_evaluation_refs: []
  comparison_method_ref: exact-version-ref
  trade_offs: []
  recommended_candidate_ref: exact-revision-ref|null
  rejected_alternatives: []           # candidate ref and rejection/dominance reasons
  uncertainty_ref: immutable-ref

DECISION_RECORD:
  decision_id: string
  decision_revision: integer
  decision_intent_ref: immutable-ref
  candidate_refs: []
  selected_candidate_ref: exact-revision-ref|null
  context_ref: exact-revision-ref
  constraint_evaluation_refs: []
  optimization_recommendation_ref: exact-revision-ref|null
  verification_challenge_audit_refs: []
  rejected_alternatives: []
  selection_reason_codes: []
  policy_decision_refs: []
  required_human_action_refs: []
  status: PROPOSED|SELECTED|BLOCKED|REJECTED|SUPERSEDED
  effect_authorization_refs: []
```

Hard constraints are evaluated before preference ranking. `FAIL` or `UNKNOWN` for a required non-waivable constraint prevents authoritative selection/effect. Waivable constraints require an explicit permitted exception record; a model or ordinary approval cannot invent an exception. Technical feasibility is one dimension, not proof of overall optimality.

Optimizer **recommends**; the trusted Decision operation **selects/records** using satisfied gates; Policy **authorizes/blocks**; Tool/executor **performs** an effect. A `SELECTED` record does not itself grant effect permission. Required human approval and Policy authorization bind the same exact candidate/context/decision revisions. Finalization checks missing evidence, unresolved critical conflicts and all mandatory verification/audit/human results. Challenger assessments do not become authoritative by their role name or model lifecycle state.

`decision_revision` identifies immutable selection/effect intent: exact candidates/context, requested outcome, rationale and effect parameters. Approval, authorization and lifecycle status are appended as event-backed records/snapshots referring to that intent; current projection status may advance without changing it or rewriting old snapshots. Event aggregate revision is a separate concurrency token. Approval of an unchanged intent may support its PROPOSED → SELECTED transition; a material intent/candidate/context change creates a new decision revision and invalidates affected approvals. Gateway binds `decision_ref` to that exact intent revision and checks current authoritative lifecycle/fence, not a mutable "latest" snapshot.

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
→ AUTO / HUMAN policy gate
→ Recovery execution through Tool Gateway
→ Recovery Verification
→ Operational Audit
```

Both must run on the same generic workflow contract. A kernel special-case for one of these is a design smell.

## Expected domain coverage

Facade, Roofing, Waterproofing, Concrete, Masonry, Flooring, HVAC, Plumbing, Electrical, Window/Door, Painting and Operational Intelligence are known domains. The contract must also accept unknown future domains without kernel redesign.

## Compatibility

A persisted run references the exact workflow version. A workflow update never rewrites the historical graph for an existing completed run.

At workflow start, resolve and persist an immutable binding set for workflow, capability/agent definitions, policy, prompt, model/provider/adapter identities and applicable tool versions, including the permitted fallback alternatives. Router may choose only among those bound alternatives; health may remove an alternative but cannot introduce or rebind one. Bindings remain fixed for active as well as completed runs. Unavailable bindings cause block/escalation, not silent upgrade. Unknown provider artifact identity is recorded as an assurance limitation and admitted only if the bound risk policy permits it; an alias is not claimed to be an immutable model artifact. A changed binding requires an explicitly authorized new run or migration with recorded lineage, never an in-place reinterpretation of history.
