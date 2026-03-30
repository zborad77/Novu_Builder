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
HEALTH_PATH = "/api/v1/health"
READY_PATH = "/api/v1/ready"
EXPECTED_HEALTH = {"status": "ok", "service": "python-backend"}
EXPECTED_READY = {"status": "ready", "service": "python-backend"}
EXPECTED_NOT_READY = {"status": "not_ready", "service": "python-backend"}


def run_probe_verification(
    *,
    base_url: str,
    timeout: int,
    require_ready: bool,
) -> list[CheckResult]:
    base = base_url.rstrip("/")
    results: list[CheckResult] = []

    health_status, health_body = request_json_or_text(
        "GET",
        f"{base}{HEALTH_PATH}",
        timeout=timeout,
    )
    results.append(
        CheckResult(
            "liveness endpoint returns HTTP 200",
            health_status == 200,
            f"status={health_status}" if health_status != 200 else "",
        )
    )
    results.append(
        CheckResult(
            "liveness payload stays minimal and stable",
            health_body == EXPECTED_HEALTH,
            repr(health_body) if health_body != EXPECTED_HEALTH else "",
        )
    )

    ready_status, ready_body = request_json_or_text(
        "GET",
        f"{base}{READY_PATH}",
        timeout=timeout,
    )
    ready_http_ok = ready_status in (200, 503)
    results.append(
        CheckResult(
            "readiness endpoint returns HTTP 200 or 503",
            ready_http_ok,
            f"status={ready_status}" if not ready_http_ok else "",
        )
    )

    if ready_status == 200:
        results.append(
            CheckResult(
                "readiness ready payload is correct",
                ready_body == EXPECTED_READY,
                repr(ready_body) if ready_body != EXPECTED_READY else "",
            )
        )
    elif ready_status == 503:
        payload_ok = ready_body == EXPECTED_NOT_READY
        results.append(
            CheckResult(
                "readiness not-ready payload is correct",
                payload_ok,
                repr(ready_body) if not payload_ok else "",
            )
        )
        results.append(
            CheckResult(
                "service reports ready when readiness is required",
                not require_ready,
                "readiness returned 503/not_ready",
            )
        )
    else:
        results.append(
            CheckResult(
                "readiness payload could be validated",
                False,
                f"unexpected readiness response: status={ready_status} body={ready_body!r}",
            )
        )

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify backend liveness and readiness probes with stable status codes and payloads."
    )
    parser.add_argument(
        "--base-url",
        "--url",
        dest="base_url",
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
        help="Accept HTTP 503/not_ready on the readiness endpoint instead of failing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = run_probe_verification(
        base_url=args.base_url,
        timeout=args.timeout,
        require_ready=not args.allow_not_ready,
    )
    print_results(results, title="HTTP probe verification")
    return 0 if all_ok(results) else 1


if __name__ == "__main__":
    sys.exit(main())
