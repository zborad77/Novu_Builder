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


def run_core_api_verification(
    *,
    base_url: str,
    email: str,
    password: str,
    timeout: int,
) -> list[CheckResult]:
    base = base_url.rstrip("/")
    results: list[CheckResult] = []

    login_status, login_body = request_json_or_text(
        "POST",
        f"{base}/api/v1/auth/login",
        body={"email": email, "password": password},
        timeout=timeout,
    )
    token = str(login_body.get("accessToken") or "") if isinstance(login_body, dict) else ""
    headers = {"Authorization": f"Bearer {token}"} if token else None

    results.append(
        CheckResult(
            "core API smoke login returns HTTP 200",
            login_status == 200,
            f"status={login_status}" if login_status != 200 else "",
        )
    )
    results.append(
        CheckResult(
            "core API smoke login returns an access token",
            bool(token),
            repr(login_body) if not token else "",
        )
    )
    if not token:
        return results

    cases_status, cases_body = request_json_or_text(
        "GET",
        f"{base}/api/v1/cases",
        headers=headers,
        timeout=timeout,
    )
    cases_items = cases_body.get("items") if isinstance(cases_body, dict) else None
    results.append(
        CheckResult(
            "cases list returns HTTP 200",
            cases_status == 200,
            f"status={cases_status}" if cases_status != 200 else "",
        )
    )
    results.append(
        CheckResult(
            "cases list returns an items array",
            isinstance(cases_items, list),
            repr(cases_body) if not isinstance(cases_items, list) else "",
        )
    )

    first_case_id = None
    if isinstance(cases_items, list) and cases_items:
        first_case = cases_items[0]
        if isinstance(first_case, dict):
            first_case_id = first_case.get("id")

    if first_case_id:
        case_status, case_body = request_json_or_text(
            "GET",
            f"{base}/api/v1/cases/{first_case_id}",
            headers=headers,
            timeout=timeout,
        )
        results.append(
            CheckResult(
                "case detail returns HTTP 200 for an existing case",
                case_status == 200,
                f"status={case_status}" if case_status != 200 else "",
            )
        )
        results.append(
            CheckResult(
                "case detail matches the requested id",
                isinstance(case_body, dict) and case_body.get("id") == first_case_id,
                repr(case_body) if not (isinstance(case_body, dict) and case_body.get("id") == first_case_id) else "",
            )
        )
    else:
        results.append(CheckResult("case detail smoke skipped because no cases exist", True))

    for path, name in (
        ("/api/v1/pricebooks", "pricebooks list"),
        ("/api/v1/material-catalog", "material catalog list"),
    ):
        status_code, body = request_json_or_text(
            "GET",
            f"{base}{path}",
            headers=headers,
            timeout=timeout,
        )
        items = body.get("items") if isinstance(body, dict) else None
        results.append(
            CheckResult(
                f"{name} returns HTTP 200",
                status_code == 200,
                f"status={status_code}" if status_code != 200 else "",
            )
        )
        results.append(
            CheckResult(
                f"{name} returns an items array",
                isinstance(items, list),
                repr(body) if not isinstance(items, list) else "",
            )
        )

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a minimal authenticated read-only API bundle for core tenant-scoped endpoints."
    )
    parser.add_argument(
        "--base-url",
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
        print("SKIP: core API smoke requires both --email and --password (or SMOKE_EMAIL / SMOKE_PASSWORD).")
        return 2

    results = run_core_api_verification(
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        timeout=args.timeout,
    )
    print_results(results, title="Core API smoke verification")
    return 0 if all_ok(results) else 1


if __name__ == "__main__":
    sys.exit(main())
