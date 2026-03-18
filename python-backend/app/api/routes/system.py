from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter()


@router.get("/")
async def root() -> dict:
    settings = get_settings()
    return {
        "message": f"{settings.app_name} Python backend skeleton",
        "status": "ok",
        "environment": settings.app_env
    }


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "python-backend",
        "debug": settings.app_debug
    }
