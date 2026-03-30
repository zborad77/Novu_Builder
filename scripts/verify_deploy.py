from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verification_common import CheckResult, all_ok, print_results
from verify_auth_smoke import run_auth_verification
from verify_core_api_smoke import run_core_api_verification
from verify_http_probes import run_probe_verification

DEFAULT_BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://localhost:8000")
DEFAULT_TIMEOUT = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a practical post-deploy verification bundle for liveness/readiness and optional auth smoke."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Backend base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--allow-not-ready",
        action="store_true",
        help="Accept readiness 503/not_ready instead of failing the bundle.",
    )
    parser.add_argument(
        "--auth-email",
        default=os.environ.get("SMOKE_EMAIL", ""),
        help="Optional auth smoke email (or SMOKE_EMAIL).",
    )
    parser.add_argument(
        "--auth-password",
        default=os.environ.get("SMOKE_PASSWORD", ""),
        help="Optional auth smoke password (or SMOKE_PASSWORD).",
    )
    parser.add_argument(
        "--require-auth",
        action="store_true",
        help="Fail if auth credentials are missing instead of skipping the auth smoke step.",
    )
    parser.add_argument(
        "--skip-auth",
        action="store_true",
        help="Skip the auth smoke step even when credentials are available.",
    )
    parser.add_argument(
        "--skip-api-smoke",
        action="store_true",
        help="Skip the authenticated core API smoke even when credentials are available.",
    )
    return parser


def run_deploy_verification(
    *,
    base_url: str,
    timeout: int,
    allow_not_ready: bool,
    auth_email: str,
    auth_password: str,
    require_auth: bool,
    skip_auth: bool,
    skip_api_smoke: bool,
) -> list[CheckResult]:
    results: list[CheckResult] = []

    probe_results = run_probe_verification(
        base_url=base_url,
        timeout=timeout,
        require_ready=not allow_not_ready,
    )
    results.extend(probe_results)

    if not all_ok(probe_results):
        return results

    if skip_auth:
        results.append(CheckResult("auth smoke skipped by operator request", True))
        results.append(CheckResult("core API smoke skipped because auth smoke was skipped", True))
        return results

    if auth_email and auth_password:
        auth_results = run_auth_verification(
            base_url=base_url,
            email=auth_email,
            password=auth_password,
            timeout=timeout,
        )
        results.extend(auth_results)
        if all_ok(auth_results):
            if skip_api_smoke:
                results.append(CheckResult("core API smoke skipped by operator request", True))
            else:
                results.extend(
                    run_core_api_verification(
                        base_url=base_url,
                        email=auth_email,
                        password=auth_password,
                        timeout=timeout,
                    )
                )
        return results

    if require_auth:
        results.append(
            CheckResult(
                "auth smoke credentials were provided",
                False,
                "missing --auth-email/--auth-password (or SMOKE_EMAIL / SMOKE_PASSWORD)",
            )
        )
        return results

    results.append(CheckResult("auth smoke skipped because credentials were not provided", True))
    results.append(CheckResult("core API smoke skipped because credentials were not provided", True))
    return results


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = run_deploy_verification(
        base_url=args.base_url,
        timeout=args.timeout,
        allow_not_ready=args.allow_not_ready,
        auth_email=args.auth_email,
        auth_password=args.auth_password,
        require_auth=args.require_auth,
        skip_auth=args.skip_auth,
        skip_api_smoke=args.skip_api_smoke,
    )
    print_results(results, title="Deployment verification")
    return 0 if all_ok(results) else 1


if __name__ == "__main__":
    sys.exit(main())
