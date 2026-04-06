import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import TimeoutError as SQLAlchemyPoolTimeoutError
import structlog

from app.api.router import api_router
from app.core.audit import AuditMiddleware
from app.core.config import get_settings, startup_failure_message
from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.core.metrics import (
    DB_POOL_EXHAUSTED_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    PROMETHEUS_CLIENT_AVAILABLE,
)
from app.core.request_id import sanitize_request_id
from app.core.redis_client import build_queue_redis_client_from_settings
from app.db.base import Base
from app.db.bootstrap import audit_seed_default_passwords, ensure_dev_seed
from app.db.session import AsyncSessionFactory, engine
from app.models import Project
from app.repositories.token_repository import TokenRepository
from app.storage.backend import verify_storage_health


logger = structlog.get_logger(__name__)

_CONTENT_SECURITY_POLICY_DIRECTIVES: tuple[str, ...] = (
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
)
_CORS_ALLOW_METHODS: tuple[str, ...] = (
    "GET",
    "POST",
    "PATCH",
    "PUT",
    "DELETE",
    "OPTIONS",
)
_CORS_ALLOW_HEADERS: tuple[str, ...] = (
    "Authorization",
    "Content-Type",
    "X-Request-ID",
)

try:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
except ModuleNotFoundError as exc:
    logger.warning("rate_limiter.handler_disabled", reason="slowapi_not_installed", error=str(exc))
    _rate_limit_exceeded_handler = None
    RateLimitExceeded = None


def verify_runtime_dependency_guards(settings):
    """Fail fast in strict environments when critical runtime dependencies degrade."""
    strict_environment = _is_strict_startup_environment(settings)

    if strict_environment and not PROMETHEUS_CLIENT_AVAILABLE:
        raise RuntimeError(
            startup_failure_message(
                "metrics",
                "prometheus_client must be installed so /metrics and operational gauges "
                "cannot be silently disabled outside development/test.",
            )
        )

    if strict_environment and (
        _rate_limit_exceeded_handler is None or RateLimitExceeded is None
    ):
        raise RuntimeError(
            startup_failure_message(
                "rate_limiter",
                "slowapi exception handler must be available so rate-limited requests "
                "fail predictably outside development/test.",
            )
        )

    sentry_sdk = None
    if settings.sentry_dsn:
        try:
            import sentry_sdk as sentry_sdk_module
        except ImportError as exc:
            if strict_environment:
                raise RuntimeError(
                    startup_failure_message(
                        "sentry",
                        "SENTRY_DSN is set but sentry-sdk is not installed. "
                        "Install sentry-sdk or unset SENTRY_DSN before startup.",
                    )
                ) from exc
            logger.warning("sentry.disabled", reason="sentry-sdk not installed")
        else:
            sentry_sdk = sentry_sdk_module

    return sentry_sdk


async def verify_database_connectivity() -> None:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise RuntimeError(
            startup_failure_message("database", f"Database connectivity check failed: {exc}")
        ) from exc


async def verify_application_schema() -> None:
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(select(Project.id).limit(1))
    except Exception as exc:
        raise RuntimeError(
            startup_failure_message("schema", f"Application schema verification failed: {exc}")
        ) from exc


async def verify_seed_credentials_on_startup(settings) -> list[dict[str, str]]:
    async with AsyncSessionFactory() as session:
        return await audit_seed_default_passwords(
            session,
            app_env=settings.app_env,
            strict_environment=_is_strict_startup_environment(settings),
        )


async def verify_storage_backend(settings) -> None:
    try:
        await verify_storage_health()
    except Exception as exc:
        raise RuntimeError(
            startup_failure_message(
                "storage",
                f"Storage availability check failed for STORAGE_BACKEND={settings.storage_backend!r}: {exc}",
            )
        ) from exc


def _is_strict_startup_environment(settings) -> bool:
    return settings.app_env.lower() not in ("development", "test")


def _build_redis_client(settings):
    return build_queue_redis_client_from_settings(
        settings,
        client_name="novu-backend",
    )


def build_content_security_policy() -> str:
    return "; ".join(_CONTENT_SECURITY_POLICY_DIRECTIVES)


