from __future__ import annotations

from dataclasses import dataclass
import inspect
from unittest.mock import Mock

from fastapi import HTTPException

from app.core.metrics import record_backpressure_rejection
from app.worker.heavy_queue import get_heavy_job_queue_counts
from app.worker.queue import get_analysis_job_queue_counts

PRIORITY_STANDARD = "standard"
PRIORITY_CRITICAL = "critical"
_SERVABLE_RUNTIME_STATES = frozenset({"ready", "degraded"})


def _has_declared_attr(obj, name: str) -> bool:
    if obj is None:
        return False
    obj_dict = getattr(obj, "__dict__", None)
    if isinstance(obj_dict, dict) and name in obj_dict:
        return True
    for cls in type(obj).__mro__:
        cls_dict = getattr(cls, "__dict__", None)
        if isinstance(cls_dict, dict) and name in cls_dict:
            return True
    return False


def _int_setting(settings, attr: str, default: int) -> int:
    value = getattr(settings, attr, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _counter_value(value: object) -> int:
    if isinstance(value, Mock):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def effective_backpressure_max_concurrent_jobs(settings) -> int:
    if hasattr(settings, "effective_backpressure_max_concurrent_jobs"):
        return max(1, _int_setting(settings, "effective_backpressure_max_concurrent_jobs", 1))
    # Backpressure capacity is a runtime throughput concept spanning both
    # standard and heavy worker lanes. This is intentionally broader than
    # worker DB pool sizing, which is configured separately.
    worker_slots = _int_setting(settings, "worker_concurrency", 0) + _int_setting(
        settings,
        "worker_heavy_concurrency",
        0,
    )
    configured = _int_setting(settings, "backpressure_max_concurrent_jobs", worker_slots or 1)
    return max(1, configured)


def effective_backpressure_max_queued_jobs(settings) -> int:
    if hasattr(settings, "effective_backpressure_max_queued_jobs"):
        return max(1, _int_setting(settings, "effective_backpressure_max_queued_jobs", 1))
    lane_depth = _int_setting(settings, "analysis_queue_max_depth", 0) + _int_setting(
        settings,
        "heavy_queue_max_depth",
        0,
    )
    configured = _int_setting(settings, "backpressure_max_queued_jobs", lane_depth or 1000)
    return max(1, configured)


def effective_backpressure_max_retry_inflight(settings) -> int:
    if hasattr(settings, "effective_backpressure_max_retry_inflight"):
        return max(1, _int_setting(settings, "effective_backpressure_max_retry_inflight", 1))
    queued_cap = effective_backpressure_max_queued_jobs(settings)
    configured = _int_setting(
        settings,
        "backpressure_max_retry_inflight",
        max(1, min(queued_cap, 1000)),
    )
    return max(1, configured)


def normalize_job_priority(value: str | None) -> str:
    normalized = (value or PRIORITY_STANDARD).strip().lower()
    if normalized == PRIORITY_CRITICAL:
        return PRIORITY_CRITICAL
    return PRIORITY_STANDARD


def analysis_job_priority_for_type(job_type: str | None) -> str:
    normalized = (job_type or "").strip().lower()
    if normalized == "quote_recalculation":
        return PRIORITY_CRITICAL
    return PRIORITY_STANDARD


def heavy_job_priority_for_type(job_type: str | None) -> str:
    normalized = (job_type or "").strip().lower()
    if normalized == "export_generate":
        return PRIORITY_CRITICAL
    return PRIORITY_STANDARD


def queue_runtime_state(job_queue) -> str:
    if job_queue is None:
        return "unavailable"
    if not _has_declared_attr(job_queue, "runtime_status"):
        return "ready"
    runtime_status = getattr(job_queue, "runtime_status", None)
    if not callable(runtime_status):
        return "ready"
    if inspect.iscoroutinefunction(runtime_status):
        return "unavailable"
    try:
        status = runtime_status()
    except Exception:
        return "unavailable"
    if inspect.isawaitable(status):
        return "unavailable"
    state = getattr(status, "state", None)
    return str(state) if isinstance(state, str) and state else "ready"


@dataclass(frozen=True)
class BackpressureSnapshot:
    runtime_state: str
    analysis_queued: int
    analysis_processing: int
    heavy_queued: int
    heavy_processing: int
    retry_inflight: int
    max_concurrent_jobs: int
    max_queued_jobs: int
    max_retry_inflight: int

    @property
    def total_concurrent_jobs(self) -> int:
        return self.analysis_processing + self.heavy_processing

    @property
    def total_queued_jobs(self) -> int:
        return self.analysis_queued + self.heavy_queued

    @property
    def analysis_total_jobs(self) -> int:
        return self.analysis_queued + self.analysis_processing

    @property
    def heavy_total_jobs(self) -> int:
        return self.heavy_queued + self.heavy_processing

    @property
    def runtime_servable(self) -> bool:
        return self.runtime_state in _SERVABLE_RUNTIME_STATES

    @property
    def global_queue_full(self) -> bool:
        return self.total_queued_jobs >= self.max_queued_jobs


async def collect_backpressure_snapshot(
    *,
    settings,
    job_queue,
    retry_inflight: int = 0,
) -> BackpressureSnapshot:
    analysis_queued = 0
    analysis_processing = 0
    heavy_queued = 0
    heavy_processing = 0
    runtime_state = queue_runtime_state(job_queue)

    if job_queue is not None and _has_declared_attr(job_queue, "llen"):
        analysis_queued, analysis_processing = await get_analysis_job_queue_counts(job_queue)
        heavy_queued, heavy_processing = await get_heavy_job_queue_counts(job_queue)

    return BackpressureSnapshot(
        runtime_state=runtime_state,
        analysis_queued=analysis_queued,
        analysis_processing=analysis_processing,
        heavy_queued=heavy_queued,
        heavy_processing=heavy_processing,
        retry_inflight=_counter_value(retry_inflight),
        max_concurrent_jobs=effective_backpressure_max_concurrent_jobs(settings),
        max_queued_jobs=effective_backpressure_max_queued_jobs(settings),
        max_retry_inflight=effective_backpressure_max_retry_inflight(settings),
    )


def ensure_analysis_intake_capacity(snapshot: BackpressureSnapshot, *, settings) -> None:
    if not snapshot.runtime_servable:
        record_backpressure_rejection(surface="analysis_api", reason="runtime_unavailable")
        raise HTTPException(status_code=503, detail="Analysis queue is unavailable.")
    if snapshot.analysis_total_jobs >= int(settings.analysis_queue_max_depth):
        record_backpressure_rejection(surface="analysis_api", reason="analysis_lane_full")
        raise HTTPException(status_code=429, detail="Analysis queue is full. Please retry later.")
    if snapshot.global_queue_full:
        record_backpressure_rejection(surface="analysis_api", reason="global_queue_full")
        raise HTTPException(status_code=429, detail="System queue capacity is exhausted. Please retry later.")


def ensure_heavy_intake_capacity(snapshot: BackpressureSnapshot, *, settings, surface: str) -> None:
    if not snapshot.runtime_servable:
        record_backpressure_rejection(surface=surface, reason="runtime_unavailable")
        raise HTTPException(status_code=503, detail="Heavy work queue is unavailable.")
    if snapshot.heavy_total_jobs >= int(settings.heavy_queue_max_depth):
        record_backpressure_rejection(surface=surface, reason="heavy_lane_full")
        raise HTTPException(status_code=429, detail="Export queue is full. Please retry later.")
    if snapshot.global_queue_full:
        record_backpressure_rejection(surface=surface, reason="global_queue_full")
        raise HTTPException(status_code=429, detail="System queue capacity is exhausted. Please retry later.")


def require_worker_capacity(surface: str, *, settings) -> None:
    """Hard guard: raise HTTP 503 when the heavy-lane worker pool is unavailable.

    Call this at the start of any operation that requires background processing.
    The invariant it enforces: the API **never** performs heavy CPU/I/O work
    inline — no fallback, no sync mode.

    Raises 503 when:
    - ``worker_heavy_concurrency == 0``  (lane not configured / worker stopped)
    """
    if _int_setting(settings, "worker_heavy_concurrency", 0) == 0:
        record_backpressure_rejection(surface=surface, reason="heavy_lane_disabled")
        raise HTTPException(
            status_code=503,
            detail="Heavy work lane is unavailable. Ensure the worker is running.",
        )


def ensure_retry_budget(retry_inflight: int, *, settings, surface: str) -> None:
    if _counter_value(retry_inflight) >= effective_backpressure_max_retry_inflight(settings):
        record_backpressure_rejection(surface=surface, reason="retry_budget_exhausted")
        raise HTTPException(
            status_code=429,
            detail="Retry capacity is exhausted during the current incident. Please retry later.",
        )
