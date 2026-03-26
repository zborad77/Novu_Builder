"""R-38: Prometheus metrics — unit and integration tests.

Tests cover:
  - /metrics endpoint returns 200 with Prometheus text content type
  - HTTP request counter increments after a request
  - Metrics module defines the three expected metric names
"""
import pytest


_METRICS_URL = "/api/v1/metrics"
_ALIVE_URL = "/api/v1/alive"


class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_200(self, app_client):
        resp = await app_client.get(_METRICS_URL)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_content_type_is_prometheus(self, app_client):
        resp = await app_client.get(_METRICS_URL)
        # Prometheus text format content type
        assert "text/plain" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_metrics_body_contains_expected_metric_names(self, app_client):
        # Trigger at least one request so counters are non-zero
        await app_client.get(_ALIVE_URL)
        resp = await app_client.get(_METRICS_URL)
        body = resp.text
        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body
        assert "http_requests_in_progress" in body

    @pytest.mark.asyncio
    async def test_alive_request_appears_in_metrics(self, app_client):
        await app_client.get(_ALIVE_URL)
        resp = await app_client.get(_METRICS_URL)
        # The /alive path template should appear in the counter output
        assert "/alive" in resp.text


class TestMetricsModule:
    def test_metrics_module_defines_all_three_objects(self):
        from app.core.metrics import (
            HTTP_REQUEST_DURATION_SECONDS,
            HTTP_REQUESTS_IN_PROGRESS,
            HTTP_REQUESTS_TOTAL,
        )
        assert HTTP_REQUESTS_TOTAL is not None
        assert HTTP_REQUEST_DURATION_SECONDS is not None
        assert HTTP_REQUESTS_IN_PROGRESS is not None

    def test_counter_has_correct_labels(self):
        from app.core.metrics import HTTP_REQUESTS_TOTAL
        # labelnames are stored as a tuple on the metric
        labels = HTTP_REQUESTS_TOTAL._labelnames
        assert "method" in labels
        assert "path_template" in labels
        assert "status_code" in labels

    def test_histogram_has_correct_labels(self):
        from app.core.metrics import HTTP_REQUEST_DURATION_SECONDS
        labels = HTTP_REQUEST_DURATION_SECONDS._labelnames
        assert "method" in labels
        assert "path_template" in labels
        assert "status_code" in labels

    def test_gauge_has_method_label(self):
        from app.core.metrics import HTTP_REQUESTS_IN_PROGRESS
        assert "method" in HTTP_REQUESTS_IN_PROGRESS._labelnames
