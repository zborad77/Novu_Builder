"""
Runner — executes backend check scripts in order and prints a summary.

Checks (in order):
  1. test-env.py              — required environment variables
  2. test-db-connection.py    — database TCP connectivity
  3. test-redis-connection.py — Redis TCP connectivity (SKIP if REDIS_URL not set)
  4. test-backend-startup.py  — HTTP health endpoint + JSON validation
  5. test-api-contracts.py    — HTTP contract smoke test
  6. test-import-startup.py   — backend import + create_app() check

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
import threading
from pathlib import Path

CHECK_TIMEOUT = 15  # seconds per check

SCRIPTS_DIR = Path(__file__).parent

# Scripts that accept --url; others receive no extra args.
URL_SCRIPTS = {"test-backend-startup.py", "test-api-contracts.py"}

CHECKS = [
    "test-env.py",
    "test-db-connection.py",
    "test-redis-connection.py",
    "test-backend-startup.py",
    "test-api-contracts.py",
    "test-import-startup.py",
]


def run_check(script: Path, extra_args: list) -> tuple[str, str]:
    """
    Run a single check script and return (status, detail).

    status: 'OK', 'SKIP', or 'FAIL'
    detail: '' for normal results, 'timeout {CHECK_TIMEOUT}s' on timeout

    SKIP is detected by exit code 0 + first output line starting with 'SKIP'.
    Output is streamed to stdout in real time via a reader thread so that
    proc.wait(timeout=...) can enforce the per-check deadline.
    """
    proc = subprocess.Popen(
        [sys.executable, str(script)] + extra_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    first_line: list[str | None] = [None]

    def _read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            if first_line[0] is None:
                first_line[0] = line.strip()

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()

    try:
        proc.wait(timeout=CHECK_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        reader.join(timeout=2)
        print(f"\n  [TIMEOUT: check exceeded {CHECK_TIMEOUT}s — process killed]", flush=True)
        return "FAIL", f"timeout {CHECK_TIMEOUT}s"

    reader.join()

    if proc.returncode != 0:
        return "FAIL", ""
    if first_line[0] is not None and first_line[0].upper().startswith("SKIP"):
        return "SKIP", ""
    return "OK", ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all backend health and diagnostic checks")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Backend base URL (default: %(default)s)",
    )
    args = parser.parse_args()

    results: list[tuple[str, str]] = []

    for script_name in CHECKS:
        script = SCRIPTS_DIR / script_name
        extra_args = ["--url", args.url] if script_name in URL_SCRIPTS else []

        label = script_name.replace("test-", "").replace(".py", "")
        print(f"\n{'─' * 42}", flush=True)
        print(f"  CHECK  {label}", flush=True)
        print(f"{'─' * 42}", flush=True)

        status, detail = run_check(script, extra_args)
        results.append((label, status, detail))

    # Summary
    print(f"\n{'═' * 42}")
    print("  SUMMARY")
    print(f"{'═' * 42}")

    any_failed = False
    for name, status, detail in results:
        marker = "✓" if status == "OK" else ("~" if status == "SKIP" else "✗")
        suffix = f"  [{detail}]" if detail else ""
        print(f"  {marker}  {status:<4}  {name}{suffix}")
        if status == "FAIL":
            any_failed = True

    print(f"{'═' * 42}")
    if any_failed:
        print("  RESULT: FAIL")
        sys.exit(1)
    else:
        print("  RESULT: OK")


if __name__ == "__main__":
    main()
