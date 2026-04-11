"""Application-level Prometheus metrics (R-38).

Three metrics cover the minimum useful signal:
  http_requests_total           request count by method / path_template / status
  http_request_duration_seconds latency histogram (same labels)
  http_requests_in_progress     concurrency gauge by method

The log_requests middleware in app/main.py populates these.
The /metrics endpoint in app/api/routes/system.py exposes them.
It is intentionally separate from /health and /ready probe semantics.

Path template (e.g. /api/v1/cases/{case_id}) is used as the label, not the raw
URL, to prevent label cardinality explosion from per-resource IDs.
"""

from __future__ import annotations

from collections import deque
from threading import Lock

import structlog

logger = structlog.get_logger(__name__)

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

    PROMETHEUS_CLIENT_AVAILABLE = True
except ModuleNotFoundError as exc:
    logger.warning(
        "metrics.disabled",
        reason="prometheus_client_not_installed",
        error=str(exc),
    )
    PROMETHEUS_CLIENT_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    generate_latest = None

    class _NoopMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs) -> None:
            return None

        def dec(self, *args, **kwargs) -> None:
            return None

        def observe(self, *args, **kwargs) -> None:
            return None

        def set(self, *args, **kwargs) -> None:
            return None

    def Counter(*args, **kwargs):  # type: ignore[misc]
        return _NoopMetric()

    def Gauge(*args, **kwargs):  # type: ignore[misc]
        return _NoopMetric()

    def Histogram(*args, **kwargs):  # type: ignore[misc]
        return _NoopMetric()


HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path_template", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path_template", "status_code"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 2.5, 5.0, 10.0],
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently being processed",
    ["method"],
)

# Operational gauges (C5)
# Refreshed from the system.py operational snapshot path used by /metrics.
# The snapshot is intentionally short-lived and in-process only.

DB_ALIVE = Gauge(
    "novu_db_alive",
    "1 if the database is reachable, 0 otherwise",
)

WORKER_ALIVE = Gauge(
    "novu_worker_alive",
    "1 if at least one worker heartbeat was received within 90 s, 0 if stale or absent",
)

WORKER_ALIVE_INSTANCES = Gauge(
    "novu_worker_alive_instances",
    "Number of worker instances with a fresh heartbeat",
)

WORKER_SEEN_INSTANCES = Gauge(
    "novu_worker_seen_instances",
    "Number of worker heartbeat keys currently visible to monitoring",
)

WORKER_MONITORING_AVAILABLE = Gauge(
    "novu_worker_monitoring_available",
    "1 if worker heartbeat monitoring can read Redis, 0 if worker status is currently unknown",
)

STORAGE_READY = Gauge(
    "novu_storage_ready",
    "1 if the active storage backend is reachable, 0 otherwise",
)

REDIS_RUNTIME_AVAILABLE = Gauge(
    "novu_redis_runtime_available",
    "1 if shared Redis-backed runtime enforcement is available, 0 otherwise",
)

REDIS_RUNTIME_DEGRADED = Gauge(
    "novu_redis_runtime_degraded",
    "1 if Redis runtime is operating in degraded mode (for example failover), 0 otherwise",
)

AUTH_PROTECTION_ENFORCED = Gauge(
    "novu_auth_protection_enforced",
    "1 if authoritative auth protection enforcement is currently active, 0 otherwise",
)

QUEUE_LENGTH = Gauge(
    "novu_queue_length",
    "Current durable analysis queue length in Redis",
)

HEAVY_QUEUE_LENGTH = Gauge(
    "novu_heavy_queue_length",
    "Current durable heavy queue length in Redis",
)

PROCESSING_JOBS = Gauge(
    "novu_processing_jobs",
    "Current number of leased analysis jobs in Redis processing",
)

HEAVY_PROCESSING_JOBS = Gauge(
    "novu_heavy_processing_jobs",
    "Current number of leased heavy jobs in Redis processing",
)

