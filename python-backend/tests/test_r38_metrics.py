"""R-38: Prometheus metrics — unit and integration tests.

Tests cover:
  - /metrics endpoint returns 200 with Prometheus text content type
  - HTTP request counter increments after a request
  - Metrics module defines the three expected metric names
  - Bearer token auth guard (R-SEC-01): enabled/disabled/wrong token/no token
"""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


_METRICS_URL = "/api/v1/metrics"
_ALIVE_URL = "/api/v1/alive"


@pytest.fixture(autouse=True)
def _reset_operational_metrics_cache():
    from app.api.routes.system import _clear_operational_metrics_cache, _clear_readiness_db_cache
    from app.main import app as fastapi_app

    _clear_operational_metrics_cache(fastapi_app)
    _clear_readiness_db_cache(fastapi_app)
    yield
    _clear_operational_metrics_cache(fastapi_app)
    _clear_readiness_db_cache(fastapi_app)


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
            AUTH_FAILURES_TOTAL,
            HTTP_REQUEST_DURATION_SECONDS,
            HTTP_REQUESTS_IN_PROGRESS,
            HTTP_REQUESTS_TOTAL,
            UPLOAD_REJECTIONS_TOTAL,
        )
        assert HTTP_REQUESTS_TOTAL is not None
        assert HTTP_REQUEST_DURATION_SECONDS is not None
        assert HTTP_REQUESTS_IN_PROGRESS is not None
        assert AUTH_FAILURES_TOTAL is not None
        assert UPLOAD_REJECTIONS_TOTAL is not None

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

    def test_operational_gauges_defined(self):
        from app.core.metrics import (
            DB_ALIVE,
            JOBS_QUEUED,
            JOBS_RUNNING,
            WORKER_ALIVE,
            WORKER_ALIVE_INSTANCES,
            WORKER_MONITORING_AVAILABLE,
            WORKER_SEEN_INSTANCES,
        )
        assert DB_ALIVE is not None
        assert WORKER_ALIVE is not None
        assert WORKER_ALIVE_INSTANCES is not None
        assert WORKER_SEEN_INSTANCES is not None
        assert WORKER_MONITORING_AVAILABLE is not None
        assert JOBS_QUEUED is not None
        assert JOBS_RUNNING is not None

    def test_operational_gauge_names(self):
        from app.core.metrics import (
            DB_ALIVE,
            JOBS_QUEUED,
            JOBS_RUNNING,
            WORKER_ALIVE,
            WORKER_ALIVE_INSTANCES,
            WORKER_MONITORING_AVAILABLE,
            WORKER_SEEN_INSTANCES,
        )
        assert DB_ALIVE._name == "novu_db_alive"
        assert WORKER_ALIVE._name == "novu_worker_alive"
        assert WORKER_ALIVE_INSTANCES._name == "novu_worker_alive_instances"
        assert WORKER_SEEN_INSTANCES._name == "novu_worker_seen_instances"
        assert WORKER_MONITORING_AVAILABLE._name == "novu_worker_monitoring_available"
        assert JOBS_QUEUED._name == "novu_jobs_queued"
        assert JOBS_RUNNING._name == "novu_jobs_running"

    def test_failure_counter_names(self):
        from app.core.metrics import AUTH_FAILURES_TOTAL, UPLOAD_REJECTIONS_TOTAL
        assert AUTH_FAILURES_TOTAL._name == "novu_auth_failures"
        assert UPLOAD_REJECTIONS_TOTAL._name == "novu_upload_rejections"


