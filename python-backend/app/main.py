import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from datetime import UTC, datetime

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
import structlog

from app.api.router import api_router
from app.core.audit import AuditMiddleware
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.core.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
)
from app.db.base import Base
from app.db.bootstrap import ensure_dev_seed
from app.db.session import AsyncSessionFactory, engine
from app.models import AnalysisJob, Project
from app.repositories.token_repository import TokenRepository
from app.storage.local_photo_storage import EXPORTS_ROOT, STORAGE_ROOT, UPLOADS_ROOT


logger = structlog.get_logger(__name__)

try:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
except ModuleNotFoundError as exc:
    logger.warning("rate_limiter.handler_disabled", reason="slowapi_not_installed", error=str(exc))
    _rate_limit_exceeded_handler = None
    RateLimitExceeded = None


async def verify_database_connectivity() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def verify_application_schema() -> None:
    async with AsyncSessionFactory() as session:
        await session.execute(select(Project.id).limit(1))


def verify_storage_root() -> None:
    # Ensure all persistent storage directories exist
    for directory in (STORAGE_ROOT, UPLOADS_ROOT, EXPORTS_ROOT):
        directory.mkdir(parents=True, exist_ok=True)

    # Write probe — fail-fast if storage is not writable
    probe_file = STORAGE_ROOT / ".startup-write-check"
    try:
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
    except OSError as exc:
        logger.error("storage.not_writable", root=str(STORAGE_ROOT), error=str(exc))
        raise RuntimeError(f"STORAGE_ROOT is not writable: {STORAGE_ROOT}") from exc

    # Count existing files to confirm data persists across restarts
    upload_count = sum(1 for _ in UPLOADS_ROOT.rglob("*") if _.is_file())
    export_count = sum(1 for _ in EXPORTS_ROOT.rglob("*") if _.is_file() and _.suffix != ".json")
    logger.info(
        "storage.verified",
        root=str(STORAGE_ROOT),
        uploads_root=str(UPLOADS_ROOT),
        exports_root=str(EXPORTS_ROOT),
        existing_uploads=upload_count,
        existing_exports=export_count,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    startup_checks = {
        "database": "pending",
        "schema": "pending",
        "storage": "pending",
    }

    if settings.should_auto_create_schema:
        logger.info("db.schema_bootstrap", mode="create_all", environment=settings.app_env)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    else:
        # R-17: application startup must NOT run migrations.
        # Run 'alembic upgrade head' (or use docker-entrypoint.sh) before starting the app.
        # Here we only verify the DB is already at the expected head revision.
        logger.info("db.schema_check", mode="version_guard", environment=settings.app_env)
        _BACKEND_ROOT = Path(__file__).resolve().parent.parent
        from alembic.config import Config as AlembicConfig
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        alembic_cfg = AlembicConfig(str(_BACKEND_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))

        script_dir = ScriptDirectory.from_config(alembic_cfg)
        expected_head = script_dir.get_current_head()

        async with engine.connect() as connection:
            current_rev = await connection.run_sync(
                lambda sync_conn: MigrationContext.configure(sync_conn).get_current_revision()
            )

        if current_rev != expected_head:
            raise RuntimeError(
                f"Database schema is not at the expected revision. "
                f"Current: {current_rev!r}, expected head: {expected_head!r}. "
                f"Run 'alembic upgrade head' before starting the application."
            )
        logger.info("db.schema_check", status="ok", revision=current_rev)

    if settings.should_seed_on_startup:
        logger.info("db.seed_bootstrap", enabled=True, environment=settings.app_env)
        async with AsyncSessionFactory() as session:
            await ensure_dev_seed(session)
    else:
        logger.info("db.seed_bootstrap", enabled=False, environment=settings.app_env)

    await verify_database_connectivity()
    startup_checks["database"] = "ok"
    await verify_application_schema()
    startup_checks["schema"] = "ok"
    verify_storage_root()
    startup_checks["storage"] = "ok"
    app.state.startup_checks = startup_checks
    logger.info("startup.checks", **startup_checks)

    async with AsyncSessionFactory() as session:
        deleted = await TokenRepository(session).delete_expired()
        if deleted:
            logger.info("startup.revoked_tokens_cleanup", deleted=deleted)

    # R-19: initialise Redis job queue — optional, fails open when Redis is absent
    if settings.redis_url:
        try:
            from redis.asyncio import Redis as _Redis
            _redis_client = _Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
            )
            await _redis_client.ping()  # type: ignore[misc]  # redis.asyncio stubs
            app.state.job_queue = _redis_client
            logger.info("job_queue.ready")
        except Exception as exc:
            logger.warning("job_queue.unavailable", error=str(exc))
            app.state.job_queue = None
    else:
        app.state.job_queue = None
        logger.info("job_queue.disabled", reason="REDIS_URL_not_set")

    # R-36: recover stale running jobs — mark as failed so they don't block retries
    try:
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(AnalysisJob).where(AnalysisJob.status == "running")
            )
            stale_jobs = result.scalars().all()
            if stale_jobs:
                now = datetime.now(UTC)
                for job in stale_jobs:
                    job.status = "failed"
                    job.finished_at = job.finished_at or now
                    job.error_message = "Server restart detected — job interrupted."
                await session.commit()
                logger.warning(
                    "startup.stale_jobs_recovered",
                    count=len(stale_jobs),
                    job_ids=[job.id for job in stale_jobs],
                )
            else:
                logger.info("startup.stale_jobs_detected", count=0)
    except Exception as exc:
        logger.warning("startup.stale_jobs_check_failed", error=str(exc))

    yield

    # Teardown — close Redis connection pool
    if getattr(app.state, "job_queue", None) is not None:
        await app.state.job_queue.aclose()
        logger.info("job_queue.closed")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_file, settings.log_error_file)

    # Error monitoring — opt-in via SENTRY_DSN env var
    if settings.sentry_dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.app_env,
                traces_sample_rate=0.0,   # disable performance tracing — errors only
                profiles_sample_rate=0.0,
            )
            logger.info("sentry.initialized", environment=settings.app_env)
        except ImportError:
            logger.warning("sentry.disabled", reason="sentry-sdk not installed")

    # In production, hide docs endpoints and disable debug tracebacks
    docs_url = "/docs" if settings.app_debug else None
    redoc_url = "/redoc" if settings.app_debug else None

    app = FastAPI(
        title=settings.app_name,
        version="0.5.0",
        description="New target backend skeleton for FotoNabidka.",
        debug=settings.app_debug,
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )
    app.state.startup_checks = {
        "database": "pending",
        "schema": "pending",
        "storage": "pending",
    }

    # Rate limiter state + 429 handler
    app.state.limiter = limiter
    if RateLimitExceeded is not None and _rate_limit_exceeded_handler is not None:
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # HTTPS redirect — only when explicitly required (production, no reverse-proxy)
    if settings.require_https:
        app.add_middleware(HTTPSRedirectMiddleware)

    app.add_middleware(AuditMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        # HSTS — tell browsers to always use HTTPS (only meaningful over TLS)
        if settings.require_https or settings.app_env != "development":
            response.headers["Strict-Transport-Security"] = (
                f"max-age={settings.hsts_max_age}; includeSubDomains"
            )
        # Prevent MIME sniffing and clickjacking on API responses
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.middleware("http")
    async def log_requests(request: Request, call_next) -> Response:
        start = time.monotonic()
        HTTP_REQUESTS_IN_PROGRESS.labels(method=request.method).inc()
        try:
            response = await call_next(request)
        finally:
            HTTP_REQUESTS_IN_PROGRESS.labels(method=request.method).dec()
        elapsed = time.monotonic() - start
        duration_ms = round(elapsed * 1000)
        if not request.url.path.startswith("/mock-storage"):
            # R-38: use route path template (e.g. /api/v1/cases/{case_id}) to avoid
            # label cardinality explosion from per-resource IDs.
            route = request.scope.get("route")
            path_template = route.path if route else request.url.path
            status_str = str(response.status_code)
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                path_template=path_template,
                status_code=status_str,
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=request.method,
                path_template=path_template,
                status_code=status_str,
            ).observe(elapsed)
            log = logger.error if response.status_code >= 500 else logger.info
            log(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
        return response

    @app.middleware("http")
    async def request_id_context(request: Request, call_next) -> Response:
        """Bind a unique request ID to the structlog context for this request."""
        structlog.contextvars.clear_contextvars()
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "http.unhandled_exception",
            exc_type=type(exc).__name__,
            method=request.method,
            path=request.url.path,
            exc_info=True,
        )
        if settings.sentry_dsn:
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(exc)
            except ImportError:
                pass
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    # WARNING: /mock-storage serves local filesystem files through an
    # authenticated route. It is a dev-only facility — in production, files
    # are served by a dedicated storage backend (S3/CDN). Never enable this
    # mount in production; doing so exposes the local storage directory.
    if settings.is_development:
        from app.api.routes.storage import router as storage_router
        app.include_router(storage_router)

    return app


app = create_app()
