from __future__ import annotations

import asyncio
import inspect
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import Response as RawResponse
from sqlalchemy import case, func, select, text
import structlog

from app.api.deps import require_superadmin
from app.core.config import get_settings
from app.core.metrics import (
    DB_ALIVE,
    JOBS_QUEUED,
    JOBS_RUNNING,
    JOB_FAIL_RATE,
    JOB_STUCK_MAX_AGE_SECONDS,
    JOB_DURATION_SECONDS_AVG,
    JOB_DURATION_SECONDS_P95,
    PROMETHEUS_CLIENT_AVAILABLE,
    PROCESSING_JOBS,
    QUEUE_LENGTH,
    DUPLICATE_PREVENTED_COUNT,
    REAPER_REQUEUES_TOTAL,
    refresh_job_observability_gauges,
    WORKER_ALIVE,
    WORKER_ALIVE_INSTANCES,
    WORKER_MONITORING_AVAILABLE,
    WORKER_SEEN_INSTANCES,
)
from app.db.session import AsyncSessionFactory
from app.models import AnalysisJob
from app.schemas.auth import AuthUserRead
from app.storage.backend import verify_storage_health
from app.worker.heartbeat import (
    WORKER_HEARTBEAT_FRESHNESS_SECONDS,
    WORKER_HEARTBEAT_KEY_PATTERN,
    WORKER_HEARTBEAT_KEY_PREFIX,
    WORKER_HEARTBEAT_LEGACY_KEY,
)
from app.worker.queue import get_analysis_job_queue_counts

router = APIRouter()
logger = structlog.get_logger(__name__)
_PROBE_SERVICE_NAME = "python-backend"
_READINESS_DB_CACHE_TTL_SECONDS = 2.0
_OPERATIONAL_METRICS_CACHE_TTL_SECONDS = 5.0

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
except ModuleNotFoundError:
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    generate_latest = None


@dataclass
class _ReadinessDbCache:
    ready: bool | None = None
    expires_at_monotonic: float = 0.0
    lock: asyncio.Lock | None = None

    def get_lock(self) -> asyncio.Lock:
        if self.lock is None:
            self.lock = asyncio.Lock()
        return self.lock


@dataclass
class _OperationalMetricsCache:
    snapshot: "_OperationalMetricsSnapshot" | None = None
    expires_at_monotonic: float = 0.0
    lock: asyncio.Lock | None = None

    def get_lock(self) -> asyncio.Lock:
        if self.lock is None:
            self.lock = asyncio.Lock()
        return self.lock


@dataclass
class _ReadinessStorageCache:
    ready: bool | None = None
    expires_at_monotonic: float = 0.0
    lock: asyncio.Lock | None = None

    def get_lock(self) -> asyncio.Lock:
        if self.lock is None:
            self.lock = asyncio.Lock()
        return self.lock


@dataclass(frozen=True)
class _WorkerHeartbeatSnapshot:
    alive: bool | None
    last_seen_at: str | None
    alive_instances: int | None
    seen_instances: int | None


@dataclass(frozen=True)
class _OperationalMetricsSnapshot:
    db_alive: bool
    jobs_running: int
    jobs_queued: int
    queue_length: int
    processing_jobs: int
    job_stuck_max_age_seconds: float
    worker: _WorkerHeartbeatSnapshot
    queue_monitoring_available: bool = False
    queue_state: str = "unavailable"


@dataclass(frozen=True)
class _JobProcessingReadinessSnapshot:
    api_ready: bool
    job_processing_ready: bool
    strict_job_processing_ready: bool
    worker_state: str
    queue_state: str
    grace_active: bool


def _queue_runtime_state(job_queue) -> str:
    if job_queue is None:
        return "unavailable"
    status_factory = getattr(job_queue, "runtime_status", None)
    if callable(status_factory):
        try:
            status = status_factory()
            if inspect.isawaitable(status):
                return "unavailable"
            state = getattr(status, "state", None)
            if isinstance(state, str) and state:
                return state
        except Exception:
            return "unavailable"
    return "ready"


