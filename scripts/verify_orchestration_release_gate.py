from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verification_common import CheckResult, all_ok, print_results

REPO_ROOT = SCRIPT_DIR.parent
BACKEND_ROOT = REPO_ROOT / "python-backend"
GATE_VERSION = "2026-04-22.1"

RELEASE_GATE_SUITES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "orchestration invariant guards",
        (
            "python-backend/tests/test_orchestration_invariant_guards.py",
        ),
    ),
    (
        "dispatch registry enforcement",
        (
            "python-backend/tests/test_dispatch_registry_enforcement.py",
        ),
    ),
    (
        "rehearsal scenarios",
        (
            "python-backend/tests/test_rehearsal_scenarios.py",
        ),
    ),
    (
        "critical flow integration",
        (
            "python-backend/tests/test_quote_recalculation_command_orchestrator.py",
            "python-backend/tests/test_quote_recalculation_rules_coverage_audit.py",
            "python-backend/tests/test_estimates_recalculate_route.py",
            "python-backend/tests/test_quote_recalculation_jobs.py",
            "python-backend/tests/test_case_workflow_transition_planning.py",
            "python-backend/tests/test_case_transition_effects.py",
        ),
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the orchestration release gate bundle. "
            "This freezes the current orchestration kernel contract before release."
        )
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used for pytest subprocesses (default: current interpreter)",
    )
    parser.add_argument(
        "--backend-root",
        default=str(BACKEND_ROOT),
        help="Path to python-backend directory (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Timeout in seconds for each pytest suite (default: %(default)s)",
    )
    return parser


def run_orchestration_release_gate(
    *,
    python_executable: str,
    backend_root: Path,
    timeout: int,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    for suite_name, suite_paths in RELEASE_GATE_SUITES:
        results.append(
            _run_pytest_suite(
                suite_name=suite_name,
                suite_paths=suite_paths,
                python_executable=python_executable,
                backend_root=backend_root,
                timeout=timeout,
            )
        )
    return results


def _run_pytest_suite(
    *,
    suite_name: str,
    suite_paths: tuple[str, ...],
    python_executable: str,
    backend_root: Path,
    timeout: int,
) -> CheckResult:
    command = [python_executable, "-m", "pytest", *suite_paths]
    try:
        completed = subprocess.run(
            command,
            cwd=str(backend_root.parent),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(suite_name, False, f"timed out after {timeout}s")
    except Exception as exc:
        return CheckResult(suite_name, False, f"{type(exc).__name__}: {exc}")

    if completed.returncode == 0:
        return CheckResult(suite_name, True)

    detail = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    )
    return CheckResult(suite_name, False, detail or f"exit code {completed.returncode}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"Gate version: {GATE_VERSION}")
    results = run_orchestration_release_gate(
        python_executable=args.python_executable,
        backend_root=Path(args.backend_root).resolve(),
        timeout=args.timeout,
    )
    print_results(results, title="Orchestration release gate")
    return 0 if all_ok(results) else 1


if __name__ == "__main__":
    sys.exit(main())