class TestOperationalMetricsExported:

    @pytest.mark.asyncio
    async def test_metrics_body_contains_operational_gauge_names(self, app_client):
        resp = await app_client.get(_METRICS_URL)
        body = resp.text
        assert "novu_db_alive" in body
        assert "novu_worker_alive" in body
        assert "novu_worker_alive_instances" in body
        assert "novu_worker_seen_instances" in body
        assert "novu_worker_monitoring_available" in body
        assert "novu_jobs_queued" in body
        assert "novu_jobs_running" in body

    @pytest.mark.asyncio
    async def test_db_alive_gauge_is_1_after_scrape(self, app_client):
        """After a successful scrape the DB gauge must reflect a live DB."""
        resp = await app_client.get(_METRICS_URL)
        assert resp.status_code == 200
        # The test DB is always available so novu_db_alive should be 1.0
        assert "novu_db_alive 1.0" in resp.text

    @pytest.mark.asyncio
    async def test_metrics_headers_disable_caching_and_indexing(self, app_client):
        resp = await app_client.get(_METRICS_URL)
        assert resp.headers["cache-control"] == "no-store"
        assert resp.headers["x-robots-tag"] == "noindex, nofollow"

    @pytest.mark.asyncio
    async def test_failed_login_increments_auth_failure_counter(self, app_client):
        await app_client.post("/api/v1/auth/login", json={"email": "manager_a@test.local", "password": "wrong-pass"})
        resp = await app_client.get(_METRICS_URL)
        assert 'novu_auth_failures_total{endpoint="login",reason="invalid_credentials"}' in resp.text

    @pytest.mark.asyncio
    async def test_upload_rejection_counter_is_exported(self, app_client):
        from app.core.metrics import UPLOAD_REJECTIONS_TOTAL

        UPLOAD_REJECTIONS_TOTAL.labels(reason="invalid_upload", status_code="400").inc()
        resp = await app_client.get(_METRICS_URL)
        assert 'novu_upload_rejections_total{reason="invalid_upload",status_code="400"}' in resp.text

    @pytest.mark.asyncio
    async def test_operational_metrics_cache_hits_within_ttl(self):
        from app.api.routes.system import (
            _WorkerHeartbeatSnapshot,
            _get_operational_metrics_snapshot_cached,
        )

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(job_queue=None)))
        db_result = MagicMock()
        db_result.one.return_value = (2, 3)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=db_result)
        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=False)
        worker_snapshot = _WorkerHeartbeatSnapshot(
            alive=False,
            last_seen_at=None,
            alive_instances=0,
            seen_instances=0,
        )

        with (
            patch("app.api.routes.system.AsyncSessionFactory", return_value=session_ctx),
            patch(
                "app.api.routes.system._get_worker_heartbeat_snapshot",
                new=AsyncMock(return_value=worker_snapshot),
            ),
            patch("app.api.routes.system._readiness_now", side_effect=[100.0, 100.0, 101.0, 101.0]),
        ):
            first = await _get_operational_metrics_snapshot_cached(request)
            second = await _get_operational_metrics_snapshot_cached(request)

        assert first.db_alive is True
        assert first.jobs_running == 2
        assert first.jobs_queued == 3
        assert second == first
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_operational_metrics_cache_refreshes_after_ttl_expiry(self):
        from app.api.routes.system import (
            _WorkerHeartbeatSnapshot,
            _get_operational_metrics_snapshot_cached,
        )

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(job_queue=None)))
        first_result = MagicMock()
        first_result.one.return_value = (1, 4)
        second_result = MagicMock()
        second_result.one.return_value = (5, 6)
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[first_result, second_result])
        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=False)
        worker_snapshot = _WorkerHeartbeatSnapshot(
            alive=True,
            last_seen_at="2026-03-30T00:00:00+00:00",
            alive_instances=1,
            seen_instances=1,
        )

        with (
            patch("app.api.routes.system.AsyncSessionFactory", return_value=session_ctx),
            patch(
                "app.api.routes.system._get_worker_heartbeat_snapshot",
                new=AsyncMock(return_value=worker_snapshot),
            ),
            patch(
                "app.api.routes.system._readiness_now",
                side_effect=[200.0, 200.0, 201.0, 206.0, 206.0, 207.0],
            ),
        ):
            first = await _get_operational_metrics_snapshot_cached(request)
            second = await _get_operational_metrics_snapshot_cached(request)

        assert first.jobs_running == 1
        assert first.jobs_queued == 4
        assert second.jobs_running == 5
        assert second.jobs_queued == 6
        assert session.execute.await_count == 2


class TestMetricsAuthGuard:
    """R-SEC-01: Bearer token guard on /metrics (METRICS_AUTH_ENABLED=true)."""

    @pytest.mark.asyncio
    async def test_no_token_returns_401_when_guard_enabled(self, app_client):
        os.environ["METRICS_AUTH_ENABLED"] = "true"
        os.environ["METRICS_AUTH_TOKEN"] = "test-scrape-secret"
        from app.core.config import get_settings
        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL)
            assert resp.status_code == 401
        finally:
            os.environ["METRICS_AUTH_ENABLED"] = "false"
            os.environ.pop("METRICS_AUTH_TOKEN", None)
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_wrong_token_returns_401(self, app_client):
        os.environ["METRICS_AUTH_ENABLED"] = "true"
        os.environ["METRICS_AUTH_TOKEN"] = "test-scrape-secret"
        from app.core.config import get_settings
        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL, headers={"Authorization": "Bearer wrong-token"})
            assert resp.status_code == 401
        finally:
            os.environ["METRICS_AUTH_ENABLED"] = "false"
            os.environ.pop("METRICS_AUTH_TOKEN", None)
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_correct_token_returns_200(self, app_client):
        os.environ["METRICS_AUTH_ENABLED"] = "true"
        os.environ["METRICS_AUTH_TOKEN"] = "test-scrape-secret"
        from app.core.config import get_settings
        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL, headers={"Authorization": "Bearer test-scrape-secret"})
            assert resp.status_code == 200
            assert "text/plain" in resp.headers["content-type"]
        finally:
            os.environ["METRICS_AUTH_ENABLED"] = "false"
            os.environ.pop("METRICS_AUTH_TOKEN", None)
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_no_token_configured_returns_401(self, app_client):
        """Guard enabled but no token set → fail closed (401)."""
        os.environ["METRICS_AUTH_ENABLED"] = "true"
        os.environ.pop("METRICS_AUTH_TOKEN", None)
        from app.core.config import get_settings
        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL, headers={"Authorization": "Bearer anything"})
            assert resp.status_code == 401
        finally:
            os.environ["METRICS_AUTH_ENABLED"] = "false"
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_guard_disabled_allows_unauthenticated(self, app_client):
        """METRICS_AUTH_ENABLED=false → public access (for internal-network-only setups)."""
        os.environ["METRICS_AUTH_ENABLED"] = "false"
        from app.core.config import get_settings
        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL)
            assert resp.status_code == 200
        finally:
            get_settings.cache_clear()