QUEUE_SCHEDULED_RETRY = Gauge(
    "novu_queue_scheduled_retry",
    "Current number of scheduled analysis retries waiting in Redis",
)

QUEUE_SCHEDULED_RETRY_DUE_NOW = Gauge(
    "novu_queue_scheduled_retry_due_now",
    "Current number of scheduled analysis retries that are due for promotion now",
)

QUEUE_DEAD_LETTER_ACTIVE = Gauge(
    "novu_queue_dead_letter_active",
    "Current number of active Redis dead-letter queue entries",
)

JOBS_QUEUED = Gauge(
    "novu_jobs_queued",
    "Number of analysis jobs in queued state",
)

JOBS_RUNNING = Gauge(
    "novu_jobs_running",
    "Number of analysis jobs in running state",
)

JOB_STUCK_MAX_AGE_SECONDS = Gauge(
    "novu_job_stuck_max_age_seconds",
    "Age in seconds of the oldest running analysis job",
)

JOB_DURATION_SECONDS = Histogram(
    "novu_job_duration_seconds",
    "Analysis job duration in seconds by terminal status and tenant",
    ["status", "tenant_id"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 180.0, 300.0, 600.0],
)

JOB_DURATION_SECONDS_AVG = Gauge(
    "novu_job_duration_seconds_avg",
    "Average analysis job duration in seconds over the in-process rolling window",
)

JOB_DURATION_SECONDS_P95 = Gauge(
    "novu_job_duration_seconds_p95",
    "P95 analysis job duration in seconds over the in-process rolling window",
)

JOB_OUTCOMES_TOTAL = Counter(
    "novu_job_outcomes_total",
    "Total completed analysis jobs by terminal status and tenant",
    ["status", "tenant_id"],
)

JOB_FAIL_RATE = Gauge(
    "novu_job_fail_rate",
    "Failure ratio across in-process observed terminal analysis jobs",
)

REAPER_REQUEUES_TOTAL = Counter(
    "novu_reaper_requeues_total",
    "Total analysis jobs requeued by the lease reaper",
)

DUPLICATE_PREVENTED_COUNT = Counter(
    "novu_duplicate_prevented_count",
    "Total duplicate job submissions or executions prevented",
    ["reason"],
)

BACKPRESSURE_CURRENT_CONCURRENT = Gauge(
    "novu_backpressure_current_concurrent_jobs",
    "Current concurrent jobs counted toward the global backpressure contract",
)

BACKPRESSURE_CURRENT_QUEUED = Gauge(
    "novu_backpressure_current_queued_jobs",
    "Current queued jobs counted toward the global backpressure contract",
)

BACKPRESSURE_CURRENT_RETRY_INFLIGHT = Gauge(
    "novu_backpressure_current_retry_inflight",
    "Current retry jobs counted toward the global backpressure contract",
)

BACKPRESSURE_MAX_CONCURRENT = Gauge(
    "novu_backpressure_max_concurrent_jobs",
    "Configured global concurrency ceiling enforced by backpressure",
)

BACKPRESSURE_MAX_QUEUED = Gauge(
    "novu_backpressure_max_queued_jobs",
    "Configured global queued-job ceiling enforced by backpressure",
)

BACKPRESSURE_MAX_RETRY_INFLIGHT = Gauge(
    "novu_backpressure_max_retry_inflight",
    "Configured global retry-inflight ceiling enforced by backpressure",
)

BACKPRESSURE_REJECTIONS_TOTAL = Counter(
    "novu_backpressure_rejections_total",
    "Total requests or retry actions rejected by backpressure",
    ["surface", "reason"],
)

# Audit trail health (R-AUD-01)
# Incremented whenever an audit log write fails so that Prometheus can alert on
# silent audit-trail gaps.  Complements the SECURITY_EVENT log warning.
AUDIT_WRITE_FAILED_TOTAL = Counter(
    "novu_audit_write_failed_total",
    "Total number of audit log write failures",
)

AUTH_FAILURES_TOTAL = Counter(
    "novu_auth_failures_total",
    "Total auth failures by endpoint, reason, and tenant",
    ["endpoint", "reason", "tenant_id"],
)

