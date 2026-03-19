from fastapi import APIRouter, Request

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
async def health(request: Request) -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "python-backend",
        "debug": settings.app_debug,
        "ready": all(value == "ok" for value in request.app.state.startup_checks.values()),
        "startupChecks": request.app.state.startup_checks,
    }
