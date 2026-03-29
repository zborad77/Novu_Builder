"""Analysis job worker process (R-19).

Run as a standalone process (outside the web server):
    python -m app.worker.runner

The worker continuously dequeues analysis jobs from Redis and executes them via
AnalysisService.execute_job(), which creates its own DB session.  A restart of
either the web server or this worker is safe: unprocessed queue items survive in
Redis; interrupted jobs are marked 'failed' by the web server's startup stale-job
recovery (R-36).

Heartbeat: the worker writes worker:heartbeat every 30 s with a 120 s TTL.
The /health/internal endpoint reads this key to detect "worker down".
"""
import asyncio
import sys
import time
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.analysis_service import AnalysisService
from app.worker.queue import dequeue_analysis_job

logger = structlog.get_logger(__name__)


async def _process_one(payload: dict, settings) -> None:
    # Validate required payload keys before any DB or service interaction.
    # KeyError here would consume the queue item without failing the job in DB.
    job_id = payload.get("job_id")
    project_id = payload.get("project_id")

    if not job_id or not isinstance(job_id, str):
        logger.error(
            "worker.invalid_payload",
            reason="missing_or_invalid_job_id",
            payload_keys=sorted(payload.keys()),
        )
        return

    if not project_id or not isinstance(project_id, str):
        logger.error(
            "worker.invalid_payload",
            reason="missing_or_invalid_project_id",
            job_id=job_id,
            payload_keys=sorted(payload.keys()),
        )
        return

    organization_id = payload.get("organization_id")
    is_superadmin_context = bool(payload.get("is_superadmin_context", False))

    log = logger.bind(job_id=job_id, project_id=project_id)
    log.info("worker.dequeued", organization_id=organization_id)

    # AnalysisService.execute_job() creates its own AsyncSession internally.
    # The repository/photo_repository attributes are not used by execute_job.
    service = AnalysisService(
        repository=None,  # type: ignore[arg-type]  — not used by execute_job
        photo_repository=None,  # type: ignore[arg-type]  — not used by execute_job
        provider_key=settings.ai_analysis_provider,
    )
    try:
        await service.execute_job(
            job_id,
            project_id,
            organization_id,
            is_superadmin_context=is_superadmin_context,
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


_HEARTBEAT_KEY = "worker:heartbeat"
_HEARTBEAT_INTERVAL = 30   # write at most once every 30 s
_HEARTBEAT_TTL = 120       # key expires after 120 s (2× interval) if worker dies


async def run(redis_url: str | None = None) -> None:
    """Main worker loop. Runs until cancelled."""
    settings = get_settings()
    url = redis_url or settings.redis_url

    from redis.asyncio import Redis
    redis = Redis.from_url(
        url,
        socket_connect_timeout=5.0,
        # socket_timeout intentionally omitted: BLPOP blocks for up to the
        # dequeue timeout (5 s) before the server sends a nil response.
        # Setting socket_timeout < BLPOP timeout would cause spurious errors.
    )

    logger.info("worker.started", provider=settings.ai_analysis_provider)
    last_heartbeat: float = 0.0
    try:
        while True:
            try:
                # Write heartbeat to Redis at most once per _HEARTBEAT_INTERVAL seconds.
                now = time.monotonic()
                if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                    await redis.set(
                        _HEARTBEAT_KEY,
                        datetime.now(UTC).isoformat(),
                        ex=_HEARTBEAT_TTL,
                    )
                    last_heartbeat = now

                payload = await dequeue_analysis_job(redis)
                if payload is None:
                    continue
                await _process_one(payload, settings)
            except asyncio.CancelledError:
                logger.info("worker.shutdown")
                break
            except Exception as exc:
                logger.error("worker.loop_error", error=str(exc), exc_info=True)
                await asyncio.sleep(1)  # brief back-off on unexpected errors
    finally:
        await redis.aclose()
        logger.info("worker.stopped")


def main() -> None:
    configure_logging(get_settings().log_level)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
