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

JOBS_QUEUED = Gauge(
    "novu_jobs_queued",
    "Number of analysis jobs in queued state",
)

JOBS_RUNNING = Gauge(
    "novu_jobs_running",
    "Number of analysis jobs in running state",
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
