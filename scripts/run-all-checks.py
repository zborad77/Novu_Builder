"""
Runner for backend checks.

Modes:
  1. Default live checks against a running backend URL.
  2. Local backend stability checks driven by existing pytest/script commands.

Live checks (default mode):
  1. test-env.py
  2. test-db-connection.py
  3. test-redis-connection.py
  4. test-backend-startup.py
  5. test-api-contracts.py
  6. test-auth-validation.py
  7. test-import-startup.py
  8. test-business-flow.py (optional via --include-flow)

Local backend stability checks (--backend-stability):
  1. import/startup smoke via scripts/test-import-startup.py
  2. backend smoke pytest suite
  3. Alembic chain consistency pytest suite
  4. OpenAPI contract pytest suite
  5. optional ruff / mypy via existing backend toolchain
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

CHECK_TIMEOUT = 15
FLOW_TIMEOUT = 180
PYTEST_TIMEOUT = 120
STATIC_TIMEOUT = 180

RETRY_SCRIPTS = {"test-db-connection.py", "test-redis-connection.py"}
RETRY_MAX = 3
RETRY_DELAY = 1

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
BACKEND_ROOT = REPO_ROOT / "python-backend"

URL_SCRIPTS = {
    "test-backend-startup.py",
    "test-api-contracts.py",
    "test-auth-validation.py",
    "test-business-flow.py",
}
CRED_SCRIPTS = {"test-business-flow.py"}

LIVE_CHECKS = [
    "test-env.py",
    "test-db-connection.py",
    "test-redis-connection.py",
    "test-backend-startup.py",
    "test-api-contracts.py",
    "test-auth-validation.py",
    "test-import-startup.py",
]


def _backend_python() -> str:
    candidates = [
        BACKEND_ROOT / ".venv" / "Scripts" / "python.exe",
        BACKEND_ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _extract_reason(lines: list[str], status: str) -> str:
    if status == "SKIP":
        for line in lines:
            if line.upper().startswith("SKIP:"):
                return line[5:].strip()
    elif status == "FAIL":
        for line in reversed(lines):
            if line.upper().startswith("FAIL:"):
                return line[5:].strip()
        for line in reversed(lines):
            if re.search(r"\d+/\d+ passed", line):
                return line.strip()
    return ""


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
) -> tuple[str, str]:
    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    lines: list[str] = []

    def _read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            lines.append(line.rstrip())

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        reader.join(timeout=2)
        print(f"\n  [TIMEOUT: check exceeded {timeout}s - process killed]", flush=True)
        return "FAIL", f"timeout {timeout}s"

    reader.join()

    if proc.returncode == 2:
        return "SKIP", _extract_reason(lines, "SKIP")
    if proc.returncode != 0:
        return "FAIL", _extract_reason(lines, "FAIL")
    return "OK", ""


def run_command_with_retry(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    max_attempts: int,
) -> tuple[str, str]:
    for attempt in range(1, max_attempts + 1):
        status, detail = run_command(command, cwd=cwd, timeout=timeout)
        if status != "FAIL":
            if attempt > 1:
                detail = f"ok on attempt {attempt}/{max_attempts}"
            return status, detail
        if attempt < max_attempts:
            print(f"  [retry {attempt}/{max_attempts - 1}: waiting {RETRY_DELAY}s ...]", flush=True)
            time.sleep(RETRY_DELAY)

    detail_parts = [detail] if detail else []
    detail_parts.append(f"failed after {max_attempts} attempts")
    return "FAIL", ", ".join(detail_parts)


def _print_header(label: str) -> None:
    print(f"\n{'-' * 42}", flush=True)
    print(f"  CHECK  {label}", flush=True)
    print(f"{'-' * 42}", flush=True)


def _live_tasks(args: argparse.Namespace) -> list[dict[str, object]]:
    checks = list(LIVE_CHECKS)
    if args.include_flow:
        checks.append("test-business-flow.py")

    tasks: list[dict[str, object]] = []
    for script_name in checks:
        script = SCRIPTS_DIR / script_name
        extra_args = ["--url", args.url] if script_name in URL_SCRIPTS else []
        if script_name in CRED_SCRIPTS:
            if args.email:
                extra_args += ["--email", args.email]
            if args.password:
                extra_args += ["--password", args.password]

        tasks.append(
            {
                "name": script_name.replace("test-", "").replace(".py", ""),
                "command": [sys.executable, str(script), *extra_args],
                "cwd": REPO_ROOT,
                "timeout": FLOW_TIMEOUT if script_name == "test-business-flow.py" else CHECK_TIMEOUT,
                "retry": script_name in RETRY_SCRIPTS,
            }
        )
    return tasks


def _backend_stability_tasks(args: argparse.Namespace) -> list[dict[str, object]]:
    backend_python = _backend_python()
    tasks: list[dict[str, object]] = [
        {
            "name": "backend import-startup",
            "command": [backend_python, str(SCRIPTS_DIR / "test-import-startup.py")],
            "cwd": REPO_ROOT,
            "timeout": CHECK_TIMEOUT,
            "retry": False,
        },
        {
            "name": "backend smoke",
            "command": [
                backend_python,
                "-m",
                "pytest",
                "tests/test_backend_smoke_guards.py",
                "tests/test_alembic_chain_consistency.py",
                "-q",
            ],
            "cwd": BACKEND_ROOT,
            "timeout": PYTEST_TIMEOUT,
            "retry": False,
        },
        {
            "name": "backend openapi-contract",
            "command": [
                backend_python,
                "-m",
                "pytest",
                "tests/test_cases_openapi_contract.py",
                "-q",
            ],
            "cwd": BACKEND_ROOT,
            "timeout": PYTEST_TIMEOUT,
            "retry": False,
        },
    ]

    if args.include_ruff:
        tasks.append(
            {
                "name": "backend ruff",
                "command": [backend_python, "-m", "ruff", "check", "."],
                "cwd": BACKEND_ROOT,
                "timeout": STATIC_TIMEOUT,
                "retry": False,
            }
        )

    if args.include_mypy:
        tasks.append(
            {
                "name": "backend mypy",
                "command": [backend_python, "-m", "mypy", "app"],
                "cwd": BACKEND_ROOT,
                "timeout": STATIC_TIMEOUT,
                "retry": False,
            }
        )

    return tasks


def _run_tasks(tasks: list[dict[str, object]]) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []

    for task in tasks:
        label = str(task["name"])
        _print_header(label)

        command = list(task["command"])
        cwd = Path(task["cwd"])
        timeout = int(task["timeout"])
        retry = bool(task["retry"])

        if retry:
            status, detail = run_command_with_retry(
                command,
                cwd=cwd,
                timeout=timeout,
                max_attempts=RETRY_MAX,
            )
        else:
            status, detail = run_command(command, cwd=cwd, timeout=timeout)
        results.append((label, status, detail))

    return results


def _print_summary(results: list[tuple[str, str, str]], as_json: bool) -> None:
    any_failed = any(status == "FAIL" for _, status, _ in results)
    overall = "FAIL" if any_failed else "OK"

    if as_json:
        payload = {
            "result": overall,
            "checks": [
                {"name": name, "status": status, **({"detail": detail} if detail else {})}
                for name, status, detail in results
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"\n{'=' * 42}")
        print("  SUMMARY")
        print(f"{'=' * 42}")
        for name, status, detail in results:
            marker = "OK" if status == "OK" else ("SKIP" if status == "SKIP" else "FAIL")
            suffix = f"  [{detail}]" if detail else ""
            print(f"  {marker:<4}  {name}{suffix}")
        print(f"{'=' * 42}")
        print(f"  RESULT: {overall}")

    if any_failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run backend live checks or local stability checks")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Backend base URL for live checks (default: %(default)s)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--include-flow",
        action="store_true",
        help="Also run test-business-flow.py in live mode",
    )
    parser.add_argument(
        "--email",
        default="",
        help="Test user email for --include-flow",
    )
    parser.add_argument(
        "--password",
        default="",
        help="Test user password for --include-flow",
    )
    parser.add_argument(
        "--backend-stability",
        action="store_true",
        help="Run local backend stabilization checks using existing pytest/script suites",
    )
    parser.add_argument(
        "--include-ruff",
        action="store_true",
        help="In backend stability mode, also run ruff check from python-backend",
    )
    parser.add_argument(
        "--include-mypy",
        action="store_true",
        help="In backend stability mode, also run mypy on python-backend/app",
    )
    args = parser.parse_args()

    tasks = _backend_stability_tasks(args) if args.backend_stability else _live_tasks(args)
    results = _run_tasks(tasks)
    _print_summary(results, as_json=args.json)


if __name__ == "__main__":
    main()
