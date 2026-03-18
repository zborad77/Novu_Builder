from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.bootstrap import ensure_dev_seed
from app.db.session import AsyncSessionFactory, engine
from app.storage.local_photo_storage import STORAGE_ROOT


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with AsyncSessionFactory() as session:
        await ensure_dev_seed(session)

    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="New target backend skeleton for FotoNabidka.",
        debug=settings.app_debug,
        lifespan=lifespan,
    )
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
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    app.mount("/mock-storage", StaticFiles(directory=STORAGE_ROOT), name="mock-storage")
    return app


app = create_app()
