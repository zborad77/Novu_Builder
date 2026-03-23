import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
import structlog

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.bootstrap import ensure_dev_seed
from app.db.session import AsyncSessionFactory, engine
from app.models import Project
from app.repositories.token_repository import TokenRepository
from app.storage.local_photo_storage import STORAGE_ROOT

logger = structlog.get_logger(__name__)


async def verify_database_connectivity() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def verify_application_schema() -> None:
    async with AsyncSessionFactory() as session:
        await session.execute(select(Project.id).limit(1))


def verify_storage_root() -> None:
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    probe_file = STORAGE_ROOT / ".startup-write-check"
    probe_file.write_text("ok", encoding="utf-8")
    probe_file.unlink(missing_ok=True)


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
        logger.info("db.schema_bootstrap", mode="migrations_only", environment=settings.app_env)

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
    configure_logging(settings.log_level, settings.log_file)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="New target backend skeleton for FotoNabidka.",
        debug=settings.app_debug,
        lifespan=lifespan,
    )
    app.state.startup_checks = {
        "database": "pending",
        "schema": "pending",
        "storage": "pending",
    }
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000)
        # Skip noisy health/static calls in logs
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
