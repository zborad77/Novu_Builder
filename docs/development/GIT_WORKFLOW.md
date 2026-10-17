# Git Workflow

Git history must be reviewable, logical, and reproducible.

## Commit Rules

- Use small logical commits.
- Do not mix unrelated concerns.
- Do not commit with failing tests.
- Do not commit without reviewed diff.
- Do not commit without checking `git status`.
- Use Conventional Commits.

## Suggested Commit Split

- `feat(ai): ...`
- `fix(test): ...`
- `docs(ai): ...`
- `chore(release): ...`

## Commit Hygiene

Separate production changes from test stabilization and documentation changes when practical. Do not hide risk by combining unrelated architecture, bugfix, and formatting changes in one commit.
