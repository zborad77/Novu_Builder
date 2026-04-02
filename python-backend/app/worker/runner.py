"""Analysis job worker process (R-19).

Run as a standalone process (outside the web server):
    python -m app.worker.runner

The worker uses Redis leases rather than destructive BLPOP semantics:
    1. dequeue_analysis_job() atomically moves the payload into processing and
       assigns a worker-owned lease
    2. successful processing ACKs the lease
    3. crashed workers leave the lease behind and the reaper reconciles it with
       DB state before requeueing

DB remains the source of truth for job lifecycle:
    - queued -> running happens only in the DB
    - completed / failed is persisted only from a valid DB state
    - expired running jobs are reset to queued only by the lease reaper
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import sys
import time
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException

from app.core.config import get_settings, startup_failure_message
from app.core.logging import configure_logging
from app.core.metrics import PROMETHEUS_CLIENT_AVAILABLE, record_reaper_requeues
from app.core.redis_client import build_queue_redis_client_from_settings
from app.db.session import WorkerAsyncSessionFactory
from app.repositories.analysis_repository import AnalysisJobLeaseOwnershipError
from app.repositories.export_repository import ExportRepository
from app.repositories.final_proposal_repository import FinalProposalRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.proposal_draft_repository import ProposalDraftRepository
from app.services.analysis_service import AnalysisService
from app.services.export_service import ExportService
from app.services.photo_service import PhotoService
from app.services.project_service import ProjectService
from app.worker.heavy_queue import (
    InvalidHeavyJobPayloadError,
    LeasedHeavyJob,
    LostHeavyJobLeaseError,
    ack_heavy_job,
    dequeue_heavy_job,
    drop_expired_heavy_job,
    get_expired_heavy_job_leases,
    requeue_expired_heavy_job,
    renew_heavy_job_lease,
    validate_heavy_job_payload,
)
from app.worker.heartbeat import (
    clear_local_worker_heartbeat,
    clear_worker_heartbeat,
    WORKER_HEARTBEAT_INTERVAL,
    WORKER_HEARTBEAT_KEY_PREFIX,
    WORKER_HEARTBEAT_LEGACY_KEY,
    WORKER_HEARTBEAT_TTL,
    build_worker_instance_id,
    write_local_worker_heartbeat,
    worker_heartbeat_key,
    write_worker_heartbeat,
)
from app.worker.queue import (
    InvalidAnalysisJobPayloadError,
    LeasedAnalysisJob,
    LostAnalysisJobLeaseError,
    ack_analysis_job,
    dequeue_analysis_job,
    drop_expired_analysis_job,
    get_expired_analysis_job_leases,
    move_analysis_job_to_dlq,
    promote_scheduled_analysis_jobs,
    renew_analysis_job_lease,
    requeue_expired_analysis_job,
    schedule_analysis_job_retry,
    validate_analysis_job_payload,
)

logger = structlog.get_logger(__name__)

try:
    from prometheus_client import start_http_server
except ModuleNotFoundError:
    start_http_server = None


class WorkerPayloadValidationError(ValueError):
    """Raised when a queued worker payload is structurally invalid."""


class WorkerJobExecutionError(RuntimeError):
    """Job-level execution failure that must not be treated as a loop/Redis fault."""

    def __init__(
        self,
        *,
        job_id: str,
        project_id: str,
        organization_id: str | None,
        cause: Exception,
    ) -> None:
        super().__init__(str(cause))
        self.job_id = job_id
        self.project_id = project_id
        self.organization_id = organization_id
        self.cause = cause


class HeavyWorkerJobExecutionError(RuntimeError):
    """Heavy-work execution failure that must not be treated as a queue fault."""

    def __init__(
        self,
        *,
        job_type: str,
        project_id: str,
        organization_id: str | None,
        export_id: str | None,
        photo_id: str | None,
        cause: Exception,
    ) -> None:
        super().__init__(str(cause))
        self.job_type = job_type
        self.project_id = project_id
        self.organization_id = organization_id
        self.export_id = export_id
        self.photo_id = photo_id
        self.cause = cause


@dataclass(frozen=True)
class WorkerJobSpec:
    job_id: str
    project_id: str
    organization_id: str | None
    is_superadmin_context: bool


@dataclass(frozen=True)
class HeavyWorkerJobSpec:
    job_type: str
    project_id: str
    organization_id: str | None
    export_id: str | None
    photo_id: str | None


@dataclass
class WorkerRuntime:
    settings: object
    redis_url: str
    redis: object
    worker_instance_id: str
    heartbeat_key: str
    job_executor: "WorkerJobExecutor"
    heavy_job_executor: "HeavyWorkerJobExecutor"
    worker_concurrency: int
    job_lease_timeout_seconds: int
    lease_reap_interval_seconds: int
    concurrency_limiter: asyncio.Semaphore
    inflight_tasks: set[asyncio.Task[None]]
    worker_heavy_concurrency: int = 0
    heavy_job_lease_timeout_seconds: int = 1800
    heavy_lease_reap_interval_seconds: int = 30
    heavy_concurrency_limiter: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))
    inflight_heavy_tasks: set[asyncio.Task[None]] = field(default_factory=set)
    last_heartbeat: float = 0.0
    last_export_cleanup: float = field(default_factory=time.monotonic)
    last_photo_cleanup: float = field(default_factory=time.monotonic)
    last_lease_reap: float = field(default_factory=time.monotonic)
    last_heavy_lease_reap: float = field(default_factory=time.monotonic)


def _extract_payload_keys(payload: object) -> list[str] | None:
    if not isinstance(payload, dict):
        return None
    try:
        return sorted(str(key) for key in payload.keys())
    except Exception:
        return None


def _extract_candidate_job_id(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    job_id = payload.get("job_id")
    if not isinstance(job_id, str):
        return None
    normalized = job_id.strip()
    return normalized or None


def _validate_worker_payload(payload: object):
    try:
        return validate_analysis_job_payload(payload)
    except InvalidAnalysisJobPayloadError as exc:
        raise WorkerPayloadValidationError(str(exc)) from exc


def _validate_heavy_worker_payload(payload: object):
    try:
        return validate_heavy_job_payload(payload)
    except InvalidHeavyJobPayloadError as exc:
        raise WorkerPayloadValidationError(str(exc)) from exc


def _build_worker_analysis_service(settings) -> AnalysisService:
    return AnalysisService(
        repository=None,  # type: ignore[arg-type]  # worker-only methods create their own session
        photo_repository=None,  # type: ignore[arg-type]  # worker-only methods create their own session
        provider_key=settings.ai_analysis_provider,
    )


class WorkerJobExecutor:
    """Isolated single-job executor."""

    def __init__(self, settings, *, service_factory=None) -> None:
        self.settings = settings
        self._service_factory = service_factory or _build_worker_analysis_service

    def _new_service(self) -> AnalysisService:
        return self._service_factory(self.settings)

    async def _parse_job_spec(self, payload: object) -> WorkerJobSpec | None:
        service = self._new_service()
        try:
            validated = _validate_worker_payload(payload)
        except WorkerPayloadValidationError as exc:
            candidate_job_id = _extract_candidate_job_id(payload)
            logger.error(
                "worker.invalid_payload",
                reason=str(exc),
                job_id=candidate_job_id,
                payload_keys=_extract_payload_keys(payload),
            )
            if candidate_job_id is not None:
                await service.fail_job_before_processing(
                    candidate_job_id,
                    message=f"Invalid worker payload: {exc}",
                )
            return None

        return WorkerJobSpec(
            job_id=validated.job_id,
            project_id=validated.project_id,
            organization_id=validated.organization_id,
            is_superadmin_context=validated.is_superadmin_context,
        )

    async def execute_payload(self, payload: object, *, job_queue=None) -> None:
        job = await self._parse_job_spec(payload)
        if job is None:
            return

        log = logger.bind(job_id=job.job_id, project_id=job.project_id)
        log.info("worker.dequeued", organization_id=job.organization_id)
        service = self._new_service()
        try:
            result = await service.execute_job(
                job.job_id,
                job.project_id,
                job.organization_id,
                is_superadmin_context=job.is_superadmin_context,
                job_queue=job_queue,
            )
            log.info("worker.job_done", status=result.disposition)
        except HTTPException as exc:
            log.warning(
                "worker.job_rejected_by_policy",
                status_code=exc.status_code,
                detail=exc.detail,
            )
        except Exception as exc:
            raise WorkerJobExecutionError(
                job_id=job.job_id,
                project_id=job.project_id,
                organization_id=job.organization_id,
                cause=exc,
            ) from exc

    async def execute_lease(self, lease: LeasedAnalysisJob, *, job_queue=None):
        job = await self._parse_job_spec(lease.payload)
        if job is None:
            return

        log = logger.bind(
            job_id=job.job_id,
            project_id=job.project_id,
            tenant_id=job.organization_id,
            lease_token=lease.token,
            worker_id=lease.worker_id,
        )
        log.info("worker.dequeued", organization_id=job.organization_id)
        service = self._new_service()
        try:
            result = await service.execute_job(
                job.job_id,
                job.project_id,
                job.organization_id,
                is_superadmin_context=job.is_superadmin_context,
                lease_token=lease.token,
                worker_id=lease.worker_id,
                job_queue=job_queue,
            )
            log.info("worker.job_done", status=result.disposition)
            return result
        except HTTPException as exc:
            log.warning(
                "worker.job_rejected_by_policy",
                status_code=exc.status_code,
                detail=exc.detail,
            )
        except AnalysisJobLeaseOwnershipError:
            raise
        except Exception as exc:
            raise WorkerJobExecutionError(
                job_id=job.job_id,
                project_id=job.project_id,
                organization_id=job.organization_id,
                cause=exc,
            ) from exc


class HeavyWorkerJobExecutor:
    async def _parse_job_spec(self, payload: object) -> HeavyWorkerJobSpec | None:
        try:
            validated = _validate_heavy_worker_payload(payload)
        except WorkerPayloadValidationError as exc:
            logger.error(
                "worker.heavy_invalid_payload",
                reason=str(exc),
                payload_keys=_extract_payload_keys(payload),
            )
            return None

        return HeavyWorkerJobSpec(
            job_type=validated.job_type,
            project_id=validated.project_id,
            organization_id=validated.organization_id,
            export_id=validated.export_id,
            photo_id=validated.photo_id,
        )

    async def execute_lease(self, lease: LeasedHeavyJob) -> None:
        job = await self._parse_job_spec(lease.payload)
        if job is None:
            return

        log = logger.bind(
            heavy_job_type=job.job_type,
            project_id=job.project_id,
            tenant_id=job.organization_id,
            lease_token=lease.token,
            worker_id=lease.worker_id,
            export_id=job.export_id,
            photo_id=job.photo_id,
        )
        log.info("worker.heavy_dequeued")
        try:
            async with WorkerAsyncSessionFactory() as session:
                if job.job_type == "export_generate":
                    project_service = ProjectService(
                        ProjectRepository(session),
                        ProposalDraftRepository(session),
                        FinalProposalRepository(session),
                        ExportService(ExportRepository(session)),
                    )
                    case_detail = await project_service.get_project_detail(job.project_id)
                    if case_detail is None:
                        raise ValueError("Project detail is required for export generation.")
                    export_service = ExportService(ExportRepository(session))
                    await export_service.process_export_by_id(job.export_id, case_detail=case_detail)
                elif job.job_type == "photo_variant_processing":
                    photo_service = PhotoService(PhotoRepository(session))
                    await photo_service.process_photo_variants_by_id(job.photo_id)
                else:
                    raise ValueError(f"Unsupported heavy job type: {job.job_type!r}")
            log.info("worker.heavy_job_done")
        except Exception as exc:
            raise HeavyWorkerJobExecutionError(
                job_type=job.job_type,
                project_id=job.project_id,
                organization_id=job.organization_id,
                export_id=job.export_id,
                photo_id=job.photo_id,
                cause=exc,
            ) from exc


async def _process_one(payload: dict, settings) -> None:
    await WorkerJobExecutor(settings).execute_payload(payload)


_HEARTBEAT_KEY_PREFIX = WORKER_HEARTBEAT_KEY_PREFIX
_HEARTBEAT_LEGACY_KEY = WORKER_HEARTBEAT_LEGACY_KEY
_HEARTBEAT_INTERVAL = WORKER_HEARTBEAT_INTERVAL
_HEARTBEAT_TTL = WORKER_HEARTBEAT_TTL
_EXPORT_CLEANUP_INTERVAL_SECONDS = 300
_PHOTO_DELETE_CLEANUP_INTERVAL_SECONDS = 30
_IDLE_LOOP_SLEEP_SECONDS = 1.0
_LEASE_RENEWAL_INTERVAL_SECONDS = 30.0
_LEASE_REAPER_BATCH_SIZE = 100


def _is_strict_worker_environment(settings) -> bool:
    return settings.app_env.lower() not in ("development", "test")


def _build_worker_redis(settings, redis_url: str):
    return build_queue_redis_client_from_settings(
        settings,
        redis_url=redis_url,
        socket_timeout=None,
        client_name="novu-worker",
    )


def _configured_worker_concurrency(settings) -> int:
    raw = getattr(settings, "worker_concurrency", 1)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1
    return max(1, value)


def _configured_heavy_worker_concurrency(settings) -> int:
    raw = getattr(settings, "worker_heavy_concurrency", 0)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def _configured_job_lease_timeout_seconds(settings) -> int:
    raw = getattr(settings, "worker_job_lease_timeout_seconds", 600)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 600
    return max(60, value)


def _configured_heavy_job_lease_timeout_seconds(settings) -> int:
    raw = getattr(settings, "worker_heavy_job_lease_timeout_seconds", 1800)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1800
    return max(60, value)


def _configured_job_reap_interval_seconds(settings) -> int:
    raw = getattr(settings, "worker_job_reap_interval_seconds", 30)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 30
    return max(5, value)


def _configured_heavy_job_reap_interval_seconds(settings) -> int:
    raw = getattr(settings, "worker_heavy_job_reap_interval_seconds", 30)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 30
    return max(5, value)


async def _verify_worker_redis_startup(redis, settings, redis_url: str) -> None:
    try:
        await redis.ping()  # type: ignore[misc]  # redis.asyncio stubs
    except Exception as exc:
        if _is_strict_worker_environment(settings):
            try:
                await redis.aclose()
            except Exception as close_exc:
                logger.warning("worker.redis_close_failed", error=str(close_exc))
            raise RuntimeError(
                startup_failure_message(
                    "redis",
                    f"Worker Redis is unavailable in APP_ENV={settings.app_env!r}. "
                    f"Fix REDIS_URL/connectivity before startup (target={redis_url!r}).",
                )
            ) from exc
        logger.warning(
            "worker.redis_startup_unavailable",
            error=str(exc),
            fail_fast=False,
        )


async def _write_heartbeat_if_due(runtime: WorkerRuntime, *, now_monotonic: float | None = None) -> None:
    current = time.monotonic() if now_monotonic is None else now_monotonic
    if current - runtime.last_heartbeat < _HEARTBEAT_INTERVAL:
        return

    now = datetime.now(UTC)
    await write_worker_heartbeat(
        runtime.redis,
        runtime.worker_instance_id,
        now=now,
    )
    await write_local_worker_heartbeat(
        runtime.worker_instance_id,
        now=now,
    )
    runtime.last_heartbeat = current


async def _run_export_cleanup_if_due(runtime: WorkerRuntime, *, now_monotonic: float | None = None) -> None:
    current = time.monotonic() if now_monotonic is None else now_monotonic
    if current - runtime.last_export_cleanup < _EXPORT_CLEANUP_INTERVAL_SECONDS:
        return

    async with WorkerAsyncSessionFactory() as session:
        deleted_count = await ExportService(ExportRepository(session)).delete_expired_exports()

    runtime.last_export_cleanup = current
    logger.info("worker.export_cleanup_completed", deleted_count=deleted_count)


async def _run_photo_cleanup_if_due(runtime: WorkerRuntime, *, now_monotonic: float | None = None) -> None:
    current = time.monotonic() if now_monotonic is None else now_monotonic
    if current - runtime.last_photo_cleanup < _PHOTO_DELETE_CLEANUP_INTERVAL_SECONDS:
        return

    async with WorkerAsyncSessionFactory() as session:
        deleted_count = await PhotoService(PhotoRepository(session)).cleanup_pending_deletes()

    runtime.last_photo_cleanup = current
    logger.info("worker.photo_cleanup_completed", deleted_count=deleted_count)


def _seconds_until_next_heartbeat(runtime: WorkerRuntime, *, now_monotonic: float | None = None) -> float:
    current = time.monotonic() if now_monotonic is None else now_monotonic
    elapsed = current - runtime.last_heartbeat
    return max(0.0, _HEARTBEAT_INTERVAL - elapsed)


async def _acquire_slot(runtime: WorkerRuntime, limiter: asyncio.Semaphore) -> bool:
    if not limiter.locked():
        await limiter.acquire()
        return True

    timeout = _seconds_until_next_heartbeat(runtime)
    if timeout <= 0:
        return False

    try:
        await asyncio.wait_for(limiter.acquire(), timeout=timeout)
    except asyncio.TimeoutError:
        return False
    return True


async def _acquire_job_slot(runtime: WorkerRuntime) -> bool:
    return await _acquire_slot(runtime, runtime.concurrency_limiter)


async def _acquire_heavy_job_slot(runtime: WorkerRuntime) -> bool:
    return await _acquire_slot(runtime, runtime.heavy_concurrency_limiter)


async def _renew_job_lease_loop(runtime: WorkerRuntime, lease: LeasedAnalysisJob) -> None:
    current_lease = lease
    service = _build_worker_analysis_service(runtime.settings)
    renewal_interval = min(
        _LEASE_RENEWAL_INTERVAL_SECONDS,
        max(5.0, runtime.job_lease_timeout_seconds / 3),
    )
    while True:
        await asyncio.sleep(renewal_interval)
        try:
            current_lease = await renew_analysis_job_lease(
                runtime.redis,
                current_lease,
                lease_timeout_seconds=runtime.job_lease_timeout_seconds,
            )
            refreshed = await service.refresh_job_lease_heartbeat(
                current_lease.job_id,
                lease_token=current_lease.token,
                worker_id=current_lease.worker_id,
                leased_at_ms=current_lease.leased_at_ms,
            )
            if not refreshed:
                logger.warning(
                    "worker.lease_lost_db_heartbeat",
                    job_id=lease.job_id,
                    lease_token=lease.token,
                    worker_id=lease.worker_id,
                )
                return
        except LostAnalysisJobLeaseError as exc:
            logger.warning(
                "worker.lease_lost",
                job_id=lease.job_id,
                lease_token=lease.token,
                error=str(exc),
            )
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "worker.lease_renewal_failed",
                job_id=lease.job_id,
                lease_token=lease.token,
                error=str(exc),
            )


async def _resolve_job_failure_finalization(
    runtime: WorkerRuntime,
    lease: LeasedAnalysisJob,
    *,
    cause: Exception,
) -> tuple[str, datetime | None, int, str | None]:
    service = _build_worker_analysis_service(runtime.settings)
    try:
        result = await service.recover_job_after_worker_error(
            lease=lease,
            cause=cause,
        )
    except AnalysisJobLeaseOwnershipError:
        return "ack", None, 0, None
    except Exception as recovery_exc:
        fallback_reason = str(cause).strip() or type(cause).__name__
        logger.error(
            "worker.job_recovery_failed",
            job_id=lease.job_id,
            tenant_id=lease.organization_id,
            lease_token=lease.token,
            worker_id=lease.worker_id,
            original_error_type=type(cause).__name__,
            original_error=fallback_reason,
            recovery_error_type=type(recovery_exc).__name__,
            recovery_error=str(recovery_exc),
            exc_info=True,
        )
        return "dlq", None, 0, fallback_reason

    attempt_count = int(getattr(result, "attempt_count", 0) or 0)
    retry_at = getattr(result, "retry_at", None)
    failure_reason = getattr(result, "failure_reason", None)
    if result.disposition == "retry_scheduled" and retry_at is not None:
        return "retry", retry_at, attempt_count, failure_reason
    if result.disposition == "dead_lettered":
        return "dlq", None, attempt_count, failure_reason
    return "ack", None, attempt_count, failure_reason


async def _run_job_task(runtime: WorkerRuntime, lease: LeasedAnalysisJob) -> None:
    renewal_task = asyncio.create_task(_renew_job_lease_loop(runtime, lease))
    finalize_action = "ack"
    retry_at: datetime | None = None
    dlq_reason: str | None = None
    attempt_count = 0
    try:
        result = await runtime.job_executor.execute_lease(lease, job_queue=runtime.redis)
        finalize_action = "ack"
        if result is not None:
            attempt_count = int(getattr(result, "attempt_count", 0) or 0)
            retry_at = getattr(result, "retry_at", None)
            dlq_reason = getattr(result, "failure_reason", None)
            if result.disposition == "retry_scheduled":
                finalize_action = "retry"
            elif result.disposition == "dead_lettered":
                finalize_action = "dlq"
    except asyncio.CancelledError:
        raise
    except AnalysisJobLeaseOwnershipError as exc:
        logger.warning(
            "worker.job_aborted_lost_db_lease",
            job_id=lease.job_id,
            tenant_id=lease.organization_id,
            lease_token=lease.token,
            worker_id=lease.worker_id,
            status="aborted",
            error=str(exc),
        )
        finalize_action = "ack"
    except WorkerJobExecutionError as exc:
        logger.error(
            "worker.job_unhandled_error",
            job_id=exc.job_id,
            project_id=exc.project_id,
            tenant_id=exc.organization_id,
            error_type=type(exc.cause).__name__,
            error=str(exc.cause),
            lease_token=lease.token,
            worker_id=lease.worker_id,
            status="failed",
            exc_info=True,
        )
        finalize_action, retry_at, attempt_count, dlq_reason = await _resolve_job_failure_finalization(
            runtime,
            lease,
            cause=exc.cause,
        )
    except InvalidAnalysisJobPayloadError as exc:
        logger.error(
            "worker.invalid_queue_payload",
            job_id=lease.job_id,
            tenant_id=lease.organization_id,
            worker_id=lease.worker_id,
            status="failed",
            error=str(exc),
            lease_token=lease.token,
        )
        finalize_action = "ack"
    except Exception as exc:
        logger.error(
            "worker.job_task_error",
            job_id=lease.job_id,
            tenant_id=lease.organization_id,
            payload_keys=_extract_payload_keys(lease.payload),
            error_type=type(exc).__name__,
            error=str(exc),
            lease_token=lease.token,
            worker_id=lease.worker_id,
            status="failed",
            exc_info=True,
        )
        finalize_action, retry_at, attempt_count, dlq_reason = await _resolve_job_failure_finalization(
            runtime,
            lease,
            cause=exc,
        )
    finally:
        renewal_task.cancel()
        await asyncio.gather(renewal_task, return_exceptions=True)
        if finalize_action == "ack":
            try:
                acked = await ack_analysis_job(runtime.redis, lease)
                if not acked:
                    logger.error(
                        "worker.job_ack_skipped",
                        job_id=lease.job_id,
                        tenant_id=lease.organization_id,
                        lease_token=lease.token,
                        worker_id=lease.worker_id,
                    )
            except LostAnalysisJobLeaseError as exc:
                logger.error(
                    "worker.job_ack_lost_lease",
                    job_id=lease.job_id,
                    tenant_id=lease.organization_id,
                    lease_token=lease.token,
                    worker_id=lease.worker_id,
                    error=str(exc),
                )
            except Exception as exc:
                logger.error(
                    "worker.job_ack_failed",
                    job_id=lease.job_id,
                    tenant_id=lease.organization_id,
                    lease_token=lease.token,
                    worker_id=lease.worker_id,
                    error=str(exc),
                )
        elif finalize_action == "retry" and retry_at is not None:
            try:
                scheduled = await schedule_analysis_job_retry(
                    runtime.redis,
                    lease,
                    retry_at=retry_at,
                )
                if not scheduled:
                    logger.error(
                        "worker.job_retry_schedule_failed",
                        job_id=lease.job_id,
                        tenant_id=lease.organization_id,
                        lease_token=lease.token,
                        worker_id=lease.worker_id,
                        retry_at=retry_at.isoformat(),
                    )
            except LostAnalysisJobLeaseError as exc:
                logger.error(
                    "worker.job_retry_lost_lease",
                    job_id=lease.job_id,
                    tenant_id=lease.organization_id,
                    lease_token=lease.token,
                    worker_id=lease.worker_id,
                    error=str(exc),
                )
            except Exception as exc:
                logger.error(
                    "worker.job_retry_schedule_error",
                    job_id=lease.job_id,
                    tenant_id=lease.organization_id,
                    lease_token=lease.token,
                    worker_id=lease.worker_id,
                    retry_at=retry_at.isoformat(),
                    error=str(exc),
                )
        elif finalize_action == "dlq":
            try:
                moved = await move_analysis_job_to_dlq(
                    runtime.redis,
                    lease,
                    attempt_count=attempt_count,
                    reason=dlq_reason,
                )
                if not moved:
                    logger.error(
                        "worker.job_dlq_move_failed",
                        job_id=lease.job_id,
                        tenant_id=lease.organization_id,
                        lease_token=lease.token,
                        worker_id=lease.worker_id,
                    )
            except LostAnalysisJobLeaseError as exc:
                logger.error(
                    "worker.job_dlq_lost_lease",
                    job_id=lease.job_id,
                    tenant_id=lease.organization_id,
                    lease_token=lease.token,
                    worker_id=lease.worker_id,
                    error=str(exc),
                )
            except Exception as exc:
                logger.error(
                    "worker.job_dlq_move_error",
                    job_id=lease.job_id,
                    tenant_id=lease.organization_id,
                    lease_token=lease.token,
                    worker_id=lease.worker_id,
                    error=str(exc),
                )
        runtime.concurrency_limiter.release()


def _spawn_job_task(runtime: WorkerRuntime, lease: LeasedAnalysisJob) -> None:
    task = asyncio.create_task(_run_job_task(runtime, lease))
    runtime.inflight_tasks.add(task)


async def _renew_heavy_job_lease_loop(runtime: WorkerRuntime, lease: LeasedHeavyJob) -> None:
    current_lease = lease
    renewal_interval = min(
        _LEASE_RENEWAL_INTERVAL_SECONDS,
        max(5.0, runtime.heavy_job_lease_timeout_seconds / 3),
    )
    while True:
        await asyncio.sleep(renewal_interval)
        try:
            current_lease = await renew_heavy_job_lease(
                runtime.redis,
                current_lease,
                lease_timeout_seconds=runtime.heavy_job_lease_timeout_seconds,
            )
        except LostHeavyJobLeaseError as exc:
            logger.warning(
                "worker.heavy_lease_lost",
                heavy_job_type=lease.job_type,
                project_id=lease.project_id,
                lease_token=lease.token,
                error=str(exc),
            )
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "worker.heavy_lease_renewal_failed",
                heavy_job_type=lease.job_type,
                project_id=lease.project_id,
                lease_token=lease.token,
                error=str(exc),
            )


async def _run_heavy_job_task(runtime: WorkerRuntime, lease: LeasedHeavyJob) -> None:
    renewal_task = asyncio.create_task(_renew_heavy_job_lease_loop(runtime, lease))
    finalize_action = "ack"
    try:
        await runtime.heavy_job_executor.execute_lease(lease)
    except asyncio.CancelledError:
        raise
    except HeavyWorkerJobExecutionError as exc:
        logger.error(
            "worker.heavy_job_unhandled_error",
            heavy_job_type=exc.job_type,
            project_id=exc.project_id,
            tenant_id=exc.organization_id,
            export_id=exc.export_id,
            photo_id=exc.photo_id,
            error_type=type(exc.cause).__name__,
            error=str(exc.cause),
            lease_token=lease.token,
            worker_id=lease.worker_id,
            exc_info=True,
        )
    except InvalidHeavyJobPayloadError as exc:
        logger.error(
            "worker.heavy_invalid_queue_payload",
            heavy_job_type=lease.job_type,
            project_id=lease.project_id,
            lease_token=lease.token,
            worker_id=lease.worker_id,
            error=str(exc),
        )
    except Exception as exc:
        logger.error(
            "worker.heavy_job_task_error",
            heavy_job_type=lease.job_type,
            project_id=lease.project_id,
            lease_token=lease.token,
            worker_id=lease.worker_id,
            payload_keys=_extract_payload_keys(lease.payload),
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
    finally:
        renewal_task.cancel()
        await asyncio.gather(renewal_task, return_exceptions=True)
        if finalize_action == "ack":
            try:
                acked = await ack_heavy_job(runtime.redis, lease)
                if not acked:
                    logger.error(
                        "worker.heavy_job_ack_skipped",
                        heavy_job_type=lease.job_type,
                        project_id=lease.project_id,
                        lease_token=lease.token,
                        worker_id=lease.worker_id,
                    )
            except LostHeavyJobLeaseError as exc:
                logger.error(
                    "worker.heavy_job_ack_lost_lease",
                    heavy_job_type=lease.job_type,
                    project_id=lease.project_id,
                    lease_token=lease.token,
                    worker_id=lease.worker_id,
                    error=str(exc),
                )
            except Exception as exc:
                logger.error(
                    "worker.heavy_job_ack_failed",
                    heavy_job_type=lease.job_type,
                    project_id=lease.project_id,
                    lease_token=lease.token,
                    worker_id=lease.worker_id,
                    error=str(exc),
                )
        runtime.heavy_concurrency_limiter.release()


def _spawn_heavy_job_task(runtime: WorkerRuntime, lease: LeasedHeavyJob) -> None:
    task = asyncio.create_task(_run_heavy_job_task(runtime, lease))
    runtime.inflight_heavy_tasks.add(task)


async def _drain_finished_tasks(runtime: WorkerRuntime) -> None:
    for task_set in (runtime.inflight_tasks, runtime.inflight_heavy_tasks):
        completed_tasks = [task for task in task_set if task.done()]
        for task in completed_tasks:
            task_set.discard(task)
            try:
                await task
            except asyncio.CancelledError:
                continue


async def _cancel_inflight_tasks(runtime: WorkerRuntime) -> None:
    all_tasks = list(runtime.inflight_tasks) + list(runtime.inflight_heavy_tasks)
    if not all_tasks:
        return

    logger.info(
        "worker.shutdown_waiting_for_jobs",
        in_flight_jobs=len(all_tasks),
    )
    for task in all_tasks:
        task.cancel()
    await asyncio.gather(*all_tasks, return_exceptions=True)
    runtime.inflight_tasks.clear()
    runtime.inflight_heavy_tasks.clear()


async def _run_lease_reaper_if_due(runtime: WorkerRuntime, *, now_monotonic: float | None = None) -> None:
    current = time.monotonic() if now_monotonic is None else now_monotonic
    if current - runtime.last_lease_reap < runtime.lease_reap_interval_seconds:
        return

    runtime.last_lease_reap = current
    expired_leases = await get_expired_analysis_job_leases(
        runtime.redis,
        limit=max(_LEASE_REAPER_BATCH_SIZE, runtime.worker_concurrency * 4),
    )
    if not expired_leases:
        return

    service = _build_worker_analysis_service(runtime.settings)
    requeued = 0
    dropped = 0

    for lease in expired_leases:
        try:
            disposition = await service.reconcile_expired_lease(lease)
        except Exception as exc:
            logger.error(
                "worker.lease_reaper_db_reconcile_failed",
                job_id=lease.job_id,
                tenant_id=lease.organization_id,
                lease_token=lease.token,
                worker_id=lease.worker_id,
                error=str(exc),
                exc_info=True,
            )
            continue

        try:
            if disposition == "requeue":
                if await requeue_expired_analysis_job(runtime.redis, lease):
                    requeued += 1
            else:
                if await drop_expired_analysis_job(runtime.redis, lease):
                    dropped += 1
        except Exception as exc:
            logger.error(
                "worker.lease_reaper_finalize_failed",
                job_id=lease.job_id,
                tenant_id=lease.organization_id,
                lease_token=lease.token,
                worker_id=lease.worker_id,
                disposition=disposition,
                error=str(exc),
                exc_info=True,
            )

    if requeued or dropped:
        record_reaper_requeues(requeued)
        logger.warning(
            "worker.lease_reaper_processed",
            requeued=requeued,
            dropped=dropped,
            inspected=len(expired_leases),
        )


async def _run_heavy_lease_reaper_if_due(runtime: WorkerRuntime, *, now_monotonic: float | None = None) -> None:
    if runtime.worker_heavy_concurrency <= 0:
        return

    current = time.monotonic() if now_monotonic is None else now_monotonic
    if current - runtime.last_heavy_lease_reap < runtime.heavy_lease_reap_interval_seconds:
        return

    runtime.last_heavy_lease_reap = current
    expired_leases = await get_expired_heavy_job_leases(
        runtime.redis,
        limit=max(_LEASE_REAPER_BATCH_SIZE, max(1, runtime.worker_heavy_concurrency) * 4),
    )
    if not expired_leases:
        return

    requeued = 0
    dropped = 0
    for lease in expired_leases:
        try:
            if await requeue_expired_heavy_job(runtime.redis, lease):
                requeued += 1
            else:
                if await drop_expired_heavy_job(runtime.redis, lease):
                    dropped += 1
        except Exception as exc:
            logger.error(
                "worker.heavy_lease_reaper_finalize_failed",
                heavy_job_type=lease.job_type,
                project_id=lease.project_id,
                lease_token=lease.token,
                worker_id=lease.worker_id,
                error=str(exc),
                exc_info=True,
            )

    if requeued or dropped:
        logger.warning(
            "worker.heavy_lease_reaper_processed",
            requeued=requeued,
            dropped=dropped,
            inspected=len(expired_leases),
        )


async def _run_one_iteration(runtime: WorkerRuntime) -> None:
    await _run_export_cleanup_if_due(runtime)
    await _run_photo_cleanup_if_due(runtime)
    await _write_heartbeat_if_due(runtime)
    await _drain_finished_tasks(runtime)
    await _run_lease_reaper_if_due(runtime)
    await _run_heavy_lease_reaper_if_due(runtime)
    await promote_scheduled_analysis_jobs(
        runtime.redis,
        limit=max(runtime.worker_concurrency * 4, 10),
        max_depth=runtime.settings.analysis_queue_max_depth,
    )

    spawned_work = False
    acquired_slot = await _acquire_job_slot(runtime)
    if acquired_slot:
        try:
            lease = await dequeue_analysis_job(
                runtime.redis,
                worker_id=runtime.worker_instance_id,
                lease_timeout_seconds=runtime.job_lease_timeout_seconds,
            )
        except BaseException:
            runtime.concurrency_limiter.release()
            raise

        if lease is None:
            runtime.concurrency_limiter.release()
        else:
            try:
                _spawn_job_task(runtime, lease)
                spawned_work = True
            except BaseException:
                runtime.concurrency_limiter.release()
                raise

    if runtime.worker_heavy_concurrency > 0:
        acquired_heavy_slot = await _acquire_heavy_job_slot(runtime)
        if acquired_heavy_slot:
            try:
                heavy_lease = await dequeue_heavy_job(
                    runtime.redis,
                    worker_id=runtime.worker_instance_id,
                    lease_timeout_seconds=runtime.heavy_job_lease_timeout_seconds,
                )
            except BaseException:
                runtime.heavy_concurrency_limiter.release()
                raise

            if heavy_lease is None:
                runtime.heavy_concurrency_limiter.release()
            else:
                try:
                    _spawn_heavy_job_task(runtime, heavy_lease)
                    spawned_work = True
                except BaseException:
                    runtime.heavy_concurrency_limiter.release()
                    raise

    if not spawned_work:
        await asyncio.sleep(_IDLE_LOOP_SLEEP_SECONDS)


async def run(redis_url: str | None = None) -> None:
    """Main worker loop. Runs until cancelled."""
    settings = get_settings()
    url = redis_url or settings.redis_url
    worker_instance_id = build_worker_instance_id()
    heartbeat_key = worker_heartbeat_key(worker_instance_id)
    job_executor = WorkerJobExecutor(settings)
    heavy_job_executor = HeavyWorkerJobExecutor()
    worker_concurrency = _configured_worker_concurrency(settings)
    worker_heavy_concurrency = _configured_heavy_worker_concurrency(settings)
    job_lease_timeout_seconds = _configured_job_lease_timeout_seconds(settings)
    heavy_job_lease_timeout_seconds = _configured_heavy_job_lease_timeout_seconds(settings)
    lease_reap_interval_seconds = _configured_job_reap_interval_seconds(settings)
    heavy_lease_reap_interval_seconds = _configured_heavy_job_reap_interval_seconds(settings)

    redis = _build_worker_redis(settings, url)
    await _verify_worker_redis_startup(redis, settings, url)
    runtime = WorkerRuntime(
        settings=settings,
        redis_url=url,
        redis=redis,
        worker_instance_id=worker_instance_id,
        heartbeat_key=heartbeat_key,
        job_executor=job_executor,
        heavy_job_executor=heavy_job_executor,
        worker_concurrency=worker_concurrency,
        job_lease_timeout_seconds=job_lease_timeout_seconds,
        lease_reap_interval_seconds=lease_reap_interval_seconds,
        concurrency_limiter=asyncio.Semaphore(worker_concurrency),
        inflight_tasks=set(),
        worker_heavy_concurrency=worker_heavy_concurrency,
        heavy_job_lease_timeout_seconds=heavy_job_lease_timeout_seconds,
        heavy_lease_reap_interval_seconds=heavy_lease_reap_interval_seconds,
        heavy_concurrency_limiter=asyncio.Semaphore(max(1, worker_heavy_concurrency or 1)),
    )
    try:
        await _write_heartbeat_if_due(runtime)
    except Exception as exc:
        logger.error("worker.startup_heartbeat_failed", error=str(exc), exc_info=True)
        try:
            await runtime.redis.aclose()
        except Exception as close_exc:
            logger.warning("worker.redis_close_failed", error=str(close_exc))
        runtime.redis = _build_worker_redis(settings, url)
        await asyncio.sleep(1)

    logger.info(
        "worker.started",
        provider=settings.ai_analysis_provider,
        instance_id=worker_instance_id,
        heartbeat_key=heartbeat_key,
        concurrency=worker_concurrency,
        heavy_concurrency=worker_heavy_concurrency,
        lease_timeout_seconds=job_lease_timeout_seconds,
        heavy_lease_timeout_seconds=heavy_job_lease_timeout_seconds,
    )
    try:
        while True:
            try:
                await _run_one_iteration(runtime)
            except asyncio.CancelledError:
                logger.info("worker.shutdown")
                break
            except InvalidAnalysisJobPayloadError as exc:
                logger.error("worker.invalid_queue_payload", error=str(exc))
                continue
            except Exception as exc:
                logger.error("worker.loop_error", error=str(exc), exc_info=True)
                try:
                    await runtime.redis.aclose()
                except Exception as close_exc:
                    logger.warning("worker.redis_close_failed", error=str(close_exc))
                runtime.redis = _build_worker_redis(settings, url)
                await asyncio.sleep(1)
    finally:
        await _cancel_inflight_tasks(runtime)
        await clear_worker_heartbeat(runtime.redis, worker_instance_id)
        await clear_local_worker_heartbeat()
        await runtime.redis.aclose()
        logger.info("worker.stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.worker_metrics_enabled:
        if start_http_server is None or not PROMETHEUS_CLIENT_AVAILABLE:
            if settings.app_env.lower() not in ("development", "test"):
                raise RuntimeError(
                    startup_failure_message(
                        "worker_metrics",
                        "prometheus_client must be installed when WORKER_METRICS_ENABLED=true outside development/test.",
                    )
                )
            logger.warning("worker.metrics_disabled", reason="prometheus_client_not_installed")
        else:
            start_http_server(
                port=settings.worker_metrics_port,
                addr=settings.worker_metrics_host,
            )
            logger.info(
                "worker.metrics_started",
                host=settings.worker_metrics_host,
                port=settings.worker_metrics_port,
            )
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
