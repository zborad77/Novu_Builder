# AI Human Gateway Contract

## Principle

Human participation is a first-class workflow actor, not an exception outside the system.

## States

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
- optional reason codes.

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