UPLOAD_REJECTIONS_TOTAL = Counter(
    "novu_upload_rejections_total",
    "Total rejected uploads by coarse-grained reason and HTTP status",
    ["reason", "status_code"],
)

STORAGE_OPERATIONS_TOTAL = Counter(
    "novu_storage_operations_total",
    "Total storage operations by operation type, backend, and outcome",
    ["operation", "backend", "outcome"],
)

STORAGE_OPERATION_DURATION_SECONDS = Histogram(
    "novu_storage_operation_duration_seconds",
    "Storage operation latency in seconds by operation type, backend, and outcome",
    ["operation", "backend", "outcome"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

CACHE_REQUESTS_TOTAL = Counter(
    "novu_cache_requests_total",
    "Cache operations by namespace, operation, and outcome",
    ["namespace", "operation", "outcome"],
)

CACHE_OPERATION_DURATION_SECONDS = Histogram(
    "novu_cache_operation_duration_seconds",
    "Cache operation latency in seconds by namespace, operation, and outcome",
    ["namespace", "operation", "outcome"],
    buckets=[0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

DB_POOL_EXHAUSTED_TOTAL = Counter(
    "novu_db_pool_exhausted_total",
    "Total requests rejected due to DB connection pool exhaustion (returns HTTP 503)",
)

WORK_CATALOG_RESOLUTION_DURATION_SECONDS = Histogram(
    "novu_work_catalog_resolution_duration_seconds",
    "Work catalog resolution latency by path and outcome",
    ["path", "outcome"],
    buckets=[0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

WORK_CATALOG_RESOLUTION_INPUT_ROWS = Histogram(
    "novu_work_catalog_resolution_input_rows",
    "Work catalog resolution input cardinality by path and input kind",
    ["path", "kind"],
    buckets=[1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500],
)

WORK_CATALOG_VALIDATION_FAILURES_TOTAL = Counter(
    "novu_work_catalog_validation_failures_total",
    "Work catalog validation failures by operation and coarse reason",
    ["operation", "reason"],
)

_JOB_DURATION_WINDOW = deque(maxlen=200)
_JOB_DURATION_LOCK = Lock()
_JOB_OUTCOME_COUNTS: dict[str, int] = {"completed": 0, "failed": 0}
_JOB_FAIL_RATE_CURRENT = 0.0
_JOB_DURATION_AVG_CURRENT = 0.0
_JOB_DURATION_P95_CURRENT = 0.0


def _percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(0, min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * quantile))))
    return float(sorted_values[index])


def normalize_tenant_metric_label(
    tenant_id: str | None,
    *,
    is_superadmin_context: bool = False,
) -> str:
    normalized = (tenant_id or "").strip()
    if normalized:
        return normalized
    if is_superadmin_context:
        return "superadmin"
    return "unknown"


def observe_job_outcome(
    *,
    status: str,
    duration_seconds: float | None,
    tenant_id: str | None = None,
    is_superadmin_context: bool = False,
) -> None:
    """Record terminal job outcome metrics and refresh rolling duration gauges.

    tenant_id should be the organization_id string.
    Pass is_superadmin_context=True for explicit cross-tenant/superadmin
    execution so unlabeled tenant context is exported as "superadmin".
    Otherwise missing tenant context is exported as "unknown".
    """
    global _JOB_FAIL_RATE_CURRENT, _JOB_DURATION_AVG_CURRENT, _JOB_DURATION_P95_CURRENT
    normalized_status = status.strip().lower() or "unknown"
    normalized_tenant = normalize_tenant_metric_label(
        tenant_id,
        is_superadmin_context=is_superadmin_context,
    )
    metric_labels(
        JOB_OUTCOMES_TOTAL,
        status=normalized_status,
        tenant_id=normalized_tenant,
    ).inc()
    with _JOB_DURATION_LOCK:
        if normalized_status in _JOB_OUTCOME_COUNTS:
            _JOB_OUTCOME_COUNTS[normalized_status] += 1

        total_terminal = sum(_JOB_OUTCOME_COUNTS.values())
        fail_rate = (
            _JOB_OUTCOME_COUNTS["failed"] / total_terminal
            if total_terminal > 0
            else 0.0
        )
        _JOB_FAIL_RATE_CURRENT = fail_rate
        JOB_FAIL_RATE.set(fail_rate)

        if duration_seconds is None:
            return

        duration = max(0.0, float(duration_seconds))
        metric_labels(
            JOB_DURATION_SECONDS,
            status=normalized_status,
            tenant_id=normalized_tenant,
        ).observe(duration)
        _JOB_DURATION_WINDOW.append(duration)
        samples = sorted(_JOB_DURATION_WINDOW)
        _JOB_DURATION_AVG_CURRENT = sum(samples) / len(samples)
        _JOB_DURATION_P95_CURRENT = _percentile(samples, 0.95)
        JOB_DURATION_SECONDS_AVG.set(_JOB_DURATION_AVG_CURRENT)
        JOB_DURATION_SECONDS_P95.set(_JOB_DURATION_P95_CURRENT)


def record_reaper_requeues(count: int = 1) -> None:
    if count > 0:
        REAPER_REQUEUES_TOTAL.inc(count)


def record_duplicate_prevented(reason: str) -> None:
    normalized_reason = reason.strip().lower() or "unknown"
    metric_labels(DUPLICATE_PREVENTED_COUNT, reason=normalized_reason).inc()


def record_backpressure_rejection(*, surface: str, reason: str) -> None:
    normalized_surface = surface.strip().lower() or "unknown"
    normalized_reason = reason.strip().lower() or "unknown"
    metric_labels(
        BACKPRESSURE_REJECTIONS_TOTAL,
        surface=normalized_surface,
        reason=normalized_reason,
    ).inc()


def observe_cache_operation(
    *,
    namespace: str,
    operation: str,
    outcome: str,
    duration_seconds: float | None = None,
) -> None:
    normalized_namespace = namespace.strip().lower() or "unknown"
    normalized_operation = operation.strip().lower() or "unknown"
    normalized_outcome = outcome.strip().lower() or "unknown"
    metric_labels(
        CACHE_REQUESTS_TOTAL,
        namespace=normalized_namespace,
        operation=normalized_operation,
        outcome=normalized_outcome,
    ).inc()
    if duration_seconds is not None:
        metric_labels(
            CACHE_OPERATION_DURATION_SECONDS,
            namespace=normalized_namespace,
            operation=normalized_operation,
            outcome=normalized_outcome,
        ).observe(max(0.0, float(duration_seconds)))


def observe_work_catalog_resolution(
    *,
    path: str,
    outcome: str,
    duration_seconds: float,
) -> None:
    normalized_path = path.strip().lower() or "unknown"
    normalized_outcome = outcome.strip().lower() or "unknown"
    metric_labels(
        WORK_CATALOG_RESOLUTION_DURATION_SECONDS,
        path=normalized_path,
        outcome=normalized_outcome,
    ).observe(max(0.0, float(duration_seconds)))


def observe_work_catalog_resolution_input(*, path: str, kind: str, count: int) -> None:
    normalized_path = path.strip().lower() or "unknown"
    normalized_kind = kind.strip().lower() or "unknown"
    metric_labels(
        WORK_CATALOG_RESOLUTION_INPUT_ROWS,
        path=normalized_path,
        kind=normalized_kind,
    ).observe(max(0, int(count)))


def record_work_catalog_validation_failure(*, operation: str, reason: str) -> None:
    normalized_operation = operation.strip().lower() or "unknown"
    normalized_reason = reason.strip().lower() or "unknown"
    metric_labels(
        WORK_CATALOG_VALIDATION_FAILURES_TOTAL,
        operation=normalized_operation,
        reason=normalized_reason,
    ).inc()


def observe_storage_operation(
    *,
    operation: str,
    backend: str,
    outcome: str,
    duration_seconds: float,
) -> None:
    """Record a single storage I/O operation (upload, read, delete, etc.)."""
    norm_op = operation.strip().lower() or "unknown"
    norm_backend = backend.strip().lower() or "unknown"
    norm_outcome = outcome.strip().lower() or "unknown"
    metric_labels(
        STORAGE_OPERATIONS_TOTAL,
        operation=norm_op,
        backend=norm_backend,
        outcome=norm_outcome,
    ).inc()
    metric_labels(
        STORAGE_OPERATION_DURATION_SECONDS,
        operation=norm_op,
        backend=norm_backend,
        outcome=norm_outcome,
    ).observe(max(0.0, float(duration_seconds)))


def refresh_job_observability_gauges() -> None:
    """Expose current in-process aggregate job gauges during every scrape."""
    metric_labels(JOB_DURATION_SECONDS, status="completed", tenant_id="unknown")
    metric_labels(JOB_DURATION_SECONDS, status="failed", tenant_id="unknown")
    metric_labels(JOB_OUTCOMES_TOTAL, status="completed", tenant_id="unknown").inc(0)
    metric_labels(JOB_OUTCOMES_TOTAL, status="failed", tenant_id="unknown").inc(0)
    JOB_FAIL_RATE.set(_JOB_FAIL_RATE_CURRENT)
    JOB_DURATION_SECONDS_AVG.set(_JOB_DURATION_AVG_CURRENT)
    JOB_DURATION_SECONDS_P95.set(_JOB_DURATION_P95_CURRENT)
    metric_labels(BACKPRESSURE_REJECTIONS_TOTAL, surface="analysis_api", reason="queue_full").inc(0)


PROMETHEUS_TEXT_CONTENT_TYPE = CONTENT_TYPE_LATEST


def metric_label_names(metric) -> tuple[str, ...]:
    return tuple(str(label_name) for label_name in (getattr(metric, "_labelnames", ()) or ()))


def metric_labels(metric, /, **label_values):
    """Bind labels using the metric's declared label order and exact label set."""
    expected = metric_label_names(metric)
    if not expected:
        if label_values:
            raise ValueError(
                f"Metric {getattr(metric, '_name', '<unknown>')} does not accept labels; "
                f"got {tuple(label_values.keys())!r}."
            )
        return metric.labels()

    provided_names = tuple(label_values.keys())
    missing = tuple(label_name for label_name in expected if label_name not in label_values)
    extra = tuple(label_name for label_name in provided_names if label_name not in expected)
    if missing or extra:
        raise ValueError(
            f"Metric {getattr(metric, '_name', '<unknown>')} expects labels {expected!r}; "
            f"got {provided_names!r}."
        )

    ordered_values = {label_name: label_values[label_name] for label_name in expected}
    return metric.labels(**ordered_values)


def metric_export_name(metric) -> str:
    """Return the canonical Prometheus text-export family name for a collector."""
    name = str(getattr(metric, "_name", "") or "")
    metric_type = str(getattr(metric, "_type", "") or "")
    if metric_type == "counter" and name and not name.endswith("_total"):
        return f"{name}_total"
    return name


def metric_help_line(metric) -> str:
    export_name = metric_export_name(metric)
    help_text = str(getattr(metric, "_documentation", "") or "")
    normalized_help = help_text.replace("\\", r"\\").replace("\n", r"\n")
    return f"# HELP {export_name} {normalized_help}"


def metric_type_line(metric) -> str:
    export_name = metric_export_name(metric)
    metric_type = str(getattr(metric, "_type", "untyped") or "untyped")
    return f"# TYPE {export_name} {metric_type}"


def render_metrics_text() -> bytes:
    """Render Prometheus metrics using a normalized LF-only text payload."""
    if not PROMETHEUS_CLIENT_AVAILABLE or generate_latest is None:
        raise RuntimeError("prometheus_client_not_installed")

    payload = generate_latest()
    text = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized.encode("utf-8")
