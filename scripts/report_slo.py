from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
BACKEND_ROOT = REPO_ROOT / "python-backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.slo import (  # noqa: E402
    API_AVAILABILITY_SLO,
    API_LATENCY_P95_SLO,
    API_LATENCY_P99_SLO,
    AUTH_PLATFORM_SUCCESS_SLO,
    JOB_COMPLETION_SUCCESS_SLO,
    error_budget_consumed_ratio,
    error_budget_remaining_ratio,
)

DEFAULT_PROMETHEUS_URL = "http://127.0.0.1:9090"
DEFAULT_WINDOW = "30d"
DEFAULT_JOB = "novu-backend"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _public_api_matchers(job: str) -> str:
    return (
        f'job="{job}",'
        'path_template!~"/api/v1/(health|ready|ready/processing|health/internal|metrics|alive)"'
    )


def _public_api_non_5xx_matchers(job: str) -> str:
    return _public_api_matchers(job) + ',status_code!~"5.."'


def _auth_matchers(job: str) -> str:
    return f'job="{job}",path_template=~"/api/v1/auth/(login|refresh)"'


def _query_url(prometheus_url: str, query: str) -> str:
    return prometheus_url.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": query})


def _prometheus_scalar(prometheus_url: str, query: str, *, timeout: int) -> float:
    request = urllib.request.Request(_query_url(prometheus_url, query), headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    result = ((payload.get("data") or {}).get("result")) or []
    if not result:
        return 0.0
    value = result[0].get("value")
    if not isinstance(value, list) or len(value) != 2:
        raise RuntimeError(f"Unexpected Prometheus result shape: {payload}")
    return float(value[1])


def _safe_percent(value: float) -> float | None:
    if not math.isfinite(value):
        return None
    return round(value * 100.0, 4)


def _safe_ms(value_seconds: float) -> float | None:
    if not math.isfinite(value_seconds):
        return None
    return round(value_seconds * 1000.0, 1)


def _budget_summary(observed_ratio: float, objective: float) -> dict[str, float | bool | None]:
    consumed = error_budget_consumed_ratio(observed_ratio, objective=objective)
    remaining = error_budget_remaining_ratio(observed_ratio, objective=objective)
    return {
        "consumedRatio": round(consumed, 4) if math.isfinite(consumed) else None,
        "remainingRatio": round(remaining, 4) if math.isfinite(remaining) else None,
        "consumedPercentOfBudget": round(consumed * 100.0, 2) if math.isfinite(consumed) else None,
        "remainingPercentOfBudget": round(remaining * 100.0, 2) if math.isfinite(remaining) else None,
        "budgetExhausted": bool(math.isfinite(remaining) and remaining < 0.0),
    }


def build_report(*, prometheus_url: str, window: str, job: str, timeout: int) -> dict:
    public_api_matchers = _public_api_matchers(job)
    public_api_non_5xx_matchers = _public_api_non_5xx_matchers(job)
    auth_matchers = _auth_matchers(job)

    api_availability_query = (
        "1 - ("
        f'sum(increase(http_requests_total{{{public_api_matchers},status_code=~"5.."}}[{window}])) '
        f'/ clamp_min(sum(increase(http_requests_total{{{public_api_matchers}}}[{window}])), 1)'
        ")"
    )
    job_success_query = (
        f'sum(increase(novu_job_outcomes_total{{job="{job}",status="completed"}}[{window}])) '
        f'/ clamp_min(sum(increase(novu_job_outcomes_total{{job="{job}",status=~"completed|failed|dead_letter"}}[{window}])), 1)'
    )
    auth_success_query = (
        "1 - ("
        f'sum(increase(http_requests_total{{{auth_matchers},status_code=~"5.."}}[{window}])) '
        f'/ clamp_min(sum(increase(http_requests_total{{{auth_matchers}}}[{window}])), 1)'
        ")"
    )
    latency_p95_query = (
        "histogram_quantile(0.95, "
        f'sum by (le) (increase(http_request_duration_seconds_bucket{{{public_api_non_5xx_matchers}}}[{window}])))'
    )
    latency_p99_query = (
        "histogram_quantile(0.99, "
        f'sum by (le) (increase(http_request_duration_seconds_bucket{{{public_api_non_5xx_matchers}}}[{window}])))'
    )
    latency_le_1s_query = (
        f'sum(increase(http_request_duration_seconds_bucket{{{public_api_non_5xx_matchers},le="1.0"}}[{window}])) '
        f'/ clamp_min(sum(increase(http_request_duration_seconds_count{{{public_api_non_5xx_matchers}}}[{window}])), 1)'
    )
    latency_le_2s_query = (
        f'sum(increase(http_request_duration_seconds_bucket{{{public_api_non_5xx_matchers},le="2.0"}}[{window}])) '
        f'/ clamp_min(sum(increase(http_request_duration_seconds_count{{{public_api_non_5xx_matchers}}}[{window}])), 1)'
    )

    api_availability = _prometheus_scalar(prometheus_url, api_availability_query, timeout=timeout)
    job_success = _prometheus_scalar(prometheus_url, job_success_query, timeout=timeout)
    auth_success = _prometheus_scalar(prometheus_url, auth_success_query, timeout=timeout)
    latency_p95_seconds = _prometheus_scalar(prometheus_url, latency_p95_query, timeout=timeout)
    latency_p99_seconds = _prometheus_scalar(prometheus_url, latency_p99_query, timeout=timeout)
    latency_le_1s = _prometheus_scalar(prometheus_url, latency_le_1s_query, timeout=timeout)
    latency_le_2s = _prometheus_scalar(prometheus_url, latency_le_2s_query, timeout=timeout)

    return {
        "generatedAt": utc_now_iso(),
        "window": window,
        "prometheusUrl": prometheus_url,
        "job": job,
        "slos": {
            "apiAvailability": {
                "objectivePercent": 99.9,
                "observedPercent": _safe_percent(api_availability),
                "errorBudgetMinutes30d": round(API_AVAILABILITY_SLO.error_budget_minutes_30d, 1),
                "description": API_AVAILABILITY_SLO.description,
                **_budget_summary(api_availability, API_AVAILABILITY_SLO.objective),
            },
            "jobCompletionSuccessRate": {
                "objectivePercent": 99.0,
                "observedPercent": _safe_percent(job_success),
                "errorBudgetMinutes30d": round(JOB_COMPLETION_SUCCESS_SLO.error_budget_minutes_30d, 1),
                "description": JOB_COMPLETION_SUCCESS_SLO.description,
                **_budget_summary(job_success, JOB_COMPLETION_SUCCESS_SLO.objective),
            },
            "authSuccessRate": {
                "objectivePercent": 99.95,
                "observedPercent": _safe_percent(auth_success),
                "errorBudgetMinutes30d": round(AUTH_PLATFORM_SUCCESS_SLO.error_budget_minutes_30d, 1),
                "description": AUTH_PLATFORM_SUCCESS_SLO.description,
                **_budget_summary(auth_success, AUTH_PLATFORM_SUCCESS_SLO.objective),
            },
            "latencyP95": {
                "objectivePercentUnderThreshold": 95.0,
                "thresholdMs": 1000.0,
                "observedLatencyMs": _safe_ms(latency_p95_seconds),
                "observedGoodPercent": _safe_percent(latency_le_1s),
                "errorBudgetMinutes30d": round(API_LATENCY_P95_SLO.error_budget_minutes_30d, 1),
                "description": API_LATENCY_P95_SLO.description,
                **_budget_summary(latency_le_1s, API_LATENCY_P95_SLO.objective),
            },
            "latencyP99": {
                "objectivePercentUnderThreshold": 99.0,
                "thresholdMs": 2000.0,
                "observedLatencyMs": _safe_ms(latency_p99_seconds),
                "observedGoodPercent": _safe_percent(latency_le_2s),
                "errorBudgetMinutes30d": round(API_LATENCY_P99_SLO.error_budget_minutes_30d, 1),
                "description": API_LATENCY_P99_SLO.description,
                **_budget_summary(latency_le_2s, API_LATENCY_P99_SLO.objective),
            },
        },
    }


def _render_budget(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def _render_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}%"


def _render_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} ms"


