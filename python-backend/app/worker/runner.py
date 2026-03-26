"""Analysis job worker process (R-19).

Run as a standalone process (outside the web server):
    python -m app.worker.runner

The worker continuously dequeues analysis jobs from Redis and executes them via
AnalysisService.execute_job(), which creates its own DB session.  A restart of
either the web server or this worker is safe: unprocessed queue items survive in
Redis; interrupted jobs are marked 'failed' by the web server's startup stale-job
recovery (R-36).
"""
import asyncio
import sys

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.analysis_service import AnalysisService
from app.worker.queue import dequeue_analysis_job

logger = structlog.get_logger(__name__)


async def _process_one(payload: dict, settings) -> None:
    job_id = payload["job_id"]
    project_id = payload["project_id"]
    organization_id = payload.get("organization_id")
    is_superadmin_context = payload.get("is_superadmin_context", False)

    log = logger.bind(job_id=job_id, project_id=project_id)
    log.info("worker.dequeued", organization_id=organization_id)

    # AnalysisService.execute_job() creates its own AsyncSession internally.
    # The repository/photo_repository attributes are not used by execute_job.
    service = AnalysisService(
        repository=None,  # type: ignore[arg-type]  — not used by execute_job
        photo_repository=None,  # type: ignore[arg-type]  — not used by execute_job
        provider_key=settings.ai_analysis_provider,
    )
    await service.execute_job(
        job_id,
        project_id,
        organization_id,
        is_superadmin_context=is_superadmin_context,
    )
    log.info("worker.job_done")


async def run(redis_url: str | None = None) -> None:
    """Main worker loop. Runs until cancelled."""
    settings = get_settings()
    url = redis_url or settings.redis_url

    from redis.asyncio import Redis
    redis = Redis.from_url(url)

    logger.info("worker.started", provider=settings.ai_analysis_provider)
    try:
        while True:
            try:
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
