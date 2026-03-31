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
    from prometheus_client import Counter, Gauge, Histogram

    PROMETHEUS_CLIENT_AVAILABLE = True
except ModuleNotFoundError as exc:
    logger.warning(
        "metrics.disabled",
        reason="prometheus_client_not_installed",
        error=str(exc),
    )
    PROMETHEUS_CLIENT_AVAILABLE = False

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
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
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

QUEUE_LENGTH = Gauge(
    "novu_queue_length",
    "Current durable analysis queue length in Redis",
)

PROCESSING_JOBS = Gauge(
    "novu_processing_jobs",
    "Current number of leased analysis jobs in Redis processing",
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
    "Analysis job duration in seconds by terminal status",
    ["status"],
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
    "Total completed analysis jobs by terminal status",
    ["status"],
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

# Audit trail health (R-AUD-01)
# Incremented whenever an audit log write fails so that Prometheus can alert on
# silent audit-trail gaps.  Complements the SECURITY_EVENT log warning.
AUDIT_WRITE_FAILED_TOTAL = Counter(
    "novu_audit_write_failed_total",
    "Total number of audit log write failures",
)

AUTH_FAILURES_TOTAL = Counter(
    "novu_auth_failures_total",
    "Total auth failures by endpoint and coarse-grained reason",
    ["endpoint", "reason"],
)

UPLOAD_REJECTIONS_TOTAL = Counter(
    "novu_upload_rejections_total",
    "Total rejected uploads by coarse-grained reason and HTTP status",
    ["reason", "status_code"],
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

WORK_CATALOG_RESOLUTION_DURATION_SECONDS = Histogram(
    "novu_work_catalog_resolution_duration_seconds",
    "Work catalog resolution latency by path and outcome",
    ["path", "outcome"],
    buckets=[0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
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


def observe_job_outcome(*, status: str, duration_seconds: float | None) -> None:
    """Record terminal job outcome metrics and refresh rolling duration gauges."""
    global _JOB_FAIL_RATE_CURRENT, _JOB_DURATION_AVG_CURRENT, _JOB_DURATION_P95_CURRENT
    normalized_status = status.strip().lower() or "unknown"
    JOB_OUTCOMES_TOTAL.labels(status=normalized_status).inc()
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
        JOB_DURATION_SECONDS.labels(status=normalized_status).observe(duration)
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
    DUPLICATE_PREVENTED_COUNT.labels(reason=normalized_reason).inc()


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
    CACHE_REQUESTS_TOTAL.labels(
        namespace=normalized_namespace,
        operation=normalized_operation,
        outcome=normalized_outcome,
    ).inc()
    if duration_seconds is not None:
        CACHE_OPERATION_DURATION_SECONDS.labels(
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
    WORK_CATALOG_RESOLUTION_DURATION_SECONDS.labels(
        path=normalized_path,
        outcome=normalized_outcome,
    ).observe(max(0.0, float(duration_seconds)))


def record_work_catalog_validation_failure(*, operation: str, reason: str) -> None:
    normalized_operation = operation.strip().lower() or "unknown"
    normalized_reason = reason.strip().lower() or "unknown"
    WORK_CATALOG_VALIDATION_FAILURES_TOTAL.labels(
        operation=normalized_operation,
        reason=normalized_reason,
    ).inc()


def refresh_job_observability_gauges() -> None:
    """Expose current in-process aggregate job gauges during every scrape."""
    JOB_DURATION_SECONDS.labels(status="completed")
    JOB_DURATION_SECONDS.labels(status="failed")
    JOB_OUTCOMES_TOTAL.labels(status="completed").inc(0)
    JOB_OUTCOMES_TOTAL.labels(status="failed").inc(0)
    JOB_FAIL_RATE.set(_JOB_FAIL_RATE_CURRENT)
    JOB_DURATION_SECONDS_AVG.set(_JOB_DURATION_AVG_CURRENT)
    JOB_DURATION_SECONDS_P95.set(_JOB_DURATION_P95_CURRENT)
