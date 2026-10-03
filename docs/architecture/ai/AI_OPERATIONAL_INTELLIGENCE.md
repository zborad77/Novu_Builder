# AI Operational Intelligence

## Purpose

Operational Intelligence protects NOVU itself. It is a controlled diagnostic/recovery decision system, not a single log-reading bot.

## Reference chain

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
→ AUTO / HUMAN
→ RECOVERY AGENT
→ RECOVERY VERIFIER
→ OPERATIONAL AUDITOR
→ INCIDENT CLOSED
→ POSTMORTEM / KNOWLEDGE / LEARNING
```

## Raw vs interpretation

Raw machine evidence remains immutable:

- log line;
- stack trace;
- metric;
- trace;
- timestamp;
- service;
- request/run ID.

AI interpretation is separate:

- classification;
- hypothesis;
- root cause;
- confidence/uncertainty;
- proposed remediation;
- decision;
- outcome.

## Incident correlation

One root incident may produce many symptoms. Correlation should identify causal chains and avoid treating every downstream failure as an independent incident.

## RCA verification

The RCA verifier receives evidence and attempts to disprove the proposed cause. Alternatives and conflicting evidence are preserved.

## Objectives and constraints

Incident response explicitly defines the objective. During outage the optimum may be rapid safe restoration; during maintenance the optimum may be a durable architectural fix.

## Recovery decision

Possible outcomes include automatic approved runbook, human approval required, blocked, emergency stop, or no action.

## Runbook safety

Autonomous recovery may invoke only:

- approved;
- versioned;
- auditable;
- parameter-validated;
- permission-scoped runbooks.

It may not improvise arbitrary production shell commands.

High-risk examples requiring human/policy gates include destructive DB operations, migrations, customer-data deletion, security-policy changes, arbitrary code merge/deploy and unapproved shell execution.

## Recovery verification

A successful command is not sufficient. Verify service health, queue progress, data consistency, disappearance of the error and customer-visible behavior.

## Postmortem and knowledge

Verified incidents should produce structured records of impact, symptoms, root cause, evidence, failed attempts, successful recovery, permanent fix, prevention, tests/runbook updates and final outcome.

## Trend/Regression intelligence

Separate roles may detect repeating patterns, workload-linked failures, post-release regressions and degradation in agent/model quality over longer time windows.

## Initial role set

- Log Intake / Normalization
- Error Classification
- Incident Correlation
- Root Cause Analysis
- RCA Verifier
- Remediation
- Incident Objectives & Constraints
- Recovery Decision
- Recovery
- Recovery Verifier
- Regression Detection
- Pattern / Trend
- Postmortem
- Operational Learning
- Operational Quality Auditor / Meta-Auditor

This role set may expand without kernel redesign.
