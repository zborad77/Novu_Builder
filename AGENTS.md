# NOVU Builder — Codex Operating Rules

<!-- novusion-development-hygiene:start -->
## Development hygiene (MANDATORY)

Follow the Novusion Development Hygiene skill, `.claude/skills/novusion-development-hygiene/SKILL.md`, in every task. Its mandatory core:

- **One project = one repository = one working directory.** Git worktrees, second checkouts and copies of a project are forbidden, whatever the reason; versions only via branches, commits and tags. Before switching a branch, keep every uncommitted change safe.
- **Never create anything outside the repository you work in** - no file, folder, script, log, cache, scratchpad, staging, backup or copy; nothing in `J:\tmp`, `J:\temp`, on other drives or in the user profile. Helper scripts and test data go into the repository's `test/`, build work into `build/`. A tool that writes TEMP outside: point its TEMP/TMP inside the project; if that is impossible, stop and report - never create an alternative workspace.
- **One `build/`, one `test/` (test sources in `tests/`), one `build.bat` entry point, one `dist/`** (`patch/`, `runtime/`, `release/`, `previous/`). No `build_core`, `build_new`, `build_cuda13`, numbered or timestamped folders, no second build script. A repository's established deviation named in its own `CLAUDE.md` / `AGENTS.md` is used until the owner agrees a plan - never added to.
- **Every folder exists exactly once;** no loose logs or notes in the repository root.
- **Retention:** `dist/release/` Release 1 only, `dist/patch/` at most 3, `dist/previous/` at most 3; never remove the patch baseline or a rollback target.
- **Start of the task:** check the repository, `git status`, `build/`, `test/`, `build.bat`, parallel build folders and free disk space; say in a line what you found. A violation found is recorded, never added to.
- **End of the task:** remove your own leftovers, check that no new folder appeared outside the structure, check `git status` and the size; report it.
- **Never delete automatically:** source, uncommitted changes, databases, user data, active builds or test environments, other agents' work, Release 1, the latest 3 releases, unknown files. Cleanup beyond your own leftovers: tag with the NovuExplorer `Delete` badge - the owner deletes.
- **Houdini / Unreal:** one project folder / one `.uproject` and one `Content/`; never copy a project; final assets, maps, Blueprints, plugins and approved simulations are protected.
- Applies to every technology: C++, Qt, Python, .NET, web, Houdini, Unreal and the rest.
<!-- novusion-development-hygiene:end -->

<!-- novusion-authorship-standard:start -->
## Authorship (MANDATORY)

Follow the Novusion Technology Authorship Standard skill, `.claude/skills/novusion-authorship-standard/SKILL.md`, in every task. Its mandatory core:

- **The author is Pavel Dostál, Novusion** (https://novusion.com, info@novusion.com).
- **Every new source file starts with the Novusion standard header**, exactly this, in its language's comment syntax (`#` lines for Python, PowerShell, CMake; `rem` for batch; `<!-- -->` for HTML/XML):

```
/*
 * Copyright (c) 2026 Novusion
 * Website: https://novusion.com
 * Contact: info@novusion.com
 *
 * Author: Pavel Dostál
 * Project: [Project Name]
 * Module: [Module Name]
 * Description: [Brief description]
 * Created: [YYYY-MM-DD]
 */
```

  `Created` is the day the file was created and never changes. Existing files keep their own headers - never rewrite historical information; vendored code keeps its own licence.
- **Claude or any other AI is never named as author, co-author or creator** - not in code, comments, metadata, UI, file names, documentation, package manifests or commit messages (no `Co-Authored-By:` AI lines, no "Generated with" lines).
- Binary assets (Unreal assets, geometry, textures) and JSON files need no header; their source code, scripts and shaders do.
- Before finishing a task: check the new files have the header, Novusion and Pavel Dostál are named correctly, and no AI is named as an author.
<!-- novusion-authorship-standard:end -->

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
