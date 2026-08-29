# Prompt Library

Reusable prompts for NOVU Builder engineering workflows. Keep prompts scoped, explicit, and aligned with the NOVU Constitution.

## Read-only Audit

```text
Use NOVU Builder working mode. Perform a read-only audit. Do not edit files, do not commit, and do not change configuration. Identify current state, risks, failing tests, and whether the issue appears related to recent changes. Report root cause candidates and the smallest safe next step.
```

## Root Cause Bug Fix

```text
Use NOVU Builder working mode. First identify the root cause in concrete files and flows. Then implement the smallest safe fix, add or update regression tests that reproduce the original failure, run relevant pytest and mypy, and report changes, verification, residual risk, and verdict. Do not commit without approval.
```

## Pre-commit Review

```text
Use NOVU Builder working mode. Review git diff, verify project invariants, check for fail-open behaviour, duplicated business logic, validation bypasses, tenant isolation risks, and pricing engine violations. Run relevant tests and mypy. Do not modify files unless a clear bug is found and approval is given.
```

## Release/Tagging

```text
Use NOVU Builder working mode. Verify clean git status, reviewed diff, green tests, green mypy, correct version bump, no known fail-open behaviour, and no security bypass. Prepare Conventional Commit and SemVer tag recommendations. Do not tag or push without explicit approval.
```

## AI Safety Review

```text
Use NOVU Builder working mode. Audit AI-adjacent changes for untrusted output handling, validation boundaries, pricing separation, invented IDs, invented work_type_code, silent fallback, and fail-open behaviour. Report findings ordered by severity with file and line references.
```

## Pricing Engine Integration Planning

```text
Use NOVU Builder working mode. Plan pricing engine integration without allowing AI-generated prices or duplicated pricing logic. Identify backend source-of-truth boundaries, required validation, data flow, tests, migration concerns, and release gates. Do not implement until the plan is approved.
```
