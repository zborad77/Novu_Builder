#!/usr/bin/env bash
# CI gate: verify no .env files with real secrets are tracked in the repo.
# Usage: bash scripts/ci-check-no-secrets.sh
# Exit 0 = clean. Exit 1 = violation found.

set -euo pipefail

FAIL=0

# ── 1. No real .env files tracked ───────────────────────────────────────────
TRACKED_ENV=$(git ls-files | grep -E "(^|\/).env(\.|$)" | grep -v "\.example$" || true)

if [[ -n "$TRACKED_ENV" ]]; then
  echo "[ci-check] FAIL: tracked .env file(s) found:"
  echo "$TRACKED_ENV" | sed 's/^/  /'
  FAIL=1
fi

# ── 2. No real secret values in tracked .example files ──────────────────────
# .example files must contain only placeholders, never real values.
EXAMPLE_FILES=$(git ls-files | grep "\.env.*\.example$" || true)

if [[ -n "$EXAMPLE_FILES" ]]; then
  SUSPECT=$(git grep -lE \
    'sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9]|:[A-Za-z0-9_]{16,}@[a-z]' \
    -- $EXAMPLE_FILES 2>/dev/null || true)

  if [[ -n "$SUSPECT" ]]; then
    echo "[ci-check] FAIL: possible real secret in .example file(s):"
    echo "$SUSPECT" | sed 's/^/  /'
    FAIL=1
  fi
fi

# ── 3. Verify gitignore covers .env ─────────────────────────────────────────
if ! git check-ignore -q python-backend/.env.production 2>/dev/null; then
  echo "[ci-check] FAIL: python-backend/.env.production is NOT covered by .gitignore"
  FAIL=1
fi

if [[ $FAIL -eq 0 ]]; then
  echo "[ci-check] OK: no secrets or real env files tracked"
fi

exit $FAIL
