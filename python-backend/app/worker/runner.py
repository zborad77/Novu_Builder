"""Analysis job worker process (R-19).

Run as a standalone process (outside the web server):
    python -m app.worker.runner

The worker continuously dequeues analysis jobs from Redis and executes them via
AnalysisService.execute_job(), which creates its own DB session. A restart of
either the web server or this worker is safe: unprocessed queue items survive in
Redis; interrupted jobs are marked 'failed' by the web server's startup stale-job
recovery (R-36).

Heartbeat: the worker writes a per-instance worker:heartbeat:<instance_id> key
every 30 s with a 120 s TTL. /health/internal treats the worker layer as alive
when at least one fresh heartbeat exists.
"""
import asyncio
from dataclasses import dataclass
import math
import sys
import time
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException

from app.core.config import get_settings, startup_failure_message
from app.core.logging import configure_logging
from app.core.redis_client import build_redis_client_from_settings
from app.services.analysis_service import AnalysisService
from app.worker.heartbeat import (
    clear_worker_heartbeat,
    WORKER_HEARTBEAT_INTERVAL,
    WORKER_HEARTBEAT_KEY_PREFIX,
    WORKER_HEARTBEAT_LEGACY_KEY,
    WORKER_HEARTBEAT_TTL,
    build_worker_instance_id,
    worker_heartbeat_key,
    write_worker_heartbeat,
)
from app.worker.queue import (
    InvalidAnalysisJobPayloadError,
    dequeue_analysis_job,
    validate_analysis_job_payload,
)

logger = structlog.get_logger(__name__)


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


@dataclass(frozen=True)
class WorkerJobSpec:
    job_id: str
    project_id: str
    organization_id: str | None
    is_superadmin_context: bool


@dataclass
class WorkerRuntime:
    settings: object
    redis_url: str
    redis: object
    worker_instance_id: str
    heartbeat_key: str
    job_executor: "WorkerJobExecutor"
    worker_concurrency: int
    concurrency_limiter: asyncio.Semaphore
    inflight_tasks: set[asyncio.Task[None]]
    last_heartbeat: float = 0.0


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


def _build_worker_analysis_service(settings) -> AnalysisService:
    return AnalysisService(
        repository=None,  # type: ignore[arg-type]  # worker-only methods create their own session
        photo_repository=None,  # type: ignore[arg-type]  # worker-only methods create their own session
        provider_key=settings.ai_analysis_provider,
    )


class WorkerJobExecutor:
    """Isolated single-job executor.

    It owns no mutable cross-job state besides configuration, which makes it a
    safe boundary for future concurrency fan-out while keeping today's
    single-worker semantics unchanged.
    """

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

    async def execute_payload(self, payload: object) -> None:
        job = await self._parse_job_spec(payload)
        if job is None:
            return

        log = logger.bind(job_id=job.job_id, project_id=job.project_id)
        log.info("worker.dequeued", organization_id=job.organization_id)
        service = self._new_service()
        try:
            await service.execute_job(
                job.job_id,
                job.project_id,
                job.organization_id,
                is_superadmin_context=job.is_superadmin_context,
            )
            log.info("worker.job_done")
        except HTTPException as exc:
            # execute_job already marked the job as failed in DB before raising.
            # Log as a policy rejection rather than an unexpected loop error so that
            # monitoring can distinguish security check failures from infrastructure faults.
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


async def _process_one(payload: dict, settings) -> None:
    await WorkerJobExecutor(settings).execute_payload(payload)


_HEARTBEAT_KEY_PREFIX = WORKER_HEARTBEAT_KEY_PREFIX
_HEARTBEAT_LEGACY_KEY = WORKER_HEARTBEAT_LEGACY_KEY
_HEARTBEAT_INTERVAL = WORKER_HEARTBEAT_INTERVAL
_HEARTBEAT_TTL = WORKER_HEARTBEAT_TTL
_DEQUEUE_TIMEOUT_SECONDS = 5


def _is_strict_worker_environment(settings) -> bool:
    return settings.app_env.lower() not in ("development", "test")


