"""R-38: Prometheus metrics - unit and integration tests."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


_METRICS_URL = "/api/v1/metrics"
_ALIVE_URL = "/api/v1/alive"
_METRICS_TOKEN = "test-scrape-secret"


def _metrics_auth_headers(token: str = _METRICS_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _metric_value(body: str, metric_name: str, labels: dict[str, str] | None = None) -> float | None:
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        if labels is None:
            if line.startswith(f"{metric_name} "):
                return float(line.rsplit(" ", 1)[1])
            continue

        if not line.startswith(f"{metric_name}{{"):
            continue
        if all(f'{key}="{value}"' in line for key, value in labels.items()):
            return float(line.rsplit(" ", 1)[1])
    return None


@pytest.fixture(autouse=True)
def _reset_metrics_state():
    from app.api.routes.system import (
        _clear_operational_metrics_cache,
        _clear_readiness_db_cache,
        _clear_readiness_storage_cache,
    )
    from app.core import metrics as metrics_module
    from app.main import app as fastapi_app

    _clear_operational_metrics_cache(fastapi_app)
    _clear_readiness_db_cache(fastapi_app)
    _clear_readiness_storage_cache(fastapi_app)

    with metrics_module._JOB_DURATION_LOCK:
        metrics_module._JOB_DURATION_WINDOW.clear()
        metrics_module._JOB_OUTCOME_COUNTS["completed"] = 0
        metrics_module._JOB_OUTCOME_COUNTS["failed"] = 0
        metrics_module._JOB_FAIL_RATE_CURRENT = 0.0
        metrics_module._JOB_DURATION_AVG_CURRENT = 0.0
        metrics_module._JOB_DURATION_P95_CURRENT = 0.0

    metrics_module.DB_ALIVE.set(0)
    metrics_module.WORKER_ALIVE.set(0)
    metrics_module.WORKER_ALIVE_INSTANCES.set(0)
    metrics_module.WORKER_SEEN_INSTANCES.set(0)
    metrics_module.WORKER_MONITORING_AVAILABLE.set(0)
    metrics_module.JOBS_QUEUED.set(0)
    metrics_module.JOBS_RUNNING.set(0)
    metrics_module.QUEUE_LENGTH.set(0)
    metrics_module.PROCESSING_JOBS.set(0)
    metrics_module.JOB_STUCK_MAX_AGE_SECONDS.set(0)
    metrics_module.JOB_FAIL_RATE.set(0)
    metrics_module.JOB_DURATION_SECONDS_AVG.set(0)
    metrics_module.JOB_DURATION_SECONDS_P95.set(0)
    metrics_module.CACHE_REQUESTS_TOTAL.labels(
        namespace="test_reset",
        operation="noop",
        outcome="noop",
    ).inc(0)
    metrics_module.WORK_CATALOG_VALIDATION_FAILURES_TOTAL.labels(
        operation="test_reset",
        reason="noop",
    ).inc(0)
    metrics_module.WORK_CATALOG_RESOLUTION_DURATION_SECONDS.labels(
        path="test_reset",
        outcome="noop",
    ).observe(0)

    yield

    _clear_operational_metrics_cache(fastapi_app)
    _clear_readiness_db_cache(fastapi_app)
    _clear_readiness_storage_cache(fastapi_app)


@pytest.fixture(autouse=True)
def _enforce_metrics_auth():
    from app.core.config import get_settings

    previous_enabled = os.environ.get("METRICS_AUTH_ENABLED")
    previous_token = os.environ.get("METRICS_AUTH_TOKEN")
    os.environ["METRICS_AUTH_ENABLED"] = "true"
    os.environ["METRICS_AUTH_TOKEN"] = _METRICS_TOKEN
    get_settings.cache_clear()
    try:
        yield
    finally:
        if previous_enabled is None:
            os.environ.pop("METRICS_AUTH_ENABLED", None)
        else:
            os.environ["METRICS_AUTH_ENABLED"] = previous_enabled
        if previous_token is None:
            os.environ.pop("METRICS_AUTH_TOKEN", None)
        else:
            os.environ["METRICS_AUTH_TOKEN"] = previous_token
        get_settings.cache_clear()


class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_200(self, app_client):
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_content_type_is_prometheus(self, app_client):
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert "text/plain" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_metrics_body_contains_expected_metric_names(self, app_client):
        await app_client.get(_ALIVE_URL)
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        body = resp.text
        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body
        assert "http_requests_in_progress" in body
        assert "novu_queue_length" in body
        assert "novu_processing_jobs" in body
        assert "novu_job_duration_seconds_avg" in body
        assert "novu_job_duration_seconds_p95" in body
        assert "novu_job_fail_rate" in body
        assert "novu_reaper_requeues_total" in body
        assert "novu_duplicate_prevented_count_total" in body
        assert "novu_cache_requests_total" in body
        assert "novu_work_catalog_resolution_duration_seconds" in body
        assert "novu_work_catalog_resolution_input_rows" in body
        assert "novu_work_catalog_validation_failures_total" in body

    @pytest.mark.asyncio
    async def test_alive_request_appears_in_metrics(self, app_client):
        await app_client.get(_ALIVE_URL)
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert "/alive" in resp.text


class TestMetricsModule:
    def test_metrics_module_defines_expected_objects(self):
        from app.core.metrics import (
            AUTH_FAILURES_TOTAL,
            DB_ALIVE,
            DUPLICATE_PREVENTED_COUNT,
            HTTP_REQUEST_DURATION_SECONDS,
            HTTP_REQUESTS_IN_PROGRESS,
            HTTP_REQUESTS_TOTAL,
            JOB_DURATION_SECONDS,
            JOB_DURATION_SECONDS_AVG,
            JOB_DURATION_SECONDS_P95,
            JOB_FAIL_RATE,
            JOB_STUCK_MAX_AGE_SECONDS,
            JOBS_QUEUED,
            JOBS_RUNNING,
            PROCESSING_JOBS,
            QUEUE_LENGTH,
            REAPER_REQUEUES_TOTAL,
            UPLOAD_REJECTIONS_TOTAL,
            WORKER_ALIVE,
        )

        assert HTTP_REQUESTS_TOTAL is not None
        assert HTTP_REQUEST_DURATION_SECONDS is not None
        assert HTTP_REQUESTS_IN_PROGRESS is not None
        assert AUTH_FAILURES_TOTAL is not None
        assert UPLOAD_REJECTIONS_TOTAL is not None
        assert DB_ALIVE is not None
        assert WORKER_ALIVE is not None
        assert JOBS_QUEUED is not None
        assert JOBS_RUNNING is not None
        assert QUEUE_LENGTH is not None
        assert PROCESSING_JOBS is not None
        assert JOB_STUCK_MAX_AGE_SECONDS is not None
        assert JOB_DURATION_SECONDS is not None
        assert JOB_DURATION_SECONDS_AVG is not None
        assert JOB_DURATION_SECONDS_P95 is not None
        assert JOB_FAIL_RATE is not None
        assert REAPER_REQUEUES_TOTAL is not None
        assert DUPLICATE_PREVENTED_COUNT is not None

    def test_counter_has_correct_labels(self):
        from app.core.metrics import HTTP_REQUESTS_TOTAL

        labels = HTTP_REQUESTS_TOTAL._labelnames
        assert "method" in labels
        assert "path_template" in labels
        assert "status_code" in labels

    def test_histogram_has_correct_labels(self):
        from app.core.metrics import HTTP_REQUEST_DURATION_SECONDS, JOB_DURATION_SECONDS

        assert "method" in HTTP_REQUEST_DURATION_SECONDS._labelnames
        assert "path_template" in HTTP_REQUEST_DURATION_SECONDS._labelnames
        assert "status_code" in HTTP_REQUEST_DURATION_SECONDS._labelnames
        assert JOB_DURATION_SECONDS._labelnames == ("status",)

    def test_operational_metric_names(self):
        from app.core.metrics import (
            DB_ALIVE,
            DUPLICATE_PREVENTED_COUNT,
            JOB_DURATION_SECONDS,
            JOB_DURATION_SECONDS_AVG,
            JOB_DURATION_SECONDS_P95,
            JOB_FAIL_RATE,
            JOB_STUCK_MAX_AGE_SECONDS,
            JOBS_QUEUED,
            JOBS_RUNNING,
            PROCESSING_JOBS,
            QUEUE_LENGTH,
            REAPER_REQUEUES_TOTAL,
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
        assert QUEUE_LENGTH._name == "novu_queue_length"
        assert PROCESSING_JOBS._name == "novu_processing_jobs"
        assert JOB_STUCK_MAX_AGE_SECONDS._name == "novu_job_stuck_max_age_seconds"
        assert JOB_DURATION_SECONDS._name == "novu_job_duration_seconds"
        assert JOB_DURATION_SECONDS_AVG._name == "novu_job_duration_seconds_avg"
        assert JOB_DURATION_SECONDS_P95._name == "novu_job_duration_seconds_p95"
        assert JOB_FAIL_RATE._name == "novu_job_fail_rate"
        assert REAPER_REQUEUES_TOTAL._name == "novu_reaper_requeues"
        assert DUPLICATE_PREVENTED_COUNT._name == "novu_duplicate_prevented_count"

    def test_failure_counter_names(self):
        from app.core.metrics import AUTH_FAILURES_TOTAL, UPLOAD_REJECTIONS_TOTAL

        assert AUTH_FAILURES_TOTAL._name == "novu_auth_failures"
        assert UPLOAD_REJECTIONS_TOTAL._name == "novu_upload_rejections"


class TestOperationalMetricsExported:
    @pytest.mark.asyncio
    async def test_metrics_body_contains_operational_gauge_names(self, app_client):
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        body = resp.text
        assert "novu_db_alive" in body
        assert "novu_worker_alive" in body
        assert "novu_worker_alive_instances" in body
        assert "novu_worker_seen_instances" in body
        assert "novu_worker_monitoring_available" in body
        assert "novu_jobs_queued" in body
        assert "novu_jobs_running" in body
        assert "novu_queue_length" in body
        assert "novu_processing_jobs" in body
        assert "novu_job_stuck_max_age_seconds" in body

    @pytest.mark.asyncio
    async def test_db_alive_gauge_is_1_after_scrape(self, app_client):
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert resp.status_code == 200
        assert "novu_db_alive 1.0" in resp.text

    @pytest.mark.asyncio
    async def test_job_observability_metrics_are_exported(self, app_client):
        from app.core.metrics import (
            observe_job_outcome,
            record_duplicate_prevented,
            record_reaper_requeues,
        )

        baseline = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        baseline_requeues = _metric_value(baseline.text, "novu_reaper_requeues_total") or 0.0
        baseline_duplicates = (
            _metric_value(
                baseline.text,
                "novu_duplicate_prevented_count_total",
                {"reason": "test_guard"},
            )
            or 0.0
        )

        observe_job_outcome(status="completed", duration_seconds=4.0)
        observe_job_outcome(status="failed", duration_seconds=10.0)
        record_reaper_requeues(2)
        record_duplicate_prevented("test_guard")

        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert _metric_value(resp.text, "novu_job_fail_rate") == pytest.approx(0.5)
        assert _metric_value(resp.text, "novu_job_duration_seconds_avg") == pytest.approx(7.0)
        assert _metric_value(resp.text, "novu_job_duration_seconds_p95") == pytest.approx(10.0)
        assert (
            _metric_value(resp.text, "novu_job_outcomes_total", {"status": "completed"}) or 0.0
        ) >= 1.0
        assert (
            _metric_value(resp.text, "novu_job_outcomes_total", {"status": "failed"}) or 0.0
        ) >= 1.0
        assert (_metric_value(resp.text, "novu_reaper_requeues_total") or 0.0) >= baseline_requeues + 2.0
        assert (
            _metric_value(
                resp.text,
                "novu_duplicate_prevented_count_total",
                {"reason": "test_guard"},
            )
            or 0.0
        ) >= baseline_duplicates + 1.0

    @pytest.mark.asyncio
    async def test_metrics_headers_disable_caching_and_indexing(self, app_client):
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert resp.headers["cache-control"] == "no-store"
        assert resp.headers["x-robots-tag"] == "noindex, nofollow"

    @pytest.mark.asyncio
    async def test_failed_login_increments_auth_failure_counter(self, app_client):
        await app_client.post("/api/v1/auth/login", json={"email": "manager_a@test.local", "password": "wrong-pass"})
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert 'novu_auth_failures_total{endpoint="login",reason="invalid_credentials"}' in resp.text

    @pytest.mark.asyncio
    async def test_upload_rejection_counter_is_exported(self, app_client):
        from app.core.metrics import UPLOAD_REJECTIONS_TOTAL

        UPLOAD_REJECTIONS_TOTAL.labels(reason="invalid_upload", status_code="400").inc()
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert 'novu_upload_rejections_total{reason="invalid_upload",status_code="400"}' in resp.text

    @pytest.mark.asyncio
    async def test_work_catalog_cache_and_validation_metrics_are_exported(self, app_client):
        from app.core.metrics import (
            observe_cache_operation,
            observe_work_catalog_resolution_input,
            observe_work_catalog_resolution,
            record_work_catalog_validation_failure,
        )

        observe_cache_operation(
            namespace="work-catalog",
            operation="get",
            outcome="hit",
            duration_seconds=0.002,
        )
        observe_work_catalog_resolution(
            path="work_catalog.get_effective_work_type",
            outcome="success",
            duration_seconds=0.01,
        )
        observe_work_catalog_resolution_input(
            path="tenant_work_type_resolution.batch_inputs",
            kind="work_types",
            count=4,
        )
        record_work_catalog_validation_failure(
            operation="work_catalog.upsert_tenant_setting",
            reason="invalid_effective_configuration",
        )

        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert 'novu_cache_requests_total{namespace="work-catalog",operation="get",outcome="hit"}' in resp.text
        assert "novu_work_catalog_resolution_input_rows_bucket" in resp.text
        assert 'path="tenant_work_type_resolution.batch_inputs"' in resp.text
        assert 'kind="work_types"' in resp.text
        assert (
            'novu_work_catalog_validation_failures_total{operation="work_catalog.upsert_tenant_setting",reason="invalid_effective_configuration"}'
            in resp.text
        )
        assert "novu_work_catalog_resolution_duration_seconds_bucket" in resp.text
        assert 'path="work_catalog.get_effective_work_type"' in resp.text
        assert 'outcome="success"' in resp.text

    @pytest.mark.asyncio
    async def test_operational_metrics_cache_hits_within_ttl(self):
        from app.api.routes.system import (
            _WorkerHeartbeatSnapshot,
            _get_operational_metrics_snapshot_cached,
        )

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(job_queue=object())))
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=False)
        worker_snapshot = _WorkerHeartbeatSnapshot(
            alive=False,
            last_seen_at=None,
            alive_instances=0,
            seen_instances=0,
        )
        query_counts = AsyncMock(return_value=(2, 3, 45.0))
        queue_counts = AsyncMock(return_value=(7, 1))

        with (
            patch("app.api.routes.system.AsyncSessionFactory", return_value=session_ctx),
            patch("app.api.routes.system._query_job_counts", new=query_counts),
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=queue_counts),
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
        assert first.queue_length == 7
        assert first.processing_jobs == 1
        assert first.job_stuck_max_age_seconds == pytest.approx(45.0)
        assert second == first
        assert query_counts.await_count == 1
        assert queue_counts.await_count == 1

    @pytest.mark.asyncio
    async def test_operational_metrics_cache_refreshes_after_ttl_expiry(self):
        from app.api.routes.system import (
            _WorkerHeartbeatSnapshot,
            _get_operational_metrics_snapshot_cached,
        )

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(job_queue=object())))
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(return_value=session)
        session_ctx.__aexit__ = AsyncMock(return_value=False)
        worker_snapshot = _WorkerHeartbeatSnapshot(
            alive=True,
            last_seen_at="2026-03-30T00:00:00+00:00",
            alive_instances=1,
            seen_instances=1,
        )
        query_counts = AsyncMock(side_effect=[(1, 4, 30.0), (5, 6, 120.0)])
        queue_counts = AsyncMock(side_effect=[(2, 1), (9, 3)])

        with (
            patch("app.api.routes.system.AsyncSessionFactory", return_value=session_ctx),
            patch("app.api.routes.system._query_job_counts", new=query_counts),
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=queue_counts),
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
        assert first.queue_length == 2
        assert first.processing_jobs == 1
        assert first.job_stuck_max_age_seconds == pytest.approx(30.0)
        assert second.jobs_running == 5
        assert second.jobs_queued == 6
        assert second.queue_length == 9
        assert second.processing_jobs == 3
        assert second.job_stuck_max_age_seconds == pytest.approx(120.0)
        assert query_counts.await_count == 2
        assert queue_counts.await_count == 2


class TestMetricsAuthGuard:
    """R-SEC-01: Bearer token guard on /metrics (METRICS_AUTH_ENABLED=true)."""

    @pytest.mark.asyncio
    async def test_no_token_returns_401_when_guard_enabled(self, app_client):
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL)
            assert resp.status_code == 401
        finally:
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_wrong_token_returns_401(self, app_client):
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL, headers={"Authorization": "Bearer wrong-token"})
            assert resp.status_code == 401
        finally:
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_correct_token_returns_200(self, app_client):
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
            assert resp.status_code == 200
            assert "text/plain" in resp.headers["content-type"]
        finally:
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_no_token_configured_returns_401(self, app_client):
        os.environ["METRICS_AUTH_ENABLED"] = "true"
        os.environ.pop("METRICS_AUTH_TOKEN", None)
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL, headers={"Authorization": "Bearer anything"})
            assert resp.status_code == 401
        finally:
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_guard_disabled_returns_503(self, app_client):
        os.environ["METRICS_AUTH_ENABLED"] = "false"
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL)
            assert resp.status_code == 503
        finally:
            get_settings.cache_clear()


class TestMetricsIpAllowlist:
    """R-SEC-02: IP allowlist enforcement on /metrics (active whenever METRICS_IP_ALLOWLIST is set)."""

    @pytest.mark.asyncio
    async def test_non_allowlisted_ip_returns_403(self, app_client):
        # testclient connects from 127.0.0.1 which is not in 10.0.0.0/8
        os.environ["METRICS_IP_ALLOWLIST"] = "10.0.0.0/8"
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
            assert resp.status_code == 403
        finally:
            os.environ.pop("METRICS_IP_ALLOWLIST", None)
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_allowlisted_ip_passes_through_to_auth(self, app_client):
        # 127.0.0.1 (testclient) is in 127.0.0.0/8 → IP passes, auth succeeds
        os.environ["METRICS_IP_ALLOWLIST"] = "127.0.0.0/8"
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
            assert resp.status_code == 200
        finally:
            os.environ.pop("METRICS_IP_ALLOWLIST", None)
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_allowlisted_ip_wrong_token_still_returns_401(self, app_client):
        # IP passes allowlist but token is wrong → 401
        os.environ["METRICS_IP_ALLOWLIST"] = "127.0.0.0/8"
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL, headers={"Authorization": "Bearer wrong"})
            assert resp.status_code == 401
        finally:
            os.environ.pop("METRICS_IP_ALLOWLIST", None)
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_empty_allowlist_skips_ip_check(self, app_client):
        """No METRICS_IP_ALLOWLIST set → IP check is skipped, only auth matters."""
        os.environ.pop("METRICS_IP_ALLOWLIST", None)
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
            assert resp.status_code == 200
        finally:
            get_settings.cache_clear()

    def test_invalid_cidr_rejected_at_startup(self, monkeypatch):
        from app.core.config import Settings
        from pydantic import ValidationError

        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("METRICS_AUTH_ENABLED", "false")
        monkeypatch.setenv("METRICS_IP_ALLOWLIST", "not-a-valid-cidr")
        with pytest.raises(ValidationError, match="invalid IP/CIDR"):
            Settings()
