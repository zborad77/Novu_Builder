# NOVU Construct — AI System Foundation

**Status:** Foundation / living architecture document  
**Version:** 0.3.0\
**Purpose:** Architectural constitution for NOVU AI.

## 1. Core principle

NOVU Construct is not one AI assistant and not one general-purpose agent. It is a controlled decision system composed of many narrowly specialized agents, verifiers, auditors, deterministic controls and human gates.

The system must be able to explain how a result was produced, identify the producer of each important value, preserve evidence and uncertainty, detect conflict, escalate insufficient evidence, distinguish the technically best solution from the optimal solution for a real situation, preserve full lineage, learn from verified outcomes, and replace agents/models without redesigning the platform.

The goal is not merely a system that works. The goal is a system whose decisions can become measurably better, safer, more appropriate and more explainable than alternatives.

## 2. Best is not always optimal

NOVU distinguishes:

- **Best technical solution** — strongest according to technical criteria.
- **Feasible solution** — valid and realistically executable under constraints.
- **Optimal solution** — best overall result for the concrete objectives, budget, lifetime, risk, time, operating conditions and other constraints.

NOVU must ask: **What is the best solution for this specific situation and objective?**

## 3. Decision chain

```text
SPECIALIST AGENTS
      ↓
VERIFIERS
      ↓
AUDITOR / QUALITY
      ↓
OBJECTIVES & CONSTRAINTS
      ↓
OPTIMIZER
      ↓
DECISION / POLICY
      ↓
FINAL APPROVAL
      ↓
FINAL RESULT
```

Each layer has a distinct responsibility.

## 4. Specialist agents

Agents should solve the smallest useful problem they can solve reliably.

Initial functional examples include Intake, Document, Vision, Measurement, Technical Diagnosis, Work Scope, Technology, Materials, Catalog, Pricing, Proposal, Risk, Compliance, Scheduling, Procurement, Cost Optimization and Quality.

Domain specialist families are part of the architecture from the beginning, even when implemented later:

- Facade
- Roofing
- Waterproofing
- Concrete
- Masonry
- Flooring
- HVAC
- Plumbing
- Electrical
- Window and Door
- Painting

A domain family may later split into narrower roles, e.g. Facade Vision, Defect, Measurement, Technology, Materials and Cost.

## 5. Separation of responsibility

Every agent has explicit inputs, outputs, permissions and prohibited actions. A measurement agent cannot change price or invent catalog items; a pricing agent cannot change approved measurements; a proposal agent cannot silently alter approved technical conclusions.

No implicit authority.

## 6. Verification

Important outputs require an independent verification path. Author and verifier are distinct roles.

Verification binds the exact candidate revision and its evidence/context. Separate producer/verifier runs and risk-appropriate identity/context independence are checked by trusted Policy; a role name or self-referencing capability does not prove independence. An independent challenge preserves an alternative/adversarial assessment without permission to replace the authoritative candidate.

Verifier outcomes:

- PASS
- FAIL
- DISAGREEMENT
- INSUFFICIENT_EVIDENCE
- REVIEW_REQUIRED

Verifier checks calculations, assumptions, evidence, contradictions, unsupported conclusions, confidence, completeness, duplicates, catalog validity and deterministic rules.

## 7. Auditor / quality layer

Normal recursive depth terminates at:

```text
WORKER → VERIFIER → AUDITOR
```

The auditor verifies process integrity: required verification occurred, evidence and uncertainty survived, disagreements were handled, assumptions were not promoted to facts, hard rules were not bypassed, and final values remain traceable.

This normal role chain is not the global execution bound. All nested verification/meta-audit, cycles, retries and fan-out obey the finite Workflow execution envelope; no role is exempt.

## 8. Objectives & Constraints

This role defines the decision context: customer objective, budget, lifetime, risk tolerance, downtime, deadline, warranty, regulation, future reconstruction, logistics, access, labor, environment and business priorities.

It does not choose the final solution.

The versioned Decision Context distinguishes non-waivable/explicitly waivable hard constraints from soft objectives and preferences. Domain schemas supply dimensions/units/evaluators without construction-specific Kernel logic.

## 9. Optimizer

The Optimizer compares verified candidates against objectives and constraints, identifies infeasible/dominated/unnecessarily expensive or risky solutions and recommends an optimum. It does not have final authority.

## 10. Decision / Policy

The decision layer receives verified candidates, audit state, objectives, constraints, optimization and deterministic policy. The trusted Decision operation selects/records; Optimizer recommends; Policy alone authorizes/blocks; Tool Gateway/executor performs the authorized effect. A selected candidate is not permission to execute it. Hard rules remain enforceable outside an LLM.