def _build_worker_redis(settings, redis_url: str):
    # BLPOP blocks for up to the dequeue timeout before the server replies, so
    # the worker must not use a short socket_timeout here.
    return build_redis_client_from_settings(
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

    await write_worker_heartbeat(
        runtime.redis,
        runtime.worker_instance_id,
        now=datetime.now(UTC),
    )
    runtime.last_heartbeat = current


def _seconds_until_next_heartbeat(runtime: WorkerRuntime, *, now_monotonic: float | None = None) -> float:
    current = time.monotonic() if now_monotonic is None else now_monotonic
    elapsed = current - runtime.last_heartbeat
    return max(0.0, _HEARTBEAT_INTERVAL - elapsed)


def _dequeue_timeout_seconds(runtime: WorkerRuntime) -> int:
    remaining = _seconds_until_next_heartbeat(runtime)
    if remaining <= 0:
        return 1
    return max(1, min(_DEQUEUE_TIMEOUT_SECONDS, math.ceil(remaining)))


async def _acquire_job_slot(runtime: WorkerRuntime) -> bool:
    if not runtime.concurrency_limiter.locked():
        await runtime.concurrency_limiter.acquire()
        return True

    timeout = _seconds_until_next_heartbeat(runtime)
    if timeout <= 0:
        return False

    try:
        await asyncio.wait_for(runtime.concurrency_limiter.acquire(), timeout=timeout)
    except asyncio.TimeoutError:
        return False
    return True


async def _run_job_task(runtime: WorkerRuntime, payload: object) -> None:
    try:
        await runtime.job_executor.execute_payload(payload)
    except asyncio.CancelledError:
        raise
    except WorkerJobExecutionError as exc:
        logger.error(
            "worker.job_unhandled_error",
            job_id=exc.job_id,
            project_id=exc.project_id,
            organization_id=exc.organization_id,
            error_type=type(exc.cause).__name__,
            error=str(exc.cause),
            exc_info=True,
        )
    except InvalidAnalysisJobPayloadError as exc:
        logger.error("worker.invalid_queue_payload", error=str(exc))
    except Exception as exc:
        logger.error(
            "worker.job_task_error",
            job_id=_extract_candidate_job_id(payload),
            payload_keys=_extract_payload_keys(payload),
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
    finally:
        runtime.concurrency_limiter.release()


def _spawn_job_task(runtime: WorkerRuntime, payload: object) -> None:
    task = asyncio.create_task(_run_job_task(runtime, payload))
    runtime.inflight_tasks.add(task)


async def _drain_finished_tasks(runtime: WorkerRuntime) -> None:
    completed_tasks = [task for task in runtime.inflight_tasks if task.done()]
    for task in completed_tasks:
        runtime.inflight_tasks.discard(task)
        try:
            await task
        except asyncio.CancelledError:
            continue


async def _cancel_inflight_tasks(runtime: WorkerRuntime) -> None:
    if not runtime.inflight_tasks:
        return

    logger.info(
        "worker.shutdown_waiting_for_jobs",
        in_flight_jobs=len(runtime.inflight_tasks),
    )
    tasks = list(runtime.inflight_tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    runtime.inflight_tasks.clear()


async def _run_one_iteration(runtime: WorkerRuntime) -> None:
    await _write_heartbeat_if_due(runtime)
    await _drain_finished_tasks(runtime)
    acquired_slot = await _acquire_job_slot(runtime)
    if not acquired_slot:
        return

    try:
        payload = await dequeue_analysis_job(
            runtime.redis,
            timeout=_dequeue_timeout_seconds(runtime),
        )
    except BaseException:
        runtime.concurrency_limiter.release()
        raise

    if payload is None:
        runtime.concurrency_limiter.release()
        return
    try:
        _spawn_job_task(runtime, payload)
    except BaseException:
        runtime.concurrency_limiter.release()
        raise


async def run(redis_url: str | None = None) -> None:
    """Main worker loop. Runs until cancelled."""
    settings = get_settings()
    url = redis_url or settings.redis_url
    worker_instance_id = build_worker_instance_id()
    heartbeat_key = worker_heartbeat_key(worker_instance_id)
    job_executor = WorkerJobExecutor(settings)
    worker_concurrency = _configured_worker_concurrency(settings)

    redis = _build_worker_redis(settings, url)
    await _verify_worker_redis_startup(redis, settings, url)
    runtime = WorkerRuntime(
        settings=settings,
        redis_url=url,
        redis=redis,
        worker_instance_id=worker_instance_id,
        heartbeat_key=heartbeat_key,
        job_executor=job_executor,
        worker_concurrency=worker_concurrency,
        concurrency_limiter=asyncio.Semaphore(worker_concurrency),
        inflight_tasks=set(),
    )

    logger.info(
        "worker.started",
        provider=settings.ai_analysis_provider,
        instance_id=worker_instance_id,
        heartbeat_key=heartbeat_key,
        concurrency=worker_concurrency,
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
        await runtime.redis.aclose()
        logger.info("worker.stopped")


def main() -> None:
    configure_logging(get_settings().log_level)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
