from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verification_common import CheckResult, all_ok, print_results
from verify_deploy import run_deploy_verification
from verify_import_startup import BACKEND_ROOT, run_fail_fast_checks, run_import_checks

DEFAULT_TIMEOUT = 15


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a safe release gate: startup preflight, optional explicit Alembic upgrade, "
            "then post-deploy verification."
        )
    )
    parser.add_argument("--base-url", required=True, help="Deployed backend base URL for post-deploy verification.")
    parser.add_argument(
        "--backend-root",
        default=str(BACKEND_ROOT),
        help="Path to python-backend directory (default: %(default)s)",
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used for subprocess checks (default: current interpreter)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Timeout in seconds for subprocess and HTTP checks (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-import-startup",
        action="store_true",
        help="Skip import/startup preflight and run only migration/deploy verification.",
    )
    parser.add_argument(
        "--skip-fail-fast",
        action="store_true",
        help="Skip representative production fail-fast settings checks inside preflight.",
    )
    parser.add_argument(
        "--apply-migrations",
        action="store_true",
        help="Actually run 'alembic upgrade head'. Without this flag, migrations are skipped on purpose.",
    )
    parser.add_argument("--auth-email", default="", help="Optional auth smoke email for post-deploy verification.")
    parser.add_argument("--auth-password", default="", help="Optional auth smoke password for post-deploy verification.")
    parser.add_argument("--require-auth", action="store_true", help="Fail if auth credentials are missing.")
    parser.add_argument("--skip-auth", action="store_true", help="Skip auth smoke and dependent API smoke.")
    parser.add_argument("--skip-api-smoke", action="store_true", help="Skip authenticated core API smoke.")
    parser.add_argument("--allow-not-ready", action="store_true", help="Accept readiness 503/not_ready.")
    parser.add_argument("--skip-processing-ready", action="store_true", help="Skip strict processing readiness verification.")
    parser.add_argument("--allow-processing-grace", action="store_true", help="Accept worker grace on processing readiness.")
    return parser


def run_release_gate(
    *,
    backend_root: Path,
    python_executable: str,
    base_url: str,
    timeout: int,
    skip_import_startup: bool,
    skip_fail_fast: bool,
    apply_migrations: bool,
    auth_email: str,
    auth_password: str,
    require_auth: bool,
    skip_auth: bool,
    skip_api_smoke: bool,
    allow_not_ready: bool,
    skip_processing_ready: bool = False,
    allow_processing_grace: bool = False,
) -> list[CheckResult]:
    results: list[CheckResult] = []

    if not skip_import_startup:
        preflight_results = run_import_checks(backend_root=backend_root)
        if not skip_fail_fast:
            preflight_results.extend(
                run_fail_fast_checks(
                    backend_root=backend_root,
                    python_executable=python_executable,
                    timeout=timeout,
                )
            )
        results.extend(preflight_results)
        if not all_ok(preflight_results):
            return results
    else:
        results.append(CheckResult("import/startup preflight skipped by operator request", True))

    if apply_migrations:
        migration_result = _run_command(
            name="alembic upgrade head",
            command=[python_executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend_root,
            timeout=timeout,
        )
        results.append(migration_result)
        if not migration_result.ok:
            return results
    else:
        results.append(CheckResult("alembic upgrade head skipped because --apply-migrations was not provided", True))

    results.extend(
        run_deploy_verification(
            base_url=base_url,
            timeout=timeout,
            allow_not_ready=allow_not_ready,
            auth_email=auth_email,
            auth_password=auth_password,
            require_auth=require_auth,
            skip_auth=skip_auth,
            skip_api_smoke=skip_api_smoke,
            skip_processing_ready=skip_processing_ready,
            allow_processing_grace=allow_processing_grace,
        )
    )
    return results


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = run_release_gate(
        backend_root=Path(args.backend_root).resolve(),
        python_executable=args.python_executable,
        base_url=args.base_url,
        timeout=args.timeout,
        skip_import_startup=args.skip_import_startup,
        skip_fail_fast=args.skip_fail_fast,
        apply_migrations=args.apply_migrations,
        auth_email=args.auth_email,
        auth_password=args.auth_password,
        require_auth=args.require_auth,
        skip_auth=args.skip_auth,
        skip_api_smoke=args.skip_api_smoke,
        allow_not_ready=args.allow_not_ready,
        skip_processing_ready=args.skip_processing_ready,
        allow_processing_grace=args.allow_processing_grace,
    )
    print_results(results, title="Release gate verification")
    return 0 if all_ok(results) else 1


def _run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    timeout: int,
) -> CheckResult:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(name, False, f"timed out after {timeout}s")
    except Exception as exc:
        return CheckResult(name, False, f"{type(exc).__name__}: {exc}")

    if completed.returncode == 0:
        return CheckResult(name, True)

    detail = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    )
    return CheckResult(name, False, detail or f"exit code {completed.returncode}")


if __name__ == "__main__":
    sys.exit(main())
