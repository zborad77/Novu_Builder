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
PROCESSING_READY_PATH = "/api/v1/ready/processing"
EXPECTED_HEALTH = {"status": "ok", "service": "python-backend"}
EXPECTED_READY = {"status": "ready", "service": "python-backend"}
EXPECTED_NOT_READY = {"status": "not_ready", "service": "python-backend"}
ACCEPTED_PROCESSING_QUEUE_STATES = {"ready", "degraded"}


def run_probe_verification(
    *,
    base_url: str,
    timeout: int,
    require_ready: bool,
    require_processing_ready: bool,
    allow_processing_grace: bool,
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

    if not require_processing_ready:
        results.append(CheckResult("processing readiness probe skipped by operator request", True))
        return results

    strict_suffix = "" if allow_processing_grace else "?strict=1"
    processing_status, processing_body = request_json_or_text(
        "GET",
        f"{base}{PROCESSING_READY_PATH}{strict_suffix}",
        timeout=timeout,
    )
    processing_http_ok = processing_status in (200, 503)
    results.append(
        CheckResult(
            "processing readiness endpoint returns HTTP 200 or 503",
            processing_http_ok,
            f"status={processing_status}" if not processing_http_ok else "",
        )
    )

    expected_processing_ready = {
        "status": "ready" if not allow_processing_grace else "ready",
        "service": "python-backend",
        "apiReady": True,
        "jobProcessingReady": True,
        "workerState": "ready",
        "graceActive": False,
        "strict": not allow_processing_grace,
    }
    expected_processing_grace = {
        "status": "warming_up",
        "service": "python-backend",
        "apiReady": True,
        "jobProcessingReady": True,
        "workerState": "missing",
        "queueState": "ready",
        "graceActive": True,
        "strict": False,
    }

    if processing_status == 200:
        expected_body = expected_processing_grace if allow_processing_grace else expected_processing_ready
        if isinstance(processing_body, dict) and not allow_processing_grace:
            queue_state = processing_body.get("queueState")
            queue_state_ok = queue_state in ACCEPTED_PROCESSING_QUEUE_STATES
            processing_body_ok = (
                queue_state_ok
                and {key: processing_body.get(key) for key in expected_processing_ready} == expected_processing_ready
            )
            results.append(
                CheckResult(
                    "processing readiness queue state is ready or degraded",
                    queue_state_ok,
                    repr(queue_state) if not queue_state_ok else "",
                )
            )
            results.append(
                CheckResult(
                    "processing readiness payload is correct",
                    processing_body_ok,
                    repr(processing_body) if not processing_body_ok else "",
                )
            )
            return results
        results.append(
            CheckResult(
                "processing readiness payload is correct",
                processing_body == expected_body,
                repr(processing_body) if processing_body != expected_body else "",
            )
        )
    elif processing_status == 503:
        results.append(
            CheckResult(
                "job-based processing path is ready when required",
                False,
                f"processing readiness returned 503: {processing_body!r}",
            )
        )
    else:
        results.append(
            CheckResult(
                "processing readiness payload could be validated",
                False,
                f"unexpected processing readiness response: status={processing_status} body={processing_body!r}",
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
    parser.add_argument(
        "--skip-processing-ready",
        action="store_true",
        help="Skip the background-job processing readiness probe.",
    )
    parser.add_argument(
        "--allow-processing-grace",
        action="store_true",
        help="Accept warming_up during worker grace instead of requiring strict processing readiness.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = run_probe_verification(
        base_url=args.base_url,
        timeout=args.timeout,
        require_ready=not args.allow_not_ready,
        require_processing_ready=not args.skip_processing_ready,
        allow_processing_grace=args.allow_processing_grace,
    )
    print_results(results, title="HTTP probe verification")
    return 0 if all_ok(results) else 1


if __name__ == "__main__":
    sys.exit(main())
