"""Application-level Prometheus metrics (R-38).

Three metrics cover the minimum useful signal:
  http_requests_total          — request count by method / path_template / status
  http_request_duration_seconds — latency histogram (same labels)
  http_requests_in_progress     — concurrency gauge by method

The log_requests middleware in app/main.py populates these.
The /metrics endpoint in app/api/routes/system.py exposes them.

Path template (e.g. /api/v1/cases/{case_id}) is used as the label, NOT the
raw URL, to prevent label cardinality explosion from per-resource IDs.
"""
from prometheus_client import Counter, Gauge, Histogram

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
