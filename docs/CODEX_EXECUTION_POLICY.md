# NOVU Builder — Codex Execution Policy

## 1. Purpose

This document defines the default execution model for Codex work in
NOVU Builder.

The goal is:

- maximum useful execution;
- minimum unnecessary handoffs;
- evidence-driven conclusions;
- strict repository and release safety.

Prefer completing one coherent engineering objective end-to-end instead
of splitting it into many artificial micro-tasks.

A normal substantial mission may include:

evidence / diagnosis
→ implementation
→ targeted tests
→ one targeted pre-commit review
→ commit
→ push
→ pull request
→ CI / Repo Guard
→ merge when authorized and gates pass
→ post-merge CI
→ runtime or deployment rehearsal where applicable
→ final evidence report

Codex should normally progress through these phases autonomously when
the task already authorizes them.

## 2. Fundamental rule

**AUTONOMY DOES NOT MEAN ASSUMPTION.**

Every material conclusion must be supported by at least one appropriate
form of actual evidence, such as:

- repository state;
- exact branch and commit SHA;
- inspected source;
- executed command output;
- test result;
- CI result;
- GitHub state;
- runtime evidence;
- deployment evidence.

If evidence is missing, obtain it.

Never infer PASS from:

- intent;
- documentation alone;
- expected behavior;
- an earlier unrelated test;
- an unexecuted command;
- a simulated result.

Never fabricate output.

## 3. Mission sizing

Prefer one coherent engineering mission when multiple steps serve the
same final objective.

Examples of work that normally belongs in one mission:

- diagnose a defect;
- implement the evidenced fix;
- add regression protection;
- run targeted tests;
- review the diff once;
- commit;
- open a PR;
- wait for CI;
- correct in-scope failures;
- merge when authorized and gates pass;
- verify the exact merged SHA;
- run the relevant runtime rehearsal.

Do not return to the user merely because one routine intermediate phase
finished when the next safe action is already defined by the task.

Do not combine unrelated engineering objectives into one mission.

## 4. Scope discipline

Every substantial task must establish, explicitly or from clear task
context:

- repository;
- baseline branch;
- baseline SHA where relevant;
- engineering objective;
- authorized files or subsystems;
- prohibited areas;
- acceptance criteria.

Do not perform a general repository audit unless explicitly requested.

Standard behavior:

> Do not perform a general repository audit.
> Inspect only files and dependencies necessary for this task.
> Do not search for unrelated improvements.

Do not turn a focused bug fix into opportunistic cleanup or refactoring.

## 5. Evidence before change

When the cause of a problem is not already proven:

1. reproduce or inspect the failure;
2. capture relevant evidence;
3. distinguish fact from hypothesis;
4. identify the smallest supported cause;
5. only then implement the fix.

Do not modify code merely because a cause seems likely.

When runtime evidence is available, prefer it over speculation.

## 6. Best-effort maximum execution

Do not stop the whole mission at the first independent failure.

For every planned phase:

### EXECUTED

If it can be executed safely, execute it.

Record what was actually done and the result.

### BLOCKED

If the phase cannot run because of an environment or external limitation,
mark:

`BLOCKED — <exact reason>`

Record:

- command or action attempted;
- execution environment;
- actual output/error;
- affected phase.

Then continue all other independent safe work.

### NOT RUN

If a phase depends on a blocked or failed prerequisite, mark:

`NOT RUN — DEPENDS ON <phase>`

Then continue unrelated independent work.

### FAILED

If an actually executed phase demonstrates a project defect, mark it
FAILED with exact evidence.

Continue independent phases when safe.

Stop the entire mission only when continuing would be unsafe,
destructive, based on a wrong/untrusted baseline, or technically
impossible.

## 7. Autonomous in-scope corrections

A newly discovered problem may be fixed autonomously when all of the
following are true:

- the problem is evidenced;
- it directly blocks or affects the current engineering objective;
- the fix remains inside the authorized scope;
- the change is reasonably reversible;
- appropriate regression verification can be added or executed;
- required CI/runtime gates can be rerun.

After an in-scope correction, continue the mission.

Do not request routine user confirmation between these phases.

## 8. Mandatory escalation boundary

Do not silently expand the mission when resolution requires a material
change involving:

- database schema or a new migration;
- security or authorization model;
- architecture ownership or boundaries;
- dependency/platform replacement;
- storage architecture redesign;
- destructive operation with uncertain isolation;
- new external paid service;
- product behavior decision;
- another milestone such as M2;
- release policy change.

Unless explicitly authorized, record the finding and leave that part
unresolved.

