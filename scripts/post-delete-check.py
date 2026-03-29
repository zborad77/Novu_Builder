#!/usr/bin/env python3
"""Post-cleanup smoke check — verifies stale references are gone and backend is alive.

Checks:
  1. No "novu-react" references remain in tracked source files
  2. No port "5173" (novu-react dev server) references remain in tracked source files
  3. GET /health returns 200

Usage:
    python scripts/post-delete-check.py [BASE_URL]

Defaults:
    BASE_URL = http://localhost:8000

Exit code: 0 if all checks pass, 1 if any check fails.

NOTE: Not integrated into CI — run manually after cleanup operations.
"""
import os
import sys
import json
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SMOKE_BASE_URL", "http://localhost:8000")).rstrip("/")

# Root of the repository (two levels up from scripts/)
REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories to skip when scanning for stale references
_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_tmp"}

# File extensions to scan (binary files excluded)
_SCAN_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md",
    ".yml", ".yaml", ".env", ".example", ".txt", ".ps1", ".sh",
    ".cpp", ".h", ".cmake", ".toml", ".cfg", ".ini",
}

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}  →  {detail}")
    return condition


def _scan_for_pattern(pattern: str) -> list[tuple[Path, int, str]]:
    """Return (file, line_number, line_content) for every occurrence of *pattern*."""
    hits: list[tuple[Path, int, str]] = []
    pattern_lower = pattern.lower()
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(skip in path.parts for skip in _SKIP_DIRS):
            continue
        if path.suffix.lower() not in _SCAN_EXTENSIONS:
            continue
        # Skip this script itself
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if pattern_lower in line.lower():
                    hits.append((path.relative_to(REPO_ROOT), i, line.strip()))
        except OSError:
            pass
    return hits


def _get_health() -> tuple[int, object]:
    url = f"{BASE_URL}/api/v1/health"
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw.decode(errors="replace")
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def run_checks() -> None:
    print(f"\nNovu Builder — post-delete smoke check\nRepo: {REPO_ROOT}\n")

    # ── 1. Stale reference: novu-react ────────────────────────────────────────
    print("── Stale reference scan ─────────────────────────────────────────────")
    hits = _scan_for_pattern("novu-react")
    if hits:
        detail = "; ".join(f"{f}:{n}" for f, n, _ in hits[:5])
        check("No 'novu-react' references in source", False, f"{len(hits)} hit(s): {detail}")
        for path, lineno, content in hits:
            print(f"       {path}:{lineno}  {content[:80]}")
    else:
        check("No 'novu-react' references in source", True)

    # ── 2. Stale reference: port 5173 ─────────────────────────────────────────
    hits = _scan_for_pattern("5173")
    if hits:
        detail = "; ".join(f"{f}:{n}" for f, n, _ in hits[:5])
        check("No '5173' port references in source", False, f"{len(hits)} hit(s): {detail}")
        for path, lineno, content in hits:
            print(f"       {path}:{lineno}  {content[:80]}")
    else:
        check("No '5173' port references in source", True)

    # ── 3. Backend health ─────────────────────────────────────────────────────
    print("── Backend health ───────────────────────────────────────────────────")
    status, body = _get_health()
    check(
        f"GET {BASE_URL}/api/v1/health returns 200",
        status == 200,
        f"status={status}, body={str(body)[:120]}",
    )
    if status == 200 and isinstance(body, dict):
        check(
            "/health status is ok or degraded",
            body.get("status") in ("ok", "degraded"),
            str(body),
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    total = _passed + _failed
    print(f"\n{'─' * 68}")
    print(f"Results: {_passed}/{total} passed", end="")
    if _failed:
        print(f", {_failed} FAILED")
    else:
        print(" — all checks passed")
    print()


if __name__ == "__main__":
    run_checks()
    sys.exit(0 if _failed == 0 else 1)
