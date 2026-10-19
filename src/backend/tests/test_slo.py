import pytest

from app.core.slo import (
    API_AVAILABILITY_SLO,
    API_LATENCY_P95_SLO,
    API_LATENCY_P99_SLO,
    AUTH_PLATFORM_SUCCESS_SLO,
    JOB_COMPLETION_SUCCESS_SLO,
    PRODUCTION_SLOS,
    error_budget_consumed_ratio,
    error_budget_remaining_ratio,
    format_ratio_as_percent,
)


def test_slo_catalog_contains_expected_keys():
    keys = {item.key for item in PRODUCTION_SLOS}
    assert keys == {
        "api_availability",
        "job_completion_success",
        "auth_platform_success",
        "api_latency_p95",
        "api_latency_p99",
    }


def test_slo_error_budget_minutes_are_stable():
    assert API_AVAILABILITY_SLO.error_budget_minutes_30d == pytest.approx(43.2)
    assert JOB_COMPLETION_SUCCESS_SLO.error_budget_minutes_30d == pytest.approx(432.0)
    assert AUTH_PLATFORM_SUCCESS_SLO.error_budget_minutes_30d == pytest.approx(21.6)
    assert API_LATENCY_P95_SLO.error_budget_minutes_30d == pytest.approx(2160.0)
    assert API_LATENCY_P99_SLO.error_budget_minutes_30d == pytest.approx(432.0)


def test_error_budget_remaining_is_zero_at_objective():
    assert error_budget_remaining_ratio(0.999, objective=0.999) == pytest.approx(0.0)
    assert error_budget_consumed_ratio(0.999, objective=0.999) == pytest.approx(1.0)


def test_error_budget_remaining_is_full_with_perfect_reliability():
    assert error_budget_remaining_ratio(1.0, objective=0.999) == pytest.approx(1.0)
    assert error_budget_consumed_ratio(1.0, objective=0.999) == pytest.approx(0.0)


def test_error_budget_remaining_goes_negative_when_exhausted():
    remaining = error_budget_remaining_ratio(0.998, objective=0.999)
    consumed = error_budget_consumed_ratio(0.998, objective=0.999)
    assert remaining == -1.0
    assert consumed == 2.0


def test_format_ratio_as_percent_uses_three_decimals():
    assert format_ratio_as_percent(0.999) == "99.900%"
    assert format_ratio_as_percent(1.5) == "100.000%"
