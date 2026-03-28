import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select, text
import structlog

from app.api.deps import require_superadmin
from app.core.config import get_settings
from app.core.metrics import (
    DB_ALIVE,
    JOBS_QUEUED,
    JOBS_RUNNING,
    PROMETHEUS_CLIENT_AVAILABLE,
    WORKER_ALIVE,
)
from app.db.session import AsyncSessionFactory
from app.models import AnalysisJob
from app.schemas.auth import AuthUserRead

router = APIRouter()
logger = structlog.get_logger(__name__)

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
except ModuleNotFoundError:
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    generate_latest = None


async def _refresh_operational_metrics(request: Request) -> None:
    """Refresh DB/worker/job gauges before each Prometheus scrape (C5).

    Failures are silently swallowed; a missing gauge value is better than a
    broken scrape endpoint.
    """
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
            DB_ALIVE.set(1)

            running_row = await session.execute(
                select(func.count()).where(AnalysisJob.status == "running")
            )
            queued_row = await session.execute(
                select(func.count()).where(AnalysisJob.status == "queued")
            )
            JOBS_RUNNING.set(running_row.scalar_one() or 0)
            JOBS_QUEUED.set(queued_row.scalar_one() or 0)
    except Exception:
        DB_ALIVE.set(0)

    try:
        redis = getattr(request.app.state, "job_queue", None)
        if redis is not None:
            raw = await redis.get("worker:heartbeat")
            if raw is not None:
                ts = datetime.fromisoformat(raw.decode())
                WORKER_ALIVE.set(1 if (datetime.now(UTC) - ts).total_seconds() < 90 else 0)
            else:
                WORKER_ALIVE.set(0)
    except Exception:
        pass


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    """Prometheus metrics scrape endpoint (R-38)."""
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
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/alive")
async def alive() -> dict:
    """Liveness probe; confirms the process is running."""
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
async def health(request: Request) -> dict:
    """Public health check; minimal, safe for load balancer probes."""
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
    """Detailed internal health check; DB stats, job counts, startup checks."""
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

    worker_alive: bool | None = None
    worker_last_seen: str | None = None
    try:
        redis = getattr(request.app.state, "job_queue", None)
        if redis is not None:
            raw = await redis.get("worker:heartbeat")
            if raw is not None:
                worker_last_seen = raw.decode()
                ts = datetime.fromisoformat(worker_last_seen)
                worker_alive = (datetime.now(UTC) - ts).total_seconds() < 90
            else:
                worker_alive = False
    except Exception:
        worker_alive = None

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
        "worker": {
            "alive": worker_alive,
            "lastSeenAt": worker_last_seen,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
