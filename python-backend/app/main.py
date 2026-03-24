import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
import structlog

from app.api.router import api_router
from app.core.audit import AuditMiddleware
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.bootstrap import ensure_dev_seed
from app.db.session import AsyncSessionFactory, engine
from app.models import Project
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
        logger.info("db.schema_bootstrap", mode="alembic_upgrade_head", environment=settings.app_env)
        _BACKEND_ROOT = Path(__file__).resolve().parent.parent
        from alembic.config import Config as AlembicConfig
        from alembic import command as alembic_command
        alembic_cfg = AlembicConfig(str(_BACKEND_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
        alembic_command.upgrade(alembic_cfg, "head")
        logger.info("db.migrations", status="head")

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

    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_file, settings.log_error_file)

    # In production, hide docs endpoints and disable debug tracebacks
    docs_url = "/docs" if settings.app_debug else None
    redoc_url = "/redoc" if settings.app_debug else None

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
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
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000)
        if not request.url.path.startswith("/mock-storage"):
            logger.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
        return response

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.mount("/mock-storage", StaticFiles(directory=STORAGE_ROOT), name="mock-storage")
    return app


app = create_app()
