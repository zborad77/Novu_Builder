from __future__ import annotations

from dataclasses import dataclass

THIRTY_DAY_MINUTES = 30 * 24 * 60


@dataclass(frozen=True)
class SloDefinition:
    key: str
    name: str
    objective: float
    description: str
    threshold_seconds: float | None = None

    @property
    def error_budget_ratio(self) -> float:
        return max(0.0, 1.0 - self.objective)

    @property
    def error_budget_minutes_30d(self) -> float:
        return self.error_budget_ratio * THIRTY_DAY_MINUTES


API_AVAILABILITY_SLO = SloDefinition(
    key="api_availability",
    name="API availability",
    objective=0.999,
    description="Public API requests outside health/metrics should avoid 5xx responses.",
)

JOB_COMPLETION_SUCCESS_SLO = SloDefinition(
    key="job_completion_success",
    name="Job completion success rate",
    objective=0.99,
    description="Terminal analysis jobs should complete successfully rather than fail or dead-letter.",
)

AUTH_PLATFORM_SUCCESS_SLO = SloDefinition(
    key="auth_platform_success",
    name="Auth success rate",
    objective=0.9995,
    description=(
        "Login and refresh should avoid platform-side 5xx failures. "
        "Invalid credentials, expired tokens, and intentional throttling are excluded from budget burn."
    ),
)

API_LATENCY_P95_SLO = SloDefinition(
    key="api_latency_p95",
    name="API latency p95",
    objective=0.95,
    description="At least 95% of public non-5xx API requests should finish within 1.0 second.",
    threshold_seconds=1.0,
)

API_LATENCY_P99_SLO = SloDefinition(
    key="api_latency_p99",
    name="API latency p99",
    objective=0.99,
    description="At least 99% of public non-5xx API requests should finish within 2.0 seconds.",
    threshold_seconds=2.0,
)

PRODUCTION_SLOS = (
    API_AVAILABILITY_SLO,
    JOB_COMPLETION_SUCCESS_SLO,
    AUTH_PLATFORM_SUCCESS_SLO,
    API_LATENCY_P95_SLO,
    API_LATENCY_P99_SLO,
)


def clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def error_budget_consumed_ratio(observed_good_ratio: float, *, objective: float) -> float:
    budget = max(0.0, 1.0 - float(objective))
    if budget == 0.0:
        return 0.0 if observed_good_ratio >= objective else 1.0
    bad_ratio = max(0.0, 1.0 - float(observed_good_ratio))
    return max(0.0, bad_ratio / budget)


def error_budget_remaining_ratio(observed_good_ratio: float, *, objective: float) -> float:
    return 1.0 - error_budget_consumed_ratio(observed_good_ratio, objective=objective)


def format_ratio_as_percent(value: float) -> str:
    return f"{clamp_ratio(value) * 100:.3f}%"