async def initialize_job_queue(settings):
    if not settings.redis_url:
        logger.info("job_queue.disabled", reason="REDIS_URL_not_set")
        return None

    try:
        redis_client = _build_redis_client(settings)
        await redis_client.ping()  # type: ignore[misc]  # redis.asyncio stubs
        logger.info("job_queue.ready")
        return redis_client
    except Exception as exc:
        if "redis_client" in locals():
            try:
                await redis_client.aclose()
            except Exception as close_exc:
                logger.warning("job_queue.close_failed", error=str(close_exc))

        if _is_strict_startup_environment(settings):
            logger.error("job_queue.unavailable", error=str(exc), fail_fast=True)
            raise RuntimeError(
                startup_failure_message(
                    "redis",
                    f"Redis job queue is unavailable in APP_ENV={settings.app_env!r}. "
                    "Fix REDIS_URL/connectivity before startup.",
                )
            ) from exc

        logger.warning("job_queue.unavailable", error=str(exc), fail_fast=False)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.readiness_started_at_monotonic = time.monotonic()
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
        logger.info("db.schema_check", mode="version_guard", environment=settings.app_env)
        backend_root = Path(__file__).resolve().parent.parent
        from alembic.config import Config as AlembicConfig
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        alembic_cfg = AlembicConfig(str(backend_root / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))

        script_dir = ScriptDirectory.from_config(alembic_cfg)
        expected_head = script_dir.get_current_head()

        async with engine.connect() as connection:
            current_rev = await connection.run_sync(
                lambda sync_conn: MigrationContext.configure(sync_conn).get_current_revision()
            )

        if current_rev != expected_head:
            raise RuntimeError(
                startup_failure_message(
                    "schema",
                    f"Database schema is not at the expected revision. "
                    f"Current: {current_rev!r}, expected head: {expected_head!r}. "
                    "Run 'alembic upgrade head' before starting the application.",
                )
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
    await verify_seed_credentials_on_startup(settings)
    try:
        await verify_storage_backend(settings)
    except Exception as exc:
        startup_checks["storage"] = "error"
        app.state.startup_checks = startup_checks
        logger.critical(
            "storage.startup_validation_failed",
            backend=settings.storage_backend,
            error=str(exc),
            fail_fast=_is_strict_startup_environment(settings),
        )
        if _is_strict_startup_environment(settings):
            raise
        logger.warning("storage.startup_validation_degraded", backend=settings.storage_backend, error=str(exc))
    else:
        startup_checks["storage"] = "ok"
    app.state.startup_checks = startup_checks
    logger.info("startup.checks", **startup_checks)

    async with AsyncSessionFactory() as session:
        token_repository = TokenRepository(session)
        revoked_deleted = await token_repository.delete_expired()
        if revoked_deleted:
            logger.info("startup.revoked_tokens_cleanup", deleted=revoked_deleted)

        password_reset_deleted = await token_repository.delete_expired_password_reset_tokens()
        if password_reset_deleted:
            logger.info("startup.password_reset_tokens_cleanup", deleted=password_reset_deleted)

    app.state.job_queue = await initialize_job_queue(settings)

    # Startup worker detection guard.
    # The system will NOT be considered READY until a worker registers a fresh
    # heartbeat.  Log an ERROR here so operators know the gap exists.
    _startup_redis = app.state.job_queue
    if _startup_redis is not None:
        from app.worker.heartbeat import scan_alive_workers  # noqa: PLC0415
        try:
            _alive_count, _last_seen = await scan_alive_workers(_startup_redis)
            if _alive_count == 0:
                logger.error(
                    "startup.worker_not_detected",
                    reason="no_fresh_heartbeat",
                    last_seen_at=_last_seen,
                    hint="system will not be READY until worker registers a heartbeat",
                )
            elif _alive_count > 0:
                logger.info("startup.worker_detected", alive_count=_alive_count)
            # _alive_count == -1: Redis scan failed (already flagged as unavailable)
        except Exception as exc:
            logger.error("startup.worker_detection_failed", error=str(exc))
    else:
        logger.info("startup.worker_detection_skipped", reason="no_redis")

    yield

    if getattr(app.state, "job_queue", None) is not None:
        await app.state.job_queue.aclose()
        logger.info("job_queue.closed")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_file, settings.log_error_file)
    sentry_sdk = verify_runtime_dependency_guards(settings)
    csp_policy = build_content_security_policy()

    if settings.sentry_dsn and sentry_sdk is not None:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            profiles_sample_rate=settings.sentry_profiles_sample_rate,
        )
        logger.info(
            "sentry.initialized",
            environment=settings.app_env,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            profiles_sample_rate=settings.sentry_profiles_sample_rate,
        )

    docs_url = "/docs" if settings.app_debug else None
    redoc_url = "/redoc" if settings.app_debug else None

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
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
    app.state.readiness_started_at_monotonic = time.monotonic()
    app.state.content_security_policy = csp_policy if settings.csp_enabled else None

    if settings.csp_enabled:
        logger.info("security.csp.enabled", policy=csp_policy)
    else:
        logger.warning("security.csp.disabled", app_env=settings.app_env)

    app.state.limiter = limiter
    if RateLimitExceeded is not None and _rate_limit_exceeded_handler is not None:
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.exception_handler(SQLAlchemyPoolTimeoutError)
    async def db_pool_exhausted_handler(request: Request, exc: SQLAlchemyPoolTimeoutError) -> JSONResponse:
        """DB connection pool exhausted — return 503 instead of 500 and increment metric."""
        route = request.scope.get("route")
        path_template = route.path if route else request.url.path
        logger.error(
            "db.pool_exhausted",
            method=request.method,
            path_template=path_template,
            error=str(exc),
        )
        DB_POOL_EXHAUSTED_TOTAL.inc()
        return JSONResponse(
            status_code=503,
            content={"detail": "Service temporarily unavailable. Please retry in a moment."},
        )

    if settings.require_https:
        app.add_middleware(HTTPSRedirectMiddleware)

    app.add_middleware(AuditMiddleware)
    # Keep the browser-facing CORS profile explicit and minimal.
    # Extend these allowlists only when a real client method/header is required.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=list(_CORS_ALLOW_METHODS),
        allow_headers=list(_CORS_ALLOW_HEADERS),
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next) -> Response:
        start = time.monotonic()
        HTTP_REQUESTS_IN_PROGRESS.labels(method=request.method).inc()
        route = request.scope.get("route")
        path_template = route.path if route else request.url.path
        try:
            response = await call_next(request)
        finally:
            HTTP_REQUESTS_IN_PROGRESS.labels(method=request.method).dec()
        elapsed = time.monotonic() - start
        duration_ms = round(elapsed * 1000)
        if not request.url.path.startswith("/mock-storage"):
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
                path_template=path_template,
                status=response.status_code,
                duration_ms=duration_ms,
            )
        return response

    @app.middleware("http")
    async def request_id_context(request: Request, call_next) -> Response:
        structlog.contextvars.clear_contextvars()
        request_id = sanitize_request_id(request.headers.get("X-Request-ID"))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        if settings.require_https or settings.app_env != "development":
            response.headers["Strict-Transport-Security"] = (
                f"max-age={settings.hsts_max_age}; includeSubDomains"
            )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

        effective_csp_policy = app.state.content_security_policy
        if effective_csp_policy:
            existing_csp_policy = response.headers.get("Content-Security-Policy")
            if existing_csp_policy and existing_csp_policy != effective_csp_policy:
                logger.warning(
                    "security.csp.override",
                    method=request.method,
                    path=request.url.path,
                    existing_policy=existing_csp_policy,
                    enforced_policy=effective_csp_policy,
                )
            response.headers["Content-Security-Policy"] = effective_csp_policy
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        route = request.scope.get("route")
        path_template = route.path if route else request.url.path
        logger.error(
            "http.unhandled_exception",
            exc_type=type(exc).__name__,
            method=request.method,
            path=request.url.path,
            path_template=path_template,
            exc_info=True,
        )
        if settings.sentry_dsn:
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(exc)
            except ImportError:
                pass
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
        effective_csp_policy = app.state.content_security_policy
        if effective_csp_policy:
            response.headers["Content-Security-Policy"] = effective_csp_policy
        return response

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    if settings.is_development:
        from app.api.routes.storage import router as storage_router
        app.include_router(storage_router)

    return app


app = create_app()