Candidate, Decision Context, Constraint Evaluation, Optimization Recommendation and Decision Record are domain-neutral artifacts in `AI_WORKFLOW_CONTRACT.md`. They preserve exact revisions, feasibility, PASS/FAIL/UNKNOWN constraints, trade-offs, rejected alternatives and policy/human references. Required failed/unknown hard constraints or unresolved critical evidence prevent finalization.

## 11. Human escalation

Valid outcomes include:

- HELP_REQUIRED
- ADDITIONAL_INPUT_REQUIRED
- HUMAN_REVIEW_REQUIRED
- EXPERT_REVIEW_REQUIRED
- DECISION_BLOCKED
- HUMAN_APPROVED
- HUMAN_REJECTED
- HUMAN_CORRECTION

Critical uncertainty must never be silently converted into certainty.

Human Gateway accepts APPROVE, REJECT, AMEND, REQUEST_MORE_EVIDENCE, PAUSE, RESUME, ABORT, OVERRIDE and EMERGENCY_STOP through verified scoped authority and revision/fencing checks. Late agent results cannot silently supersede an accepted correction/stop/override. Human approval cannot waive non-waivable hard policy or enlarge an active execution budget.

## 12. Immutable event history

Important actions produce versioned, traceable events. Typical families include case/input, agent run/result/failure, verification, audit, conflict/retry, help/human correction, objectives/constraints, optimization, decision/policy, finalization and system failure.

Raw evidence must remain distinct from AI interpretation.

Semantic events carry verified tenant/platform scope, aggregate revision, execution/node/agent/attempt/call identity and causal references. State/history/outbox intents commit atomically. Producer idempotency, consumer deduplication and fencing protect replay/concurrency; replay does not re-execute effects. Outbox/SSE remain transport, not semantic order or workflow authority.

## 13. Log categories

At minimum preserve execution, decision, evidence, error, recovery, help/escalation, correction and final logs.

## 14. Full lineage

For every important final value NOVU must be able to answer: **Why was this exact value used?**

## 15. Agent run record

A run should preserve case/run IDs, agent/version, provider/model/build, prompt version, input/output references, timestamps, confidence/uncertainty, evidence, warnings, status, latency and cost. Records are appended/versioned, not silently overwritten.

## 16. Champion / Challenger

Important roles eventually support a production Champion and a Challenger evaluated by benchmark and shadow execution. Promotion requires measured superiority for the specific NOVU task, not novelty.

## 17. NOVU benchmarks

NOVU should maintain domain benchmarks for Vision, Measurement, Diagnosis, Technology, Catalog, Pricing, Optimization, Decision and Proposal. Metrics include accuracy, severe error rate, human correction, verifier disagreement, confidence calibration/false confidence, latency, cost, retry and missing evidence.

## 18. Learning loop

```text
PRODUCTION CASE
→ AI RESULT
→ VERIFICATION
→ HUMAN CORRECTION / CONFIRMATION
→ VERIFIED DATASET
→ TRAINING / FINE-TUNING / RAG UPDATE
→ CANDIDATE
→ BENCHMARK
→ SHADOW
→ APPROVAL
→ NEW CHAMPION
```

Production models do not modify themselves uncontrolled after each case.

## 19. Positive and negative data

Preserve correct outputs, errors and corrections, disagreements, rejected solutions and reasons, optimizer recommendations, actual decisions and real-world outcomes.

## 20. Model independence

Business logic must not depend on one provider. Agents request model capabilities/quality, while routing may use OpenAI, Anthropic, Google, future providers or NOVU self-hosted models.

Different roles may use different models.

## 21. NOVU AI Kernel

Long-term core:

```text
NOVU AI KERNEL
├── Agent Registry
├── Capability Registry
├── Workflow Registry / Orchestrator
├── Event Ledger
├── Policy Engine
├── Model Router
├── Tool Gateway
├── Human Gateway
└── Knowledge / Context
```

The kernel works with contracts and capabilities, not hard-coded agent names.

## 22. Evidence and uncertainty

Important outputs distinguish:

- FACT
- INFERENCE
- ASSUMPTION
- DECISION

Confidence alone is insufficient. Preserve provenance, missing information, alternative hypotheses, measurement tolerance and critical unknowns.

Assertions have exact versions and evidence links, multiple-source `derived_from` transformations, model/prompt/adapter/tool identity, trust/completeness, freshness, contradiction and supersession. Decision finalization evaluates those properties, not only confidence. Large raw evidence remains in governed scoped objects referenced by the semantic Ledger.

## 23. Operational Intelligence

NOVU has a separate intelligence branch protecting NOVU itself:

```text
RAW LOGS / METRICS / TRACES
→ NORMALIZATION
→ ERROR CLASSIFIER
→ INCIDENT CORRELATOR
→ ROOT CAUSE AGENT
→ RCA VERIFIER
→ REMEDIATION AGENT
→ OBJECTIVES & CONSTRAINTS
→ OPTIMIZER
→ RECOVERY DECISION
→ AUTO / HUMAN policy gate
→ Recovery execution through Tool Gateway
→ RECOVERY VERIFIER
→ OPERATIONAL AUDITOR
→ INCIDENT CLOSED
→ POSTMORTEM / KNOWLEDGE / LEARNING
```

Raw machine evidence is immutable and separate from interpretations.

Autonomous recovery may use only approved, versioned, auditable runbooks with explicit permissions. Destructive or high-risk actions require policy/human gates. Successful command execution is not proof of recovery; the resulting system behavior must be verified.

RCA/remediation agents propose; Policy is the action authorizer and Gateway the executor boundary. Recovery consumes the same root execution budget and cannot modify its own governing policy, approvals or limits. Autonomous recovery remains deferred; its runbook envelope must define environment/blast-radius constraints, rollback/compensation applicability, cooldown/circuit breaker and bounded escalation before activation.

## 24. Future intelligence domains

The same kernel must allow Domain, Operational, Security, Commercial, Customer, Compliance, Planning, Procurement, Predictive, Financial, Sustainability and unknown future domains.

## 25. Extension principle

A new extension supplies a manifest, capabilities, input/output schemas, permissions, allowed tools, risk classification, policy requirements, verification path, tests, benchmark and version compatibility. It should not modify kernel internals.

## 26. Non-negotiable principles

1. No important final result without traceability.
2. No unsupported certainty.
3. No hidden assumptions.
4. No unrestricted agents.
5. No silent model/prompt changes in production.
6. No important AI output without an appropriate verification path.
7. No optimization without explicit objectives and constraints.
8. No final decision based solely on an LLM when deterministic policy is available.
9. No uncontrolled recursive agent chains.
10. No uncontrolled production learning.
11. No vendor lock-in at business-logic level.
12. Technically best does not automatically mean optimal.
13. Every failure should improve system knowledge.
14. Every correction is potential training/benchmark data.
15. Important agents must be replaceable without redesign.
16. One trusted Controller owns finite execution limits; no retry/fallback/redelivery/recovery resets them.
17. Privacy/locality/retention/data-use constraints are hard gates for every route and fallback.
18. Active runs never silently rebind workflow/agent/capability/policy/prompt/model/adapter/tool definitions.

## 27. Foundation governance

This is a living architectural constitution, not an implementation specification. Major conceptual changes require an ADR. Implementation must not silently violate this foundation. Unknown future requirements should be handled via extension points rather than speculative hard-coding.

Reference question:

> Does this feature, model, agent or infrastructure decision strengthen NOVU while preserving traceability, control, replaceability, measurable quality and future extensibility?

## 28. Current release boundary

M1 is documentation and read-only audit only. v0.8.6 remains a release candidate awaiting staging acceptance. Runtime implementation belongs to later milestones after explicit approval.

## 29. Normative M1 control boundaries (v0.3.0)

MUST/MUST NOT requirements in the contracts define target invariants, not claims of existing implementation. `AI_ARCHITECTURE_CURRENT_STATE_AUDIT.md` separates baseline facts/limitations from the single-owner target convergence map. This version strengthens the existing Foundation; it does not authorize M2 or create physical services.

- **Execution:** `AI_WORKFLOW_CONTRACT.md` defines the trusted Controller, finite validated depth/cycle/fan-out/run/concurrency limits, shared attempt/cost budget, absolute deadline, cancellation fences, terminal/partial/evidence outcomes and immutable start bindings. No production numeric defaults are selected in M1.
- **Authority:** `AI_POLICY_ENGINE.md` defines exact-effect authorization; `AI_TOOL_GATEWAY.md` validates it at dispatch. Actor/tenant/resource/revision/parameters/purpose/environment/risk/validity are bound, not supplied as permission by an agent.
- **History:** `AI_EVENT_CONTRACT.md` owns identity vocabulary, scope, aggregate ordering, atomic state/history/outbox, deduplication and stale writer rejection. Corrections are new events, never silent rewrites.
- **Human/evidence:** the Human and Evidence contracts define authority/fencing, transformation provenance, validity and critical conflict/missing-evidence handling.
- **Privacy:** recipient egress/locality/retention/training restrictions, redaction, raw-output retention and dataset eligibility are hard Policy/Router/Gateway constraints. Untrusted evidence cannot become instruction authority. Immutable references do not permit indefinite PII retention or exposing credentials/presigned URLs.
- **Convergence:** existing vision/offer adapters and domain persistence are reused through these boundaries. A third parallel provider/orchestration/retry/run store is prohibited. Logical modules and current outbox/storage are sufficient starting points.

## 30. Architectural motto

> **NOVU Construct does not ask one AI for an answer. It builds, verifies, challenges, optimizes and audits a decision.**
