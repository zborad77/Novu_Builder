# NOVU Builder — Codex Operating Rules

For substantial repository work, read and follow:

`docs/CODEX_EXECUTION_POLICY.md`

These instructions apply repository-wide unless a more specific nested
`AGENTS.md` explicitly overrides them for its own subtree.

## Core rules

- Prefer one coherent engineering mission over many unnecessary small handoffs.
- Autonomy does not mean assumption.
- Every material conclusion must be supported by actual evidence.
- Never simulate commands, invent outputs, or report unexecuted work as PASS.
- Use best-effort maximum execution: continue independent safe work after a blocker.
- Mark dependent unexecuted work explicitly as `NOT RUN — DEPENDS ON <phase>`.
- Do not perform a general repository audit unless the task explicitly requests one.
- Inspect only files and dependencies necessary for the current engineering objective.
- Do not search for unrelated improvements.
- Do not broaden scope beyond the authorized objective.
- Prefer one targeted pre-commit review over repeated general audits.
- Runtime and release work requires real runtime evidence where applicable.
- A Codex statement alone is not sufficient evidence of correctness.
- If a newly discovered problem is evidenced, safely fixable, and remains within
  the authorized objective and scope, diagnose it, fix it, verify it, and continue.
- If resolution requires a material architecture, security, schema/migration,
  dependency/platform, destructive-operation, product-decision, or milestone
  expansion, do not guess or improvise. Record the finding and leave that part
  unresolved unless the task explicitly authorizes the expansion.

The detailed policy in `docs/CODEX_EXECUTION_POLICY.md` is mandatory for
substantial Codex work in this repository.