def _queue_runtime_details(job_queue) -> dict[str, object] | None:
    if job_queue is None:
        return None
    status_factory = getattr(job_queue, "runtime_status", None)
    if not callable(status_factory):
        return None
    try:
        status = status_factory()
        if inspect.isawaitable(status):
            return None
    except Exception:
        return None
    return {
        "mode": getattr(status, "mode", "single"),
        "state": getattr(status, "state", "unknown"),
        "candidateCount": getattr(status, "candidate_count", None),
        "activeUrl": getattr(status, "active_url", None),
        "degraded": getattr(status, "degraded", None),
        "lastError": getattr(status, "last_error", None),
        "lastFailoverAt": getattr(status, "last_failover_at", None),
    }


async def _refresh_operational_metrics(request: Request) -> None:
    """Refresh DB/worker/job gauges before each Prometheus scrape (C5).

    Failures are silently swallowed; a missing gauge value is better than a
    broken scrape endpoint.
    """
    snapshot = await _get_operational_metrics_snapshot_cached(request)
    DB_ALIVE.set(1 if snapshot.db_alive else 0)
    JOBS_RUNNING.set(snapshot.jobs_running)
    JOBS_QUEUED.set(snapshot.jobs_queued)
    QUEUE_LENGTH.set(snapshot.queue_length)
    PROCESSING_JOBS.set(snapshot.processing_jobs)
    JOB_STUCK_MAX_AGE_SECONDS.set(snapshot.job_stuck_max_age_seconds)
    refresh_job_observability_gauges()
    REAPER_REQUEUES_TOTAL.inc(0)
    DUPLICATE_PREVENTED_COUNT.labels(reason="active_job_exists").inc(0)

    worker = snapshot.worker
    if worker.alive is None:
        WORKER_MONITORING_AVAILABLE.set(0)
        WORKER_ALIVE.set(0)
        WORKER_ALIVE_INSTANCES.set(0)
        WORKER_SEEN_INSTANCES.set(0)
        return

    WORKER_MONITORING_AVAILABLE.set(1)
    WORKER_ALIVE.set(1 if worker.alive else 0)
    WORKER_ALIVE_INSTANCES.set(worker.alive_instances or 0)
    WORKER_SEEN_INSTANCES.set(worker.seen_instances or 0)


async def _database_ready() -> bool:
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _startup_ready(request: Request) -> bool:
    startup_checks = getattr(request.app.state, "startup_checks", {})
    return bool(startup_checks) and all(value == "ok" for value in startup_checks.values())


def _readiness_now() -> float:
    return time.monotonic()


def _get_readiness_db_cache(request: Request) -> _ReadinessDbCache:
    cache = getattr(request.app.state, "readiness_db_cache", None)
    if not isinstance(cache, _ReadinessDbCache):
        cache = _ReadinessDbCache()
        request.app.state.readiness_db_cache = cache
    return cache


def _clear_readiness_db_cache(app) -> None:
    app.state.readiness_db_cache = _ReadinessDbCache()


def _get_readiness_storage_cache(request: Request) -> _ReadinessStorageCache:
    cache = getattr(request.app.state, "readiness_storage_cache", None)
    if not isinstance(cache, _ReadinessStorageCache):
        cache = _ReadinessStorageCache()
        request.app.state.readiness_storage_cache = cache
    return cache


def _clear_readiness_storage_cache(app) -> None:
    app.state.readiness_storage_cache = _ReadinessStorageCache()


def _get_operational_metrics_cache(request: Request) -> _OperationalMetricsCache:
    cache = getattr(request.app.state, "operational_metrics_cache", None)
    if not isinstance(cache, _OperationalMetricsCache):
        cache = _OperationalMetricsCache()
        request.app.state.operational_metrics_cache = cache
    return cache


def _clear_operational_metrics_cache(app) -> None:
    app.state.operational_metrics_cache = _OperationalMetricsCache()


def _decode_heartbeat_timestamp(raw_value: bytes | str | None) -> datetime | None:
    if raw_value is None:
        return None

    decoded = raw_value.decode() if isinstance(raw_value, bytes) else str(raw_value)
    try:
        parsed = datetime.fromisoformat(decoded)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


