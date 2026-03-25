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
import json
import argparse
import subprocess
import threading
import time
from pathlib import Path

CHECK_TIMEOUT = 15  # seconds per check

RETRY_SCRIPTS = {"test-db-connection.py", "test-redis-connection.py"}
RETRY_MAX = 3       # total attempts (1 initial + 2 retries)
RETRY_DELAY = 1     # seconds between attempts

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

    Exit code convention:
      0 → OK
      1 → FAIL
      2 → SKIP

    detail: '' for normal results, 'timeout {CHECK_TIMEOUT}s' on timeout.
    Output is streamed to stdout in real time via a reader thread so that
    proc.wait(timeout=...) can enforce the per-check deadline.
    """
    proc = subprocess.Popen(
        [sys.executable, str(script)] + extra_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    def _read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)

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

    if proc.returncode == 2:
        return "SKIP", ""
    if proc.returncode != 0:
        return "FAIL", ""
    return "OK", ""


def run_check_with_retry(script: Path, extra_args: list, max_attempts: int) -> tuple[str, str]:
    """
    Wrap run_check with up to max_attempts total attempts.

    Retry only on FAIL or timeout; SKIP stops immediately (no retry).
    detail reflects attempt count when more than one attempt was needed.
    """
    for attempt in range(1, max_attempts + 1):
        status, detail = run_check(script, extra_args)
        if status != "FAIL":
            # OK or SKIP — done, no retry needed
            if attempt > 1:
                detail = f"ok on attempt {attempt}/{max_attempts}"
            return status, detail
        if attempt < max_attempts:
            print(f"  [retry {attempt}/{max_attempts - 1}: waiting {RETRY_DELAY}s ...]", flush=True)
            time.sleep(RETRY_DELAY)

    # All attempts exhausted
    detail_parts = [detail] if detail else []
    detail_parts.append(f"failed after {max_attempts} attempts")
    return "FAIL", ", ".join(detail_parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all backend health and diagnostic checks")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Backend base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable text",
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

        if script_name in RETRY_SCRIPTS:
            status, detail = run_check_with_retry(script, extra_args, RETRY_MAX)
        else:
            status, detail = run_check(script, extra_args)
        results.append((label, status, detail))

    any_failed = any(status == "FAIL" for _, status, _ in results)
    overall = "FAIL" if any_failed else "OK"

    if args.json:
        payload = {
            "result": overall,
            "checks": [
                {"name": name, "status": status, **({"detail": detail} if detail else {})}
                for name, status, detail in results
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        # Default human-readable summary — unchanged
        print(f"\n{'═' * 42}")
        print("  SUMMARY")
        print(f"{'═' * 42}")
        for name, status, detail in results:
            marker = "✓" if status == "OK" else ("~" if status == "SKIP" else "✗")
            suffix = f"  [{detail}]" if detail else ""
            print(f"  {marker}  {status:<4}  {name}{suffix}")
        print(f"{'═' * 42}")
        print(f"  RESULT: {overall}")

    if any_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
