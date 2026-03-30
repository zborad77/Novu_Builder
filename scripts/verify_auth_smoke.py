from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verification_common import CheckResult, all_ok, print_results, request_json_or_text

DEFAULT_BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://localhost:8000")
DEFAULT_TIMEOUT = 5


def run_auth_verification(
    *,
    base_url: str,
    email: str,
    password: str,
    timeout: int,
) -> list[CheckResult]:
    base = base_url.rstrip("/")
    results: list[CheckResult] = []

    no_token_status, _ = request_json_or_text(
        "GET",
        f"{base}/api/v1/auth/me",
        timeout=timeout,
    )
    results.append(
        CheckResult(
            "protected endpoint rejects missing token",
            no_token_status == 401,
            f"status={no_token_status}" if no_token_status != 401 else "",
        )
    )

    bad_token_status, _ = request_json_or_text(
        "GET",
        f"{base}/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
        timeout=timeout,
    )
    results.append(
        CheckResult(
            "protected endpoint rejects invalid token",
            bad_token_status == 401,
            f"status={bad_token_status}" if bad_token_status != 401 else "",
        )
    )

    login_status, login_body = request_json_or_text(
        "POST",
        f"{base}/api/v1/auth/login",
        body={"email": email, "password": password},
        timeout=timeout,
    )
    results.append(
        CheckResult(
            "login returns HTTP 200",
            login_status == 200,
            f"status={login_status}" if login_status != 200 else "",
        )
    )

    token = ""
    if isinstance(login_body, dict):
        token = str(login_body.get("accessToken") or "")
    results.append(
        CheckResult(
            "login returns an access token",
            bool(token),
            repr(login_body) if not token else "",
        )
    )

    me_status, me_body = request_json_or_text(
        "GET",
        f"{base}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"} if token else None,
        timeout=timeout,
    )
    results.append(
        CheckResult(
            "authenticated /auth/me returns HTTP 200",
            me_status == 200,
            f"status={me_status}" if me_status != 200 else "",
        )
    )
    results.append(
        CheckResult(
            "authenticated /auth/me matches login identity",
            isinstance(me_body, dict) and me_body.get("email") == email,
            repr(me_body) if not (isinstance(me_body, dict) and me_body.get("email") == email) else "",
        )
    )

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a minimal login + authenticated endpoint flow without modifying business data."
    )
    parser.add_argument(
        "--base-url",
        "--url",
        dest="base_url",
        default=DEFAULT_BASE_URL,
        help="Backend base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("SMOKE_EMAIL", ""),
        help="Smoke-test login email (or set SMOKE_EMAIL).",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("SMOKE_PASSWORD", ""),
        help="Smoke-test login password (or set SMOKE_PASSWORD).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds (default: %(default)s)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.email or not args.password:
        print("SKIP: auth smoke requires both --email and --password (or SMOKE_EMAIL / SMOKE_PASSWORD).")
        return 2

    results = run_auth_verification(
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        timeout=args.timeout,
    )
    print_results(results, title="Auth smoke verification")
    return 0 if all_ok(results) else 1


if __name__ == "__main__":
    sys.exit(main())