async def _iter_worker_heartbeat_values(redis):
    scan_iter = getattr(redis, "scan_iter", None)
    if scan_iter is not None:
        heartbeat_keys: list[object] = []
        async for raw_key in scan_iter(match=WORKER_HEARTBEAT_KEY_PATTERN):
            heartbeat_keys.append(raw_key)

        if heartbeat_keys:
            raw_values = await redis.mget(heartbeat_keys)
            for raw_key, raw_value in zip(heartbeat_keys, raw_values):
                if raw_value is None:
                    continue

                key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
                instance_id = (
                    key[len(WORKER_HEARTBEAT_KEY_PREFIX):]
                    if key.startswith(WORKER_HEARTBEAT_KEY_PREFIX)
                    else None
                )
                yield instance_id, raw_value

    legacy_value = await redis.get(WORKER_HEARTBEAT_LEGACY_KEY)
    if legacy_value is not None:
        yield None, legacy_value


async def _get_worker_heartbeat_snapshot(redis) -> _WorkerHeartbeatSnapshot:
    if redis is None:
        return _WorkerHeartbeatSnapshot(
            alive=None,
            last_seen_at=None,
            alive_instances=None,
            seen_instances=None,
        )

    entries: list[tuple[str | None, datetime]] = []
    async for instance_id, raw_value in _iter_worker_heartbeat_values(redis):
        timestamp = _decode_heartbeat_timestamp(raw_value)
        if timestamp is not None:
            entries.append((instance_id, timestamp))

    if not entries:
        return _WorkerHeartbeatSnapshot(
            alive=False,
            last_seen_at=None,
            alive_instances=0,
            seen_instances=0,
        )

    now = datetime.now(UTC)
    alive_instances = sum(
        1
        for _, timestamp in entries
        if (now - timestamp).total_seconds() < WORKER_HEARTBEAT_FRESHNESS_SECONDS
    )
    last_seen_at = max(timestamp for _, timestamp in entries).isoformat()
    return _WorkerHeartbeatSnapshot(
        alive=alive_instances > 0,
        last_seen_at=last_seen_at,
        alive_instances=alive_instances,
        seen_instances=len(entries),
    )


def _store_readiness_db_cache(
    request: Request,
    *,
    ready: bool,
    now_monotonic: float | None = None,
) -> None:
    cache = _get_readiness_db_cache(request)
    now = _readiness_now() if now_monotonic is None else now_monotonic
    cache.ready = ready
    cache.expires_at_monotonic = now + _READINESS_DB_CACHE_TTL_SECONDS


def _peek_operational_metrics_snapshot(
    request: Request,
    *,
    now_monotonic: float | None = None,
) -> _OperationalMetricsSnapshot | None:
    cache = _get_operational_metrics_cache(request)
    now = _readiness_now() if now_monotonic is None else now_monotonic
    if cache.snapshot is None or now >= cache.expires_at_monotonic:
        return None
    return cache.snapshot


