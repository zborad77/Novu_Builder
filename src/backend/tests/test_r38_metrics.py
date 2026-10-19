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


def _metric_line(body: str, prefix: str) -> str | None:
    for line in body.splitlines():
        if line.startswith(prefix):
            return line
    return None


def _metric_labels_fragment(line: str) -> str | None:
    start = line.find("{")
    end = line.find("}")
    if start == -1 or end == -1 or end < start:
        return None
    return line[start + 1:end]


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

    def test_metric_label_contracts_are_exact(self):
        from app.core.metrics import (
            AUTH_FAILURES_TOTAL,
            BACKPRESSURE_REJECTIONS_TOTAL,
            CACHE_OPERATION_DURATION_SECONDS,
            CACHE_REQUESTS_TOTAL,
            DUPLICATE_PREVENTED_COUNT,
            HTTP_REQUEST_DURATION_SECONDS,
            HTTP_REQUESTS_IN_PROGRESS,
            HTTP_REQUESTS_TOTAL,
            JOB_DURATION_SECONDS,
            JOB_OUTCOMES_TOTAL,
            STORAGE_OPERATIONS_TOTAL,
            STORAGE_OPERATION_DURATION_SECONDS,
            UPLOAD_REJECTIONS_TOTAL,
            WORK_CATALOG_RESOLUTION_DURATION_SECONDS,
            WORK_CATALOG_RESOLUTION_INPUT_ROWS,
            WORK_CATALOG_VALIDATION_FAILURES_TOTAL,
            metric_label_names,
        )

        expected = {
            HTTP_REQUESTS_TOTAL: ("method", "path_template", "status_code"),
            HTTP_REQUEST_DURATION_SECONDS: ("method", "path_template", "status_code"),
            HTTP_REQUESTS_IN_PROGRESS: ("method",),
            JOB_DURATION_SECONDS: ("status", "tenant_id"),
            JOB_OUTCOMES_TOTAL: ("status", "tenant_id"),
            DUPLICATE_PREVENTED_COUNT: ("reason",),
            BACKPRESSURE_REJECTIONS_TOTAL: ("surface", "reason"),
            AUTH_FAILURES_TOTAL: ("endpoint", "reason", "tenant_id"),
            UPLOAD_REJECTIONS_TOTAL: ("reason", "status_code"),
            STORAGE_OPERATIONS_TOTAL: ("operation", "backend", "outcome"),
            STORAGE_OPERATION_DURATION_SECONDS: ("operation", "backend", "outcome"),
            CACHE_REQUESTS_TOTAL: ("namespace", "operation", "outcome"),
            CACHE_OPERATION_DURATION_SECONDS: ("namespace", "operation", "outcome"),
            WORK_CATALOG_RESOLUTION_DURATION_SECONDS: ("path", "outcome"),
            WORK_CATALOG_RESOLUTION_INPUT_ROWS: ("path", "kind"),
            WORK_CATALOG_VALIDATION_FAILURES_TOTAL: ("operation", "reason"),
        }

        for metric, label_names in expected.items():
            assert metric_label_names(metric) == label_names

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
            metric_export_name,
        )

        assert metric_export_name(DB_ALIVE) == "novu_db_alive"
        assert metric_export_name(WORKER_ALIVE) == "novu_worker_alive"
        assert metric_export_name(WORKER_ALIVE_INSTANCES) == "novu_worker_alive_instances"
        assert metric_export_name(WORKER_SEEN_INSTANCES) == "novu_worker_seen_instances"
        assert metric_export_name(WORKER_MONITORING_AVAILABLE) == "novu_worker_monitoring_available"
        assert metric_export_name(JOBS_QUEUED) == "novu_jobs_queued"
        assert metric_export_name(JOBS_RUNNING) == "novu_jobs_running"
        assert metric_export_name(QUEUE_LENGTH) == "novu_queue_length"
        assert metric_export_name(PROCESSING_JOBS) == "novu_processing_jobs"
        assert metric_export_name(JOB_STUCK_MAX_AGE_SECONDS) == "novu_job_stuck_max_age_seconds"
        assert metric_export_name(JOB_DURATION_SECONDS) == "novu_job_duration_seconds"
        assert metric_export_name(JOB_DURATION_SECONDS_AVG) == "novu_job_duration_seconds_avg"
        assert metric_export_name(JOB_DURATION_SECONDS_P95) == "novu_job_duration_seconds_p95"
        assert metric_export_name(JOB_FAIL_RATE) == "novu_job_fail_rate"
        assert metric_export_name(REAPER_REQUEUES_TOTAL) == "novu_reaper_requeues_total"
        assert metric_export_name(DUPLICATE_PREVENTED_COUNT) == "novu_duplicate_prevented_count_total"

    def test_failure_counter_names(self):
        from app.core.metrics import AUTH_FAILURES_TOTAL, UPLOAD_REJECTIONS_TOTAL, metric_export_name

        assert metric_export_name(AUTH_FAILURES_TOTAL) == "novu_auth_failures_total"
        assert metric_export_name(UPLOAD_REJECTIONS_TOTAL) == "novu_upload_rejections_total"

    def test_metric_labels_enforce_exact_label_set(self):
        from app.core.metrics import HTTP_REQUESTS_TOTAL, metric_labels

        with pytest.raises(ValueError, match="expects labels"):
            metric_labels(HTTP_REQUESTS_TOTAL, method="GET", path_template="/alive")

        with pytest.raises(ValueError, match="expects labels"):
            metric_labels(
                HTTP_REQUESTS_TOTAL,
                method="GET",
                path_template="/alive",
                status_code="200",
                extra_label="unexpected",
            )

    def test_metric_labels_normalize_keyword_order(self):
        from app.core.metrics import HTTP_REQUESTS_TOTAL, metric_labels

        labeled_metric = metric_labels(
            HTTP_REQUESTS_TOTAL,
            status_code="200",
            path_template="/api/v1/alive",
            method="GET",
        )
        assert labeled_metric is not None

    def test_normalize_tenant_metric_label_is_fail_closed(self):
        from app.core.metrics import normalize_tenant_metric_label

        assert normalize_tenant_metric_label(" tenant-a ") == "tenant-a"
        assert normalize_tenant_metric_label(None) == "unknown"
        assert normalize_tenant_metric_label("", is_superadmin_context=True) == "superadmin"


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
        job_outcomes_line = _metric_line(
            resp.text,
            'novu_job_outcomes_total{status="completed",tenant_id="unknown"}',
        )
        assert job_outcomes_line is not None

    @pytest.mark.asyncio
    async def test_job_duration_histogram_contract_is_stable_for_tenant_context(self, app_client):
        from app.core.metrics import observe_job_outcome

        observe_job_outcome(status="completed", duration_seconds=4.0, tenant_id="tenant-a")

        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        count_line = _metric_line(
            resp.text,
            'novu_job_duration_seconds_count{status="completed",tenant_id="tenant-a"}',
        )
        sum_line = _metric_line(
            resp.text,
            'novu_job_duration_seconds_sum{status="completed",tenant_id="tenant-a"}',
        )
        bucket_value = _metric_value(
            resp.text,
            "novu_job_duration_seconds_bucket",
            {"status": "completed", "tenant_id": "tenant-a", "le": "5.0"},
        )

        assert count_line is not None
        assert sum_line is not None
        assert bucket_value is not None
        assert _metric_labels_fragment(count_line) == 'status="completed",tenant_id="tenant-a"'
        assert _metric_labels_fragment(sum_line) == 'status="completed",tenant_id="tenant-a"'

    @pytest.mark.asyncio
    async def test_job_outcome_metrics_use_superadmin_tenant_label_when_explicit(self, app_client):
        from app.core.metrics import observe_job_outcome

        observe_job_outcome(
            status="completed",
            duration_seconds=1.0,
            tenant_id=None,
            is_superadmin_context=True,
        )

        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        line = _metric_line(
            resp.text,
            'novu_job_outcomes_total{status="completed",tenant_id="superadmin"}',
        )
        assert line is not None
        assert _metric_labels_fragment(line) == 'status="completed",tenant_id="superadmin"'

    @pytest.mark.asyncio
    async def test_auth_failure_metric_uses_unknown_tenant_when_context_is_missing(self, app_client):
        from app.api.routes.auth import _record_auth_failure

        _record_auth_failure("refresh", "missing_token")

        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        line = _metric_line(
            resp.text,
            'novu_auth_failures_total{endpoint="refresh",reason="missing_token",tenant_id="unknown"}',
        )
        assert line is not None
        assert _metric_labels_fragment(line) == 'endpoint="refresh",reason="missing_token",tenant_id="unknown"'

    @pytest.mark.asyncio
    async def test_auth_failure_metric_uses_explicit_tenant_and_superadmin_invariants(self, app_client):
        from app.api.routes.auth import _record_auth_failure

        _record_auth_failure(
            "change_password",
            "invalid_current_password",
            tenant_id="tenant-a",
        )
        _record_auth_failure(
            "change_password",
            "token_state_unavailable",
            tenant_id=None,
            is_superadmin_context=True,
        )

        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        tenant_line = _metric_line(
            resp.text,
            'novu_auth_failures_total{endpoint="change_password",reason="invalid_current_password",tenant_id="tenant-a"}',
        )
        superadmin_line = _metric_line(
            resp.text,
            'novu_auth_failures_total{endpoint="change_password",reason="token_state_unavailable",tenant_id="superadmin"}',
        )

        assert tenant_line is not None
        assert superadmin_line is not None
        assert _metric_labels_fragment(tenant_line) == 'endpoint="change_password",reason="invalid_current_password",tenant_id="tenant-a"'
        assert _metric_labels_fragment(superadmin_line) == 'endpoint="change_password",reason="token_state_unavailable",tenant_id="superadmin"'

    @pytest.mark.asyncio
    async def test_metrics_headers_disable_caching_and_indexing(self, app_client):
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert resp.headers["cache-control"] == "no-store"
        assert resp.headers["x-robots-tag"] == "noindex, nofollow"

    @pytest.mark.asyncio
    async def test_metrics_text_export_help_and_type_lines_are_exact(self, app_client):
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        lines = resp.text.splitlines()
        expected_lines = [
            "# HELP http_requests_total Total HTTP requests",
            "# TYPE http_requests_total counter",
            "# HELP http_request_duration_seconds HTTP request latency in seconds",
            "# TYPE http_request_duration_seconds histogram",
            "# HELP novu_db_alive 1 if the database is reachable, 0 otherwise",
            "# TYPE novu_db_alive gauge",
            "# HELP novu_reaper_requeues_total Total analysis jobs requeued by the lease reaper",
            "# TYPE novu_reaper_requeues_total counter",
            "# HELP novu_auth_failures_total Total auth failures by endpoint, reason, and tenant",
            "# TYPE novu_auth_failures_total counter",
        ]

        for expected_line in expected_lines:
            assert expected_line in lines

    @pytest.mark.asyncio
    async def test_metrics_text_export_uses_stable_lf_format(self, app_client):
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        assert "\r" not in resp.text
        assert resp.text.endswith("\n")

    @pytest.mark.asyncio
    async def test_failed_login_increments_auth_failure_counter(self, app_client):
        await app_client.post("/api/v1/auth/login", json={"email": "manager_a@test.local", "password": "wrong-pass"})
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        line = _metric_line(resp.text, 'novu_auth_failures_total{endpoint="login",reason="invalid_credentials"')
        assert line is not None
        assert _metric_labels_fragment(line) == 'endpoint="login",reason="invalid_credentials",tenant_id="unknown"'
        assert 'tenant_id="unknown"' in line

    @pytest.mark.asyncio
    async def test_upload_rejection_counter_is_exported(self, app_client):
        from app.core.metrics import UPLOAD_REJECTIONS_TOTAL, metric_labels

        metric_labels(
            UPLOAD_REJECTIONS_TOTAL,
            status_code="400",
            reason="invalid_upload",
        ).inc()
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        line = _metric_line(resp.text, 'novu_upload_rejections_total{reason="invalid_upload",status_code="400"}')
        assert line is not None
        assert _metric_labels_fragment(line) == 'reason="invalid_upload",status_code="400"'

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
    async def test_http_request_metric_labels_are_exported_in_declared_order(self, app_client):
        await app_client.get(_ALIVE_URL)
        resp = await app_client.get(_METRICS_URL, headers=_metrics_auth_headers())
        line = _metric_line(
            resp.text,
            'http_requests_total{method="GET",path_template="/api/v1/alive",status_code="200"}',
        )
        assert line is not None
        assert _metric_labels_fragment(line) == 'method="GET",path_template="/api/v1/alive",status_code="200"'

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
