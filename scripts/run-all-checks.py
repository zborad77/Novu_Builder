"""
Run all infrastructure health checks in order.

Checks (in order):
  1. test-env.py            — required environment variables
  2. test-db-connection.py  — database TCP connectivity
  3. test-redis-connection.py — Redis TCP connectivity (skipped if REDIS_URL not set)
  4. test-backend-startup.py — HTTP health endpoint + JSON validation

Exit code:
  0 — all checks passed (SKIP counts as pass)
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
    {"name": "env",             "script": "test-env.py",             "extra_args": []},
    {"name": "db-connection",   "script": "test-db-connection.py",   "extra_args": []},
    {"name": "redis-connection","script": "test-redis-connection.py", "extra_args": []},
    {"name": "backend-startup", "script": "test-backend-startup.py",  "extra_args": ["--url", "{url}"]},
]

WIDTH = 20


def run_check(name: str, script: Path, extra_args: list[str]) -> bool:
    print(f"\n{'─' * 40}")
    print(f"  CHECK: {name}")
    print(f"{'─' * 40}")
    result = subprocess.run(
        [sys.executable, str(script)] + extra_args,
        text=True,
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all infrastructure health checks")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL (default: %(default)s)")
    args = parser.parse_args()

    results: list[tuple[str, str]] = []

    for check in CHECKS:
        extra = [a.replace("{url}", args.url) for a in check["extra_args"]]
        script = SCRIPTS_DIR / check["script"]
        passed = run_check(check["name"], script, extra)
        results.append((check["name"], "OK" if passed else "FAIL"))

    print(f"\n{'═' * 40}")
    print("  SUMMARY")
    print(f"{'═' * 40}")
    any_failed = False
    for name, status in results:
        print(f"  {status:<6}  {name}")
        if status == "FAIL":
            any_failed = True
    print(f"{'═' * 40}")

    if any_failed:
        print("  RESULT: FAIL")
        sys.exit(1)
    else:
        print("  RESULT: OK")


if __name__ == "__main__":
    main()