async def _query_job_counts(session) -> tuple[int, int, float]:
    counts_row = await session.execute(
        select(
            func.coalesce(
                func.sum(case((AnalysisJob.status == "running", 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((AnalysisJob.status == "queued", 1), else_=0)),
                0,
            ),
        )
    )
    jobs_running, jobs_queued = counts_row.one()

    oldest_running_started_at = await session.scalar(
        select(func.min(AnalysisJob.started_at)).where(
            AnalysisJob.status == "running",
            AnalysisJob.started_at.is_not(None),
        )
    )
    if oldest_running_started_at is None:
        max_age_seconds = 0.0
    else:
        if oldest_running_started_at.tzinfo is None:
            oldest_running_started_at = oldest_running_started_at.replace(tzinfo=UTC)
        max_age_seconds = max(
            0.0,
            (datetime.now(UTC) - oldest_running_started_at.astimezone(UTC)).total_seconds(),
        )
    return int(jobs_running or 0), int(jobs_queued or 0), max_age_seconds


async def _collect_operational_metrics_snapshot(request: Request) -> _OperationalMetricsSnapshot:
    db_alive = False
    jobs_running = 0
    jobs_queued = 0
    queue_length = 0
    processing_jobs = 0
    job_stuck_max_age_seconds = 0.0
    queue_monitoring_available = False
    queue_state = "unavailable"
    try:
        async with AsyncSessionFactory() as session:
            jobs_running, jobs_queued, job_stuck_max_age_seconds = await _query_job_counts(session)
            db_alive = True
    except Exception:
        db_alive = False

    _store_readiness_db_cache(request, ready=db_alive)

    job_queue = getattr(request.app.state, "job_queue", None)
    queue_state = _queue_runtime_state(job_queue)
    if job_queue is not None:
        try:
            queue_length, processing_jobs = await get_analysis_job_queue_counts(job_queue)
            queue_monitoring_available = True
        except Exception:
            queue_length = 0
            processing_jobs = 0
            queue_state = "unavailable"

    try:
        worker_snapshot = await _get_worker_heartbeat_snapshot(job_queue)
    except Exception:
        worker_snapshot = _WorkerHeartbeatSnapshot(
            alive=None,
            last_seen_at=None,
            alive_instances=None,
            seen_instances=None,
        )

    return _OperationalMetricsSnapshot(
        db_alive=db_alive,
        jobs_running=jobs_running,
        jobs_queued=jobs_queued,
        queue_length=queue_length,
        processing_jobs=processing_jobs,
        job_stuck_max_age_seconds=job_stuck_max_age_seconds,
        worker=worker_snapshot,
        queue_monitoring_available=queue_monitoring_available,
        queue_state=queue_state,
    )


async def _get_operational_metrics_snapshot_cached(request: Request) -> _OperationalMetricsSnapshot:
    cache = _get_operational_metrics_cache(request)
    now = _readiness_now()
    if cache.snapshot is not None and now < cache.expires_at_monotonic:
        return cache.snapshot

    async with cache.get_lock():
        now = _readiness_now()
        if cache.snapshot is not None and now < cache.expires_at_monotonic:
            return cache.snapshot

        snapshot = await _collect_operational_metrics_snapshot(request)
        cache.snapshot = snapshot
        cache.expires_at_monotonic = now + _OPERATIONAL_METRICS_CACHE_TTL_SECONDS
        return snapshot


async def _database_ready_cached(request: Request) -> bool:
    cache = _get_readiness_db_cache(request)
    now = _readiness_now()
    if cache.ready is not None and now < cache.expires_at_monotonic:
        return cache.ready

    async with cache.get_lock():
        now = _readiness_now()
        if cache.ready is not None and now < cache.expires_at_monotonic:
            return cache.ready

        operational_snapshot = _peek_operational_metrics_snapshot(request, now_monotonic=now)
        if operational_snapshot is not None:
            cache.ready = operational_snapshot.db_alive
            cache.expires_at_monotonic = min(
                now + _READINESS_DB_CACHE_TTL_SECONDS,
                _get_operational_metrics_cache(request).expires_at_monotonic,
            )
            return operational_snapshot.db_alive

        ready = await _database_ready()
        cache.ready = ready
        cache.expires_at_monotonic = now + _READINESS_DB_CACHE_TTL_SECONDS
        return ready


async def _storage_ready() -> bool:
    try:
        await verify_storage_health()
        return True
    except Exception:
        return False


async def _storage_ready_cached(request: Request) -> bool:
    cache = _get_readiness_storage_cache(request)
    now = _readiness_now()
    if cache.ready is not None and now < cache.expires_at_monotonic:
        return cache.ready

    async with cache.get_lock():
        now = _readiness_now()
        if cache.ready is not None and now < cache.expires_at_monotonic:
            return cache.ready

        ready = await _storage_ready()
        cache.ready = ready
        cache.expires_at_monotonic = now + _READINESS_DB_CACHE_TTL_SECONDS
        return ready


async def _is_ready(request: Request) -> bool:
    return (
        _startup_ready(request)
        and await _database_ready_cached(request)
        and await _storage_ready_cached(request)
    )


def _processing_grace_active(request: Request, *, now_monotonic: float | None = None) -> bool:
    settings = get_settings()
    grace_seconds = max(0, int(settings.readiness_processing_grace_seconds))
    if grace_seconds == 0:
        return False

    started_at = getattr(request.app.state, "readiness_started_at_monotonic", None)
    if not isinstance(started_at, (int, float)):
        return False

    now = _readiness_now() if now_monotonic is None else now_monotonic
    return max(0.0, now - float(started_at)) < grace_seconds


def _worker_state(snapshot: _WorkerHeartbeatSnapshot) -> str:
    if snapshot.alive is None:
        return "unknown"
    if snapshot.alive:
        return "ready"
    if (snapshot.seen_instances or 0) > 0:
        return "stale"
    return "missing"


def _evaluate_job_processing_readiness(
    request: Request,
    *,
    api_ready: bool,
    queue_monitoring_available: bool,
    queue_state: str,
    worker_snapshot: _WorkerHeartbeatSnapshot,
    strict: bool,
    now_monotonic: float | None = None,
) -> _JobProcessingReadinessSnapshot:
    strict_job_processing_ready = (
        api_ready
        and queue_monitoring_available
        and queue_state in {"ready", "degraded"}
        and worker_snapshot.alive is True
    )
    grace_active = api_ready and not strict_job_processing_ready and _processing_grace_active(
        request,
        now_monotonic=now_monotonic,
    )
    job_processing_ready = strict_job_processing_ready or (grace_active and not strict)
    return _JobProcessingReadinessSnapshot(
        api_ready=api_ready,
        job_processing_ready=job_processing_ready,
        strict_job_processing_ready=strict_job_processing_ready,
        worker_state=_worker_state(worker_snapshot),
        queue_state=queue_state if queue_monitoring_available else "unavailable",
        grace_active=grace_active,
    )


async def _get_job_processing_readiness(
    request: Request,
    *,
    strict: bool,
) -> _JobProcessingReadinessSnapshot:
    api_ready = await _is_ready(request)
    snapshot = await _get_operational_metrics_snapshot_cached(request)
    return _evaluate_job_processing_readiness(
        request,
        api_ready=api_ready,
        queue_monitoring_available=snapshot.queue_monitoring_available,
        queue_state=snapshot.queue_state,
        worker_snapshot=snapshot.worker,
        strict=strict,
    )


def _probe_payload(status_value: str) -> dict[str, str]:
    return {
        "status": status_value,
        "service": _PROBE_SERVICE_NAME,
    }


def _set_readiness_status(response: Response, *, ready: bool) -> None:
    response.status_code = (
        status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    )


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> RawResponse:
    """Prometheus scrape endpoint. Not a health or readiness probe."""
    if not PROMETHEUS_CLIENT_AVAILABLE or generate_latest is None:
        logger.warning("metrics.scrape_unavailable", reason="prometheus_client_not_installed")
        raise HTTPException(
            status_code=503,
            detail="Prometheus metrics are unavailable because prometheus-client is not installed.",
        )

    settings = get_settings()
    if settings.metrics_auth_enabled:
        if not settings.metrics_auth_token:
            raise HTTPException(status_code=401, detail="Metrics auth token not configured.")
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token.")
        provided = auth_header[len("Bearer "):]
        if not secrets.compare_digest(provided, settings.metrics_auth_token):
            raise HTTPException(status_code=401, detail="Invalid metrics token.")

    await _refresh_operational_metrics(request)
    return RawResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
        headers={
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )


@router.get("/alive")
async def alive() -> dict:
    """Legacy liveness alias; confirms the process is running."""
    return {"status": "alive"}


@router.get("/")
async def root() -> dict:
    settings = get_settings()
    return {
        "message": f"{settings.app_name} Python backend skeleton",
        "status": "ok",
        "environment": settings.app_env,
    }


@router.get("/health")
async def health() -> dict[str, str]:
    """Public liveness probe; fast, dependency-free, and intentionally minimal."""
    return _probe_payload("ok")


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, str]:
    """Public readiness probe; returns ready only when traffic can be served safely."""
    if await _is_ready(request):
        _set_readiness_status(response, ready=True)
        return _probe_payload("ready")

    _set_readiness_status(response, ready=False)
    return _probe_payload("not_ready")


@router.get("/ready/processing")
async def ready_processing(
    request: Request,
    response: Response,
    strict: bool = False,
) -> dict[str, object]:
    """Readiness for background-job processing, separate from API/read readiness."""
    readiness = await _get_job_processing_readiness(request, strict=strict)
    _set_readiness_status(response, ready=readiness.job_processing_ready)

    status_value = "ready"
    if not readiness.job_processing_ready:
        status_value = "not_ready"
    elif readiness.grace_active and not readiness.strict_job_processing_ready:
        status_value = "warming_up"

    return {
        "status": status_value,
        "service": _PROBE_SERVICE_NAME,
        "apiReady": readiness.api_ready,
        "jobProcessingReady": readiness.job_processing_ready,
        "workerState": readiness.worker_state,
        "queueState": readiness.queue_state,
        "graceActive": readiness.grace_active,
        "strict": strict,
    }


@router.get("/health/internal", include_in_schema=False)
async def health_internal(
    request: Request,
    response: Response,
    _: AuthUserRead = Depends(require_superadmin),
) -> dict:
    """Protected diagnostics endpoint; richer than liveness/readiness probes."""
    startup_ready = _startup_ready(request)

    db_live = False
    storage_live = False
    jobs_running = 0
    jobs_queued = 0
    processing_jobs = 0
    queue_length = 0
    max_running_age_seconds = 0.0
    last_completed_at: str | None = None
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
            db_live = True

            running_row = await session.execute(
                select(func.count()).where(AnalysisJob.status == "running")
            )
            queued_row = await session.execute(
                select(func.count()).where(AnalysisJob.status == "queued")
            )
            jobs_running = running_row.scalar_one() or 0
            jobs_queued = queued_row.scalar_one() or 0

            last_row = await session.execute(
                select(AnalysisJob.finished_at)
                .where(AnalysisJob.status == "completed")
                .order_by(AnalysisJob.finished_at.desc())
                .limit(1)
            )
            last_ts = last_row.scalar_one_or_none()
            if last_ts:
                if last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=UTC)
                last_completed_at = last_ts.isoformat()

            oldest_started = await session.scalar(
                select(func.min(AnalysisJob.started_at)).where(
                    AnalysisJob.status == "running",
                    AnalysisJob.started_at.is_not(None),
                )
            )
            if oldest_started is not None:
                if oldest_started.tzinfo is None:
                    oldest_started = oldest_started.replace(tzinfo=UTC)
                max_running_age_seconds = max(
                    0.0,
                    (datetime.now(UTC) - oldest_started.astimezone(UTC)).total_seconds(),
                )
    except Exception:
        pass

    try:
        queue_length, processing_jobs = await get_analysis_job_queue_counts(getattr(request.app.state, "job_queue", None))
        queue_monitoring_available = getattr(request.app.state, "job_queue", None) is not None
    except Exception:
        queue_length = 0
        processing_jobs = 0
        queue_monitoring_available = False

    worker_snapshot = _WorkerHeartbeatSnapshot(
        alive=None,
        last_seen_at=None,
        alive_instances=None,
        seen_instances=None,
    )
    try:
        worker_snapshot = await _get_worker_heartbeat_snapshot(getattr(request.app.state, "job_queue", None))
    except Exception:
        worker_snapshot = _WorkerHeartbeatSnapshot(
            alive=None,
            last_seen_at=None,
            alive_instances=None,
            seen_instances=None,
        )

    storage_live = await _storage_ready_cached(request)
    api_ready = startup_ready and db_live and storage_live
    job_processing = _evaluate_job_processing_readiness(
        request,
        api_ready=api_ready,
        queue_monitoring_available=queue_monitoring_available,
        queue_state=_queue_runtime_state(getattr(request.app.state, "job_queue", None)),
        worker_snapshot=worker_snapshot,
        strict=True,
    )
    ready = api_ready and job_processing.strict_job_processing_ready
    _set_readiness_status(response, ready=ready)

    return {
        "status": "ok" if ready else "degraded",
        "service": _PROBE_SERVICE_NAME,
        "ready": ready,
        "apiReady": api_ready,
        "jobProcessingReady": job_processing.strict_job_processing_ready,
        "jobProcessingGraceActive": job_processing.grace_active,
        "startupChecks": request.app.state.startup_checks,
        "db": "ok" if db_live else "error",
        "storage": "ok" if storage_live else "error",
        "jobs": {
            "running": jobs_running,
            "queued": jobs_queued,
            "processing": processing_jobs,
            "queueLength": queue_length,
            "maxRunningAgeSeconds": round(max_running_age_seconds, 1),
            "lastCompletedAt": last_completed_at,
        },
        "queue": _queue_runtime_details(getattr(request.app.state, "job_queue", None)),
        "worker": {
            "alive": worker_snapshot.alive,
            "state": job_processing.worker_state,
            "lastSeenAt": worker_snapshot.last_seen_at,
            "aliveInstances": worker_snapshot.alive_instances,
            "seenInstances": worker_snapshot.seen_instances,
        },
        "queue": {
            "state": job_processing.queue_state,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
