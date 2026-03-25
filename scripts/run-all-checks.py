"""
Runner — executes all check scripts in order and prints a summary.

Checks (in order):
  1. test-env.py              — required environment variables
  2. test-db-connection.py    — database TCP connectivity
  3. test-redis-connection.py — Redis TCP connectivity (SKIP if REDIS_URL not set)
  4. test-backend-startup.py  — HTTP health endpoint + JSON validation
  5. test-api-contracts.py    — HTTP contract smoke test
  6. test-auth-validation.py  — auth (401/403) and validation (422) contracts
  7. test-business-flow.py        — create case → trigger analysis → verify result
  8. test-performance-baseline.py — p95 latency check for critical endpoints
  9. test-import-startup.py       — backend import + create_app() check

Exit code:
  0 — all checks passed or skipped
  1 — one or more checks failed

Usage:
    python scripts/run-all-checks.py
    python scripts/run-all-checks.py --url http://localhost:8000
"""

import sys
import argparse
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent

CHECKS = [
    {"name": "env",              "script": "test-env.py",              "extra_args": []},
    {"name": "db-connection",    "script": "test-db-connection.py",    "extra_args": []},
    {"name": "redis-connection", "script": "test-redis-connection.py", "extra_args": []},
    {"name": "backend-startup",  "script": "test-backend-startup.py",  "extra_args": ["--url", "{url}"]},
    {"name": "api-contracts",    "script": "test-api-contracts.py",    "extra_args": ["--url", "{url}"]},
    {"name": "auth-validation",  "script": "test-auth-validation.py",  "extra_args": ["--url", "{url}"]},
    {"name": "business-flow",       "script": "test-business-flow.py",        "extra_args": ["--url", "{url}"]},
    {"name": "performance-baseline", "script": "test-performance-baseline.py", "extra_args": ["--url", "{url}"]},
    {"name": "import-startup",       "script": "test-import-startup.py",       "extra_args": []},
]


def run_check(name: str, script: Path, extra_args: list[str]) -> str:
    """Run a single check script. Returns 'OK', 'SKIP', or 'FAIL'."""
    print(f"\n{'-' * 40}", flush=True)
    print(f"  CHECK: {name}", flush=True)
    print(f"{'-' * 40}", flush=True)
    result = subprocess.run(
        [sys.executable, str(script)] + extra_args,
        text=True,
        capture_output=False,
    )
    if result.returncode != 0:
        return "FAIL"
    return "OK"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all health and diagnostic checks")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL (default: %(default)s)")
    args = parser.parse_args()

    results: list[tuple[str, str]] = []

    for check in CHECKS:
        extra = [a.replace("{url}", args.url) for a in check["extra_args"]]
        script = SCRIPTS_DIR / check["script"]
        status = run_check(check["name"], script, extra)
        results.append((check["name"], status))

    print(f"\n{'=' * 40}")
    print("  SUMMARY")
    print(f"{'=' * 40}")
    any_failed = False
    for name, status in results:
        print(f"  {status:<6}  {name}")
        if status == "FAIL":
            any_failed = True
    print(f"{'=' * 40}")

    if any_failed:
        print("  RESULT: FAIL")
        sys.exit(1)
    else:
        print("  RESULT: OK")


if __name__ == "__main__":
    main()