Do not guess.

## 9. Implementation discipline

Implement the smallest complete fix supported by evidence.

Avoid:

- unrelated refactoring;
- speculative future-proofing;
- duplicate abstractions;
- temporary bypasses that weaken production behavior;
- disabling safety checks to make tests pass;
- changing tests merely to accommodate incorrect behavior.

Preserve existing architecture and contracts unless the task explicitly
authorizes changing them.

## 10. Verification layers

Use verification appropriate to the change.

### Layer 1 — targeted verification

Run the tests/checks directly relevant to the modified behavior.

### Layer 2 — repository verification

For substantial changes, use the repository's normal gates:

- targeted tests;
- appropriate full test suite;
- lint;
- repository guards;
- PR CI.

### Layer 3 — pre-commit review

Perform one targeted review before commit.

Inspect:

- diff;
- changed-file boundary;
- unintended changes;
- acceptance criteria;
- security/release invariants relevant to the task.

Prefer one meaningful review over repeated broad audits.

### Layer 4 — merge verification

When the task authorizes merge:

- merge only after required gates pass;
- record the exact merge commit;
- verify the destination branch points to the expected result;
- wait for required post-merge/push CI on that exact SHA.

Do not treat PR CI on the pre-merge SHA as proof of post-merge branch
state when repository policy requires a final push run.

### Layer 5 — runtime verification

For runtime, deployment, integration, backup/restore, networking, SSE,
worker, infrastructure, or release-critical changes, execute real
runtime verification where the environment supports it.

Static configuration validation alone is not equivalent to runtime
acceptance.

## 11. CI failure handling

If CI fails:

1. inspect the exact failed job/step;
2. determine whether the failure is caused by the current change;
3. distinguish harness/environment failure from project failure;
4. if the correction remains inside scope, fix it and rerun;
5. do not restart with a general audit.

Do not weaken gates merely to obtain green CI.

## 12. Runtime rehearsal rules

For production-like rehearsal:

- execute real commands;
- use disposable resources;
- do not use production credentials or production data;
- capture relevant logs before cleanup;
- preserve failure evidence;
- do not report staging acceptance from a local or CI rehearsal;
- cleanup must run even after failure.

A rehearsal PASS means only what was actually exercised.

Do not claim untested properties.

## 13. Failure evidence

For a failed executed phase, report at minimum:

- phase;
- exact command/action;
- environment;
- exit status where available;
- relevant error;
- affected component;
- logs or runtime evidence where relevant.

Do not replace missing evidence with a diagnosis.

If the precise root cause is unknown, state that it is unknown.

## 14. Git discipline

Before editing, establish the baseline.

Before commit:

- inspect `git status`;
- inspect the diff;
- verify changed-file scope;
- run `git diff --check` where appropriate.

Do not modify tracked files merely to work around environment
limitations.

Do not commit temporary evidence, credentials, generated secrets, or
disposable rehearsal files.

## 15. Pull request discipline

PRs should describe:

- evidenced problem;
- implemented fix;
- exact scope;
- regression protection;
- important non-changes;
- relevant validation.

Do not overstate what was proven.

## 16. Release discipline

For release-critical work:

- distinguish technical automated acceptance from staging acceptance;
- do not create a release/tag before required release gates;
- never move an already-published release tag;
- preserve exact commit identity;
- runtime/rehearsal evidence must correspond to the stated commit.

For NOVU Builder, M2 must not be entered merely because unrelated M1 or
release work completed. Respect the current milestone lock state.

## 17. Audits

Do not default to repeated broad audits.

Use an audit when it is itself the objective or at a genuine decision
gate, such as:

- major release acceptance;
- security boundary change;
- migration strategy change;
- architecture milestone;
- explicit independent review;
- concrete reason to distrust repository state.

For normal implementation work, prefer targeted inspection and tests.

## 18. Final reporting

Final reports must distinguish clearly:

- EXECUTED;
- PASS;
- FAILED;
- BLOCKED;
- NOT RUN.

Include exact SHAs, PRs, CI runs, runtime evidence, or other identifiers
when they materially establish the result.

Do not describe planned work as completed work.

Do not report a task as fully complete while a required acceptance
criterion remains unverified.

## 19. Operating principle

The preferred NOVU Builder Codex workflow is:

**broad objective + narrow guardrails + strong evidence + autonomous execution**

not:

**small prompt + handoff + small prompt + handoff**

and not:

**broad objective + unrestricted improvisation**

The target is to complete as much correct work as safely possible in one
coherent mission while preserving strict evidence and release safety.
