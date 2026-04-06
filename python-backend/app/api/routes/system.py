from __future__ import annotations

import asyncio
import inspect
import ipaddress
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import Response as RawResponse
from sqlalchemy import case, func, select, text
import structlog

from app.api.deps import require_superadmin
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.metrics import (
    AUTH_PROTECTION_ENFORCED,
    BACKPRESSURE_CURRENT_CONCURRENT,
    BACKPRESSURE_CURRENT_QUEUED,
    BACKPRESSURE_CURRENT_RETRY_INFLIGHT,
    BACKPRESSURE_MAX_CONCURRENT,
    BACKPRESSURE_MAX_QUEUED,
    BACKPRESSURE_MAX_RETRY_INFLIGHT,
    DB_ALIVE,
    HEAVY_PROCESSING_JOBS,
    HEAVY_QUEUE_LENGTH,
    JOBS_QUEUED,
    JOBS_RUNNING,
    JOB_FAIL_RATE,
    JOB_STUCK_MAX_AGE_SECONDS,
    JOB_DURATION_SECONDS_AVG,
    JOB_DURATION_SECONDS_P95,
    PROMETHEUS_CLIENT_AVAILABLE,
    PROCESSING_JOBS,
    QUEUE_DEAD_LETTER_ACTIVE,
    QUEUE_LENGTH,
    QUEUE_SCHEDULED_RETRY,
    QUEUE_SCHEDULED_RETRY_DUE_NOW,
    REDIS_RUNTIME_AVAILABLE,
    REDIS_RUNTIME_DEGRADED,
    STORAGE_READY,
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
from app.worker.queue import (
    DLQ_ACTIVE_SET_KEY,
    RETRY_QUEUE_KEY,
    get_analysis_job_queue_counts,
)
from app.worker.heavy_queue import get_heavy_job_queue_counts

router = APIRouter()
logger = structlog.get_logger(__name__)
_PROBE_SERVICE_NAME = "python-backend"
_READINESS_DB_CACHE_TTL_SECONDS = 2.0
_OPERATIONAL_METRICS_CACHE_TTL_SECONDS = 5.0
_SYSTEM_STATE_READY = "ready"
_SYSTEM_STATE_DEGRADED = "degraded"
_SYSTEM_STATE_UNAVAILABLE = "unavailable"
_SYSTEM_STATE_SEVERITY = {
    _SYSTEM_STATE_READY: 0,
    _SYSTEM_STATE_DEGRADED: 1,
    _SYSTEM_STATE_UNAVAILABLE: 2,
}

def _is_ip_allowlisted(client_ip: str | None, allowlist: str) -> bool:
    """Return True if client_ip matches any entry in a comma-separated IP/CIDR allowlist."""
    if not client_ip:
        return False
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowlist.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


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
class _AuthProtectionSnapshot:
    state: str
    enforced: bool
    source: str | None


@dataclass(frozen=True)
class _SystemStateSnapshot:
    state: str
    ready: bool
    healthy: bool
    startup_state: str
    api_state: str
    processing_state: str
    redis_state: str
    db_state: str
    storage_state: str
    queue_state: str
    worker_state: str
    auth_protection: _AuthProtectionSnapshot
    operational: "_OperationalMetricsSnapshot"
    job_processing: "_JobProcessingReadinessSnapshot"


@dataclass(frozen=True)
class _OperationalMetricsSnapshot:
    db_alive: bool = False
    jobs_running: int = 0
    jobs_queued: int = 0
    queue_length: int = 0
    processing_jobs: int = 0
    heavy_queue_length: int = 0
    heavy_processing_jobs: int = 0
    job_stuck_max_age_seconds: float = 0.0
    worker: _WorkerHeartbeatSnapshot = field(
        default_factory=lambda: _WorkerHeartbeatSnapshot(
            alive=None,
            last_seen_at=None,
            alive_instances=None,
            seen_instances=None,
        )
    )
    retry_queued_jobs: int = 0
    retry_inflight_jobs: int = 0
    dead_letter_jobs: int = 0
    oldest_queued_age_seconds: float = 0.0
    retry_scheduled: int | None = None
    retry_due_now: int | None = None
    dlq_active: int | None = None
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


@dataclass(frozen=True)
class _DatabaseJobSnapshot:
    jobs_running: int = 0
    jobs_queued: int = 0
    retry_queued_jobs: int = 0
    retry_inflight_jobs: int = 0
    dead_letter_jobs: int = 0
    max_running_age_seconds: float = 0.0
    oldest_queued_age_seconds: float = 0.0


def _normalize_system_state(value: str | None) -> str:
    if value in _SYSTEM_STATE_SEVERITY:
        return str(value)
    return _SYSTEM_STATE_UNAVAILABLE


def _worst_system_state(*states: str | None) -> str:
    normalized = [_normalize_system_state(state) for state in states if state is not None]
    if not normalized:
        return _SYSTEM_STATE_UNAVAILABLE
    return max(normalized, key=lambda item: _SYSTEM_STATE_SEVERITY[item])


def _state_from_ready_flag(ready: bool) -> str:
    return _SYSTEM_STATE_READY if ready else _SYSTEM_STATE_UNAVAILABLE


def _state_is_servable(state: str) -> bool:
    return _normalize_system_state(state) in {_SYSTEM_STATE_READY, _SYSTEM_STATE_DEGRADED}


def _state_is_healthy(state: str) -> bool:
    return _normalize_system_state(state) != _SYSTEM_STATE_UNAVAILABLE


def _queue_runtime_state(job_queue) -> str:
    if job_queue is None:
        return _SYSTEM_STATE_UNAVAILABLE
    status_factory = getattr(job_queue, "runtime_status", None)
    if callable(status_factory):
        if inspect.iscoroutinefunction(status_factory):
            return _SYSTEM_STATE_UNAVAILABLE
        try:
            status = status_factory()
            if inspect.isawaitable(status):
                return _SYSTEM_STATE_UNAVAILABLE
            state = getattr(status, "state", None)
            if isinstance(state, str) and state in _SYSTEM_STATE_SEVERITY:
                return state
        except Exception:
            return _SYSTEM_STATE_UNAVAILABLE
    return _SYSTEM_STATE_READY


def _queue_runtime_details(job_queue) -> dict[str, object] | None:
    if job_queue is None:
        return None
    status_factory = getattr(job_queue, "runtime_status", None)
    if not callable(status_factory):
        return None
    if inspect.iscoroutinefunction(status_factory):
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


async def _probe_runtime_state(client) -> str:
    if client is None:
        return _SYSTEM_STATE_UNAVAILABLE

    runtime_state = _queue_runtime_state(client)
    if runtime_state in {_SYSTEM_STATE_READY, _SYSTEM_STATE_DEGRADED}:
        return runtime_state

    ping = getattr(client, "ping", None)
    if not callable(ping):
        return _SYSTEM_STATE_UNAVAILABLE

    try:
        ping_result = ping()
        if inspect.isawaitable(ping_result):
            await ping_result
        return _SYSTEM_STATE_READY
    except Exception:
        return _SYSTEM_STATE_UNAVAILABLE


async def _get_auth_protection_snapshot(request: Request) -> _AuthProtectionSnapshot:
    auth_store = getattr(request.app.state, "auth_token_store", None)
    source = "authTokenStore"
    if auth_store is None:
        auth_store = getattr(request.app.state, "job_queue", None)
        source = "jobQueueSharedStore" if auth_store is not None else None

    state = await _probe_runtime_state(auth_store)
    return _AuthProtectionSnapshot(
        state=state,
        enforced=state in {_SYSTEM_STATE_READY, _SYSTEM_STATE_DEGRADED},
        source=source,
    )


async def _refresh_operational_metrics(request: Request) -> None:
    """Refresh DB/worker/job gauges before each Prometheus scrape (C5).

    Failures are silently swallowed; a missing gauge value is better than a
    broken scrape endpoint.
    """
    system_snapshot = await _collect_system_state_snapshot(request)
    snapshot = system_snapshot.operational
    DB_ALIVE.set(1 if snapshot.db_alive else 0)
    STORAGE_READY.set(1 if system_snapshot.storage_state == _SYSTEM_STATE_READY else 0)
    REDIS_RUNTIME_AVAILABLE.set(1 if _state_is_servable(system_snapshot.redis_state) else 0)
    REDIS_RUNTIME_DEGRADED.set(1 if system_snapshot.redis_state == _SYSTEM_STATE_DEGRADED else 0)
    AUTH_PROTECTION_ENFORCED.set(1 if system_snapshot.auth_protection.enforced else 0)
    JOBS_RUNNING.set(snapshot.jobs_running)
    JOBS_QUEUED.set(snapshot.jobs_queued)
    QUEUE_LENGTH.set(snapshot.queue_length)
    PROCESSING_JOBS.set(snapshot.processing_jobs)
    HEAVY_QUEUE_LENGTH.set(snapshot.heavy_queue_length)
    HEAVY_PROCESSING_JOBS.set(snapshot.heavy_processing_jobs)
    QUEUE_SCHEDULED_RETRY.set(snapshot.retry_scheduled or 0)
    QUEUE_SCHEDULED_RETRY_DUE_NOW.set(snapshot.retry_due_now or 0)
    QUEUE_DEAD_LETTER_ACTIVE.set(snapshot.dlq_active or 0)
    settings = get_settings()
    BACKPRESSURE_CURRENT_CONCURRENT.set(snapshot.processing_jobs + snapshot.heavy_processing_jobs)
    BACKPRESSURE_CURRENT_QUEUED.set(snapshot.queue_length + snapshot.heavy_queue_length)
    BACKPRESSURE_CURRENT_RETRY_INFLIGHT.set(snapshot.retry_inflight_jobs)
    BACKPRESSURE_MAX_CONCURRENT.set(settings.effective_backpressure_max_concurrent_jobs)
    BACKPRESSURE_MAX_QUEUED.set(settings.effective_backpressure_max_queued_jobs)
    BACKPRESSURE_MAX_RETRY_INFLIGHT.set(settings.effective_backpressure_max_retry_inflight)
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


_WORKER_NOT_ALIVE_LOG_INTERVAL_SECONDS = 60.0


def _log_worker_not_alive_if_due(request: Request, *, worker_alive, worker_state_str, seen_instances, last_seen_at) -> None:
    """Emit an ERROR log when the worker is not alive, at most once per minute."""
    now = _readiness_now()
    last_logged = getattr(request.app.state, "_worker_not_alive_last_logged", 0.0)
    if now - last_logged < _WORKER_NOT_ALIVE_LOG_INTERVAL_SECONDS:
        return
    request.app.state._worker_not_alive_last_logged = now
    logger.error(
        "readiness.worker_not_alive",
        worker_alive=worker_alive,
        worker_state=worker_state_str,
        seen_instances=seen_instances,
        last_seen_at=last_seen_at,
    )


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


async def _query_job_counts(session) -> _DatabaseJobSnapshot:
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
            func.coalesce(
                func.sum(
                    case(
                        (
                            (AnalysisJob.status == "queued")
                            & (func.coalesce(AnalysisJob.retry_count, 0) > 0),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            AnalysisJob.status.in_(("queued", "running"))
                            & (
                                (func.coalesce(AnalysisJob.retry_count, 0) > 0)
                                | (func.coalesce(AnalysisJob.attempt_count, 0) > 1)
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(case((AnalysisJob.status == "dead_letter", 1), else_=0)),
                0,
            ),
        )
    )
    count_values = tuple(counts_row.one())
    if len(count_values) >= 5:
        jobs_running, jobs_queued, retry_queued_jobs, retry_inflight_jobs, dead_letter_jobs = count_values[:5]
    elif len(count_values) == 4:
        jobs_running, jobs_queued, retry_queued_jobs, dead_letter_jobs = count_values
        retry_inflight_jobs = retry_queued_jobs
    elif len(count_values) == 3:
        jobs_running, jobs_queued, dead_letter_jobs = count_values
        retry_queued_jobs = 0
        retry_inflight_jobs = 0
    else:
        jobs_running = jobs_queued = retry_queued_jobs = retry_inflight_jobs = dead_letter_jobs = 0

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

    oldest_queued_created_at = await session.scalar(
        select(func.min(AnalysisJob.created_at)).where(
            AnalysisJob.status == "queued",
            AnalysisJob.created_at.is_not(None),
        )
    )
    if oldest_queued_created_at is None:
        oldest_queued_age_seconds = 0.0
    else:
        if oldest_queued_created_at.tzinfo is None:
            oldest_queued_created_at = oldest_queued_created_at.replace(tzinfo=UTC)
        oldest_queued_age_seconds = max(
            0.0,
            (datetime.now(UTC) - oldest_queued_created_at.astimezone(UTC)).total_seconds(),
        )

    return _DatabaseJobSnapshot(
        jobs_running=int(jobs_running or 0),
        jobs_queued=int(jobs_queued or 0),
        retry_queued_jobs=int(retry_queued_jobs or 0),
        retry_inflight_jobs=int(retry_inflight_jobs or 0),
        dead_letter_jobs=int(dead_letter_jobs or 0),
        max_running_age_seconds=max_age_seconds,
        oldest_queued_age_seconds=oldest_queued_age_seconds,
    )


async def _query_queue_operational_counts(redis) -> tuple[int | None, int | None, int | None]:
    if redis is None:
        return None, None, None

    retry_scheduled = int(await redis.zcard(RETRY_QUEUE_KEY))
    retry_due_now = int(
        await redis.zcount(
            RETRY_QUEUE_KEY,
            min=0,
            max=int(datetime.now(UTC).timestamp() * 1000),
        )
    )
    dlq_active = int(await redis.scard(DLQ_ACTIVE_SET_KEY))
    return retry_scheduled, retry_due_now, dlq_active


async def _collect_operational_metrics_snapshot(request: Request) -> _OperationalMetricsSnapshot:
    db_alive = False
    jobs_running = 0
    jobs_queued = 0
    retry_queued_jobs = 0
    retry_inflight_jobs = 0
    dead_letter_jobs = 0
    queue_length = 0
    processing_jobs = 0
    heavy_queue_length = 0
    heavy_processing_jobs = 0
    job_stuck_max_age_seconds = 0.0
    oldest_queued_age_seconds = 0.0
    retry_scheduled = None
    retry_due_now = None
    dlq_active = None
    queue_monitoring_available = False
    queue_state = "unavailable"
    try:
        async with AsyncSessionFactory() as session:
            db_snapshot = await _query_job_counts(session)
            if isinstance(db_snapshot, tuple):
                jobs_running = int(db_snapshot[0]) if len(db_snapshot) > 0 else 0
                jobs_queued = int(db_snapshot[1]) if len(db_snapshot) > 1 else 0
                job_stuck_max_age_seconds = float(db_snapshot[2]) if len(db_snapshot) > 2 else 0.0
            else:
                jobs_running = db_snapshot.jobs_running
                jobs_queued = db_snapshot.jobs_queued
                retry_queued_jobs = db_snapshot.retry_queued_jobs
                retry_inflight_jobs = db_snapshot.retry_inflight_jobs
                dead_letter_jobs = db_snapshot.dead_letter_jobs
                job_stuck_max_age_seconds = db_snapshot.max_running_age_seconds
                oldest_queued_age_seconds = db_snapshot.oldest_queued_age_seconds
            db_alive = True
    except Exception:
        db_alive = False

    _store_readiness_db_cache(request, ready=db_alive)

    job_queue = getattr(request.app.state, "job_queue", None)
    queue_state = _queue_runtime_state(job_queue)
    if job_queue is not None:
        queue_metrics_collected = False
        try:
            queue_length, processing_jobs = await get_analysis_job_queue_counts(job_queue)
            queue_metrics_collected = True
        except Exception:
            queue_length = 0
            processing_jobs = 0
        try:
            heavy_queue_length, heavy_processing_jobs = await get_heavy_job_queue_counts(job_queue)
            queue_metrics_collected = True
        except Exception:
            heavy_queue_length = 0
            heavy_processing_jobs = 0
        queue_monitoring_available = queue_metrics_collected
        if not queue_monitoring_available:
            queue_state = "unavailable"
        else:
            try:
                retry_scheduled, retry_due_now, dlq_active = await _query_queue_operational_counts(job_queue)
            except Exception:
                retry_scheduled = None
                retry_due_now = None
                dlq_active = None

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
        heavy_queue_length=heavy_queue_length,
        heavy_processing_jobs=heavy_processing_jobs,
        job_stuck_max_age_seconds=job_stuck_max_age_seconds,
        worker=worker_snapshot,
        retry_queued_jobs=retry_queued_jobs,
        retry_inflight_jobs=retry_inflight_jobs,
        dead_letter_jobs=dead_letter_jobs,
        oldest_queued_age_seconds=oldest_queued_age_seconds,
        retry_scheduled=retry_scheduled,
        retry_due_now=retry_due_now,
        dlq_active=dlq_active,
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
    return (await _collect_system_state_snapshot(request)).ready


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
        return _SYSTEM_STATE_READY
    if (snapshot.seen_instances or 0) > 0:
        return "stale"
    return "missing"


def _worker_service_state(snapshot: _WorkerHeartbeatSnapshot) -> str:
    if snapshot.alive is None:
        return _SYSTEM_STATE_UNAVAILABLE
    if snapshot.alive:
        return _SYSTEM_STATE_READY
    return _SYSTEM_STATE_DEGRADED


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
    # Use api_state (startup/db/storage/auth) rather than snapshot.ready so
    # that the worker-liveness invariant does not collapse the apiReady field
    # in /ready/processing responses.
    snapshot = await _collect_system_state_snapshot(request)
    api_ready = _state_is_servable(snapshot.api_state)
    return _evaluate_job_processing_readiness(
        request,
        api_ready=api_ready,
        queue_monitoring_available=snapshot.operational.queue_monitoring_available,
        queue_state=snapshot.operational.queue_state,
        worker_snapshot=snapshot.operational.worker,
        strict=strict,
    )


async def _collect_system_state_snapshot(request: Request) -> _SystemStateSnapshot:
    startup_state = _state_from_ready_flag(_startup_ready(request))
    operational = await _get_operational_metrics_snapshot_cached(request)
    storage_state = _state_from_ready_flag(await _storage_ready_cached(request))
    db_state = _state_from_ready_flag(operational.db_alive)
    auth_protection = await _get_auth_protection_snapshot(request)
    api_state = _worst_system_state(
        startup_state,
        db_state,
        storage_state,
        auth_protection.state,
    )
    job_processing = _evaluate_job_processing_readiness(
        request,
        api_ready=_state_is_servable(api_state),
        queue_monitoring_available=operational.queue_monitoring_available,
        queue_state=operational.queue_state,
        worker_snapshot=operational.worker,
        strict=False,
    )

    queue_state = (
        operational.queue_state
        if operational.queue_monitoring_available
        else _SYSTEM_STATE_UNAVAILABLE
    )
    worker_state = _worker_service_state(operational.worker)
    processing_state = _worst_system_state(queue_state, worker_state)
    if job_processing.grace_active and not job_processing.strict_job_processing_ready:
        processing_state = _SYSTEM_STATE_DEGRADED
    redis_state = _worst_system_state(queue_state, auth_protection.state)
    state = _worst_system_state(api_state, processing_state)
    # Hard invariant: system is not READY without an alive worker and a
    # serviceable queue.  API can run, but readiness is denied.
    worker_alive = operational.worker.alive is True
    queue_ok = _state_is_healthy(queue_state)
    if not worker_alive:
        _log_worker_not_alive_if_due(
            request,
            worker_alive=operational.worker.alive,
            worker_state_str=_worker_state(operational.worker),
            seen_instances=operational.worker.seen_instances,
            last_seen_at=operational.worker.last_seen_at,
        )
    ready = _state_is_servable(api_state) and worker_alive and queue_ok
    healthy = _state_is_healthy(state)

    return _SystemStateSnapshot(
        state=state,
        ready=ready,
        healthy=healthy,
        startup_state=startup_state,
        api_state=api_state,
        processing_state=processing_state,
        redis_state=redis_state,
        db_state=db_state,
        storage_state=storage_state,
        queue_state=queue_state,
        worker_state=worker_state,
        auth_protection=auth_protection,
        operational=operational,
        job_processing=job_processing,
    )


def _probe_payload(status_value: str) -> dict[str, str]:
    return {
        "status": status_value,
        "service": _PROBE_SERVICE_NAME,
    }


def _public_dependency_summary(snapshot: _SystemStateSnapshot) -> dict[str, str]:
    return {
        "startup": snapshot.startup_state,
        "db": snapshot.db_state,
        "storage": snapshot.storage_state,
        "redis": snapshot.redis_state,
    }


def _public_probe_payload(snapshot: _SystemStateSnapshot) -> dict[str, object]:
    return {
        "status": snapshot.state,
        "service": _PROBE_SERVICE_NAME,
        "ready": snapshot.ready,
        "apiState": snapshot.api_state,
        "processingState": snapshot.processing_state,
        "dependencies": _public_dependency_summary(snapshot),
        "queue": {
            "state": snapshot.queue_state,
        },
        "worker": {
            "state": snapshot.job_processing.worker_state,
        },
        "security": {
            "authProtection": {
                "state": snapshot.auth_protection.state,
                "enforced": snapshot.auth_protection.enforced,
            },
        },
    }


def _set_probe_state_status(response: Response, *, state: str) -> None:
    response.status_code = (
        status.HTTP_200_OK
        if _state_is_healthy(state)
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )


@router.get("/metrics", include_in_schema=False)
@limiter.limit(get_settings().rate_limit_metrics)
async def metrics(request: Request) -> RawResponse:
    """Prometheus scrape endpoint. Not a health or readiness probe."""
    if not PROMETHEUS_CLIENT_AVAILABLE or generate_latest is None:
        logger.warning("metrics.scrape_unavailable", reason="prometheus_client_not_installed")
        raise HTTPException(
            status_code=503,
            detail="Prometheus metrics are unavailable because prometheus-client is not installed.",
        )

    settings = get_settings()
    if not settings.metrics_auth_enabled:
        logger.error("metrics.auth_disabled", app_env=settings.app_env)
        raise HTTPException(
            status_code=503,
            detail="Metrics endpoint is unavailable because authentication is disabled.",
        )

    # Enforce IP allowlist when configured (defense-in-depth before token check).
    # Recommended in production: METRICS_IP_ALLOWLIST=10.0.0.0/8,192.168.0.0/16
    allowlist = (settings.metrics_ip_allowlist or "").strip()
    if allowlist:
        client_ip = request.client.host if request.client else None
        if not _is_ip_allowlisted(client_ip, allowlist):
            logger.warning(
                "metrics.access_denied",
                reason="ip_not_allowlisted",
                client_ip=client_ip,
                app_env=settings.app_env,
            )
            raise HTTPException(status_code=403, detail="Access denied: client IP not in allowlist.")

    if not settings.metrics_auth_token:
        logger.warning("metrics.auth_denied", reason="token_not_configured")
        raise HTTPException(status_code=401, detail="Metrics auth token not configured.")
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        logger.warning(
            "metrics.auth_denied",
            reason="missing_bearer",
            client_ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    provided = auth_header[len("Bearer "):]
    if not secrets.compare_digest(provided, settings.metrics_auth_token):
        logger.warning(
            "metrics.auth_denied",
            reason="invalid_token",
            client_ip=request.client.host if request.client else None,
        )
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
async def health(request: Request, response: Response) -> dict[str, object]:
    """Public health probe; reports truthful runtime integrity without internal counts."""
    snapshot = await _collect_system_state_snapshot(request)
    _set_probe_state_status(response, state=snapshot.state)
    return _public_probe_payload(snapshot)


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, object]:
    """Public readiness probe; returns ready only when traffic can be served safely."""
    snapshot = await _collect_system_state_snapshot(request)
    ready_state = snapshot.state if snapshot.ready else _SYSTEM_STATE_UNAVAILABLE
    _set_probe_state_status(response, state=ready_state)
    return _public_probe_payload(snapshot)


@router.get("/ready/processing")
async def ready_processing(
    request: Request,
    response: Response,
    strict: bool = False,
) -> dict[str, object]:
    """Readiness for background-job processing, separate from API/read readiness."""
    readiness = await _get_job_processing_readiness(request, strict=strict)
    readiness_state = _SYSTEM_STATE_READY
    if not readiness.job_processing_ready:
        readiness_state = _SYSTEM_STATE_UNAVAILABLE
    elif readiness.grace_active and not readiness.strict_job_processing_ready:
        readiness_state = _SYSTEM_STATE_DEGRADED
    _set_probe_state_status(response, state=readiness_state)

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
    snapshot = await _collect_system_state_snapshot(request)
    operational = snapshot.operational
    queue_details = _queue_runtime_details(getattr(request.app.state, "job_queue", None)) or {}

    last_completed_at: str | None = None
    if operational.db_alive:
        try:
            async with AsyncSessionFactory() as session:
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
        except Exception:
            last_completed_at = None

    _set_probe_state_status(response, state=snapshot.state)
    queue_section = {
        "state": snapshot.queue_state,
        "monitoringAvailable": operational.queue_monitoring_available,
        "depth": {
            "durable": operational.queue_length,
            "processing": operational.processing_jobs,
            "heavyDurable": operational.heavy_queue_length,
            "heavyProcessing": operational.heavy_processing_jobs,
            "scheduledRetry": operational.retry_scheduled,
            "scheduledRetryDueNow": operational.retry_due_now,
            "deadLetterActive": operational.dlq_active,
        },
    }
    for key, value in queue_details.items():
        if key == "state":
            continue
        queue_section[key] = value

    return {
        "status": snapshot.state,
        "service": _PROBE_SERVICE_NAME,
        "ready": snapshot.ready,
        "healthy": snapshot.healthy,
        "apiReady": snapshot.ready,
        "apiState": snapshot.api_state,
        "jobProcessingReady": snapshot.job_processing.strict_job_processing_ready,
        "jobProcessingState": snapshot.processing_state,
        "jobProcessingGraceActive": snapshot.job_processing.grace_active,
        "startupChecks": request.app.state.startup_checks,
        "db": "ok" if operational.db_alive else "error",
        "storage": "ok" if snapshot.storage_state == _SYSTEM_STATE_READY else "error",
        "dependencies": {
            "startup": snapshot.startup_state,
            "db": snapshot.db_state,
            "storage": snapshot.storage_state,
            "redis": snapshot.redis_state,
        },
        "jobs": {
            "running": operational.jobs_running,
            "queued": operational.jobs_queued,
            "retryQueued": operational.retry_queued_jobs,
            "retryInflight": operational.retry_inflight_jobs,
            "deadLetter": operational.dead_letter_jobs,
            "processing": operational.processing_jobs,
            "queueLength": operational.queue_length,
            "heavyProcessing": operational.heavy_processing_jobs,
            "heavyQueueLength": operational.heavy_queue_length,
            "maxRunningAgeSeconds": round(operational.job_stuck_max_age_seconds, 1),
            "oldestQueuedAgeSeconds": round(operational.oldest_queued_age_seconds, 1),
            "lastCompletedAt": last_completed_at,
            "backpressure": {
                "currentConcurrent": operational.processing_jobs + operational.heavy_processing_jobs,
                "maxConcurrent": get_settings().effective_backpressure_max_concurrent_jobs,
                "currentQueued": operational.queue_length + operational.heavy_queue_length,
                "maxQueued": get_settings().effective_backpressure_max_queued_jobs,
                "currentRetryInflight": operational.retry_inflight_jobs,
                "maxRetryInflight": get_settings().effective_backpressure_max_retry_inflight,
            },
        },
        "worker": {
            "alive": operational.worker.alive,
            "state": snapshot.job_processing.worker_state,
            "serviceState": snapshot.worker_state,
            "lastSeenAt": operational.worker.last_seen_at,
            "aliveInstances": operational.worker.alive_instances,
            "seenInstances": operational.worker.seen_instances,
        },
        "security": {
            "authProtection": {
                "state": snapshot.auth_protection.state,
                "enforced": snapshot.auth_protection.enforced,
                "source": snapshot.auth_protection.source,
            },
        },
        "queue": queue_section,
        "timestamp": datetime.now(UTC).isoformat(),
    }
