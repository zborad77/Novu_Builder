"""
Authenticated static file serving — replaces the unauthenticated /mock-storage mount.

Path structure:
  /mock-storage/projects/{project_id}/...   → photos, previews, AI inputs
  /mock-storage/exports/{case_id}/...       → generated export files

Access is scoped to the current user's organization. Superadmin bypasses org filter.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import get_current_user, get_project_service, resolve_org_id
from app.core.config import get_settings
from app.schemas.auth import AuthUserRead
from app.services.project_service import ProjectService
from app.storage.local_photo_storage import STORAGE_ROOT

router = APIRouter()

_ALLOWED_PREFIXES = ("projects", "exports")


@router.get("/mock-storage/{file_path:path}")
async def serve_storage_file(
    file_path: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
):
    settings = get_settings()
    if settings.storage_backend != "local":
        raise HTTPException(status_code=404, detail="File not found.")

    # Resolve and guard against path traversal
    absolute_path = (STORAGE_ROOT / file_path).resolve()
    try:
        absolute_path.relative_to(STORAGE_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found.")

    # Parse: <prefix>/<case_id>/...
    parts = Path(file_path).parts
    if len(parts) < 2 or parts[0] not in _ALLOWED_PREFIXES:
        raise HTTPException(status_code=404, detail="File not found.")

    case_id = parts[1]

    # Validate org access
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="File not found.")

    if not absolute_path.exists() or not absolute_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(absolute_path)
