from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text

from app.api.deps import require_superadmin
from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.models import AnalysisJob
from app.schemas.auth import AuthUserRead

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus metrics scrape endpoint (R-38).

    Returns metrics in Prometheus text exposition format.
    Restricted to internal IPs at the nginx/proxy layer — do NOT expose publicly.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/alive")
async def alive() -> dict:
    """Liveness probe — confirms the process is running. No DB, no latency."""
    return {"status": "alive"}


@router.get("/")
async def root() -> dict:
    settings = get_settings()
    return {
        "message": f"{settings.app_name} Python backend skeleton",
        "status": "ok",
        "environment": settings.app_env
    }


@router.get("/health")
async def health(request: Request) -> dict:
    """Public health check — minimal, safe for load balancer probes."""
    db_live = False
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
            db_live = True
    except Exception:
        pass

    ready = all(value == "ok" for value in request.app.state.startup_checks.values())
    return {
        "status": "ok" if (ready and db_live) else "degraded",
        "service": "python-backend",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health/internal", include_in_schema=False)
async def health_internal(
    request: Request,
    _: AuthUserRead = Depends(require_superadmin),
) -> dict:
    """Detailed internal health check — DB stats, job counts, startup checks.

    Requires superadmin token. Additionally restricted to internal IPs at nginx.
    """
    settings = get_settings()
    ready = all(value == "ok" for value in request.app.state.startup_checks.values())

    db_live = False
    jobs_running = 0
    jobs_queued = 0
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
    except Exception:
        pass

    return {
        "status": "ok" if (ready and db_live) else "degraded",
        "service": "python-backend",
        "debug": settings.app_debug,
        "ready": ready,
        "startupChecks": request.app.state.startup_checks,
        "db": "ok" if db_live else "error",
        "jobs": {
            "running": jobs_running,
            "queued": jobs_queued,
            "lastCompletedAt": last_completed_at,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