def render_markdown(report: dict) -> str:
    slos = report["slos"]
    lines = [
        "# Production SLO Report",
        "",
        f"- Generated at: `{report['generatedAt']}`",
        f"- Window: `{report['window']}`",
        f"- Prometheus: `{report['prometheusUrl']}`",
        f"- Job label: `{report['job']}`",
        "",
        "| SLO | Objective | Observed | Budget Remaining | Status |",
        "| --- | --- | --- | --- | --- |",
        (
            f"| API availability | 99.9% | {_render_percent(slos['apiAvailability']['observedPercent'])} | "
            f"{_render_budget(slos['apiAvailability']['remainingPercentOfBudget'])} | "
            f"{'EXHAUSTED' if slos['apiAvailability']['budgetExhausted'] else 'OK'} |"
        ),
        (
            f"| Job completion success | 99.0% | {_render_percent(slos['jobCompletionSuccessRate']['observedPercent'])} | "
            f"{_render_budget(slos['jobCompletionSuccessRate']['remainingPercentOfBudget'])} | "
            f"{'EXHAUSTED' if slos['jobCompletionSuccessRate']['budgetExhausted'] else 'OK'} |"
        ),
        (
            f"| Auth success | 99.95% | {_render_percent(slos['authSuccessRate']['observedPercent'])} | "
            f"{_render_budget(slos['authSuccessRate']['remainingPercentOfBudget'])} | "
            f"{'EXHAUSTED' if slos['authSuccessRate']['budgetExhausted'] else 'OK'} |"
        ),
        (
            f"| API latency p95 <= 1000 ms | 95.0% under threshold | "
            f"{_render_percent(slos['latencyP95']['observedGoodPercent'])} under threshold, p95={_render_ms(slos['latencyP95']['observedLatencyMs'])} | "
            f"{_render_budget(slos['latencyP95']['remainingPercentOfBudget'])} | "
            f"{'EXHAUSTED' if slos['latencyP95']['budgetExhausted'] else 'OK'} |"
        ),
        (
            f"| API latency p99 <= 2000 ms | 99.0% under threshold | "
            f"{_render_percent(slos['latencyP99']['observedGoodPercent'])} under threshold, p99={_render_ms(slos['latencyP99']['observedLatencyMs'])} | "
            f"{_render_budget(slos['latencyP99']['remainingPercentOfBudget'])} | "
            f"{'EXHAUSTED' if slos['latencyP99']['budgetExhausted'] else 'OK'} |"
        ),
        "",
        "## Notes",
        "",
        "- Auth SLO measures platform-side reliability of login/refresh, not credential correctness.",
        "- API SLO excludes health/readiness/metrics endpoints so probes do not distort user-facing availability.",
        "- Job completion SLO excludes user-canceled jobs and counts `failed` + `dead_letter` as budget burn.",
    ]
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a production SLO report from Prometheus.")
    parser.add_argument("--prometheus-url", default=DEFAULT_PROMETHEUS_URL)
    parser.add_argument("--window", default=DEFAULT_WINDOW)
    parser.add_argument("--job", default=DEFAULT_JOB)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--markdown-out", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(
        prometheus_url=args.prometheus_url,
        window=args.window,
        job=args.job,
        timeout=args.timeout,
    )
    rendered_json = json.dumps(report, indent=2) + "\n"
    rendered_markdown = render_markdown(report)
    print(rendered_markdown, end="")

    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered_json, encoding="utf-8")

    if args.markdown_out:
        output_path = Path(args.markdown_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered_markdown, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
