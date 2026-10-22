"""Streamování exportů klientům (NC-007 etapa 1, kap. 6.2).

``GET /files/exports/{export_id}`` – stejná role a stejné vyhledání v rámci
firmy jako ``GET /exports/{export_id}`` (``require_manager`` + kontrola
zakázky). Jen dokončený, neexpirovaný a existující export, jinak 404.
Každé úspěšné stažení zapíše audit ``export.downloaded``.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.modules.audit.public import AuditEntry, log_cross_tenant_denied, record_audit_entries
from app.modules.exports.api.deps import get_export_service
from app.modules.exports.export_service import ExportService
from app.modules.identity.public import AuthUserRead, require_manager, resolve_org_id
from app.modules.workflow.public import ProjectService, get_project_service
from app.platform.config import get_settings
from app.platform.db.session import get_db_session
from app.platform.http.file_streaming import (
    FILE_RESPONSES_DOC,
    GENERIC_CONTENT_TYPE,
    storage_file_response,
)
from app.platform.http.limiter import limiter

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["files"])

_NOT_FOUND_DETAIL = "Export not found."

# Typy souborů, které export skutečně vyrábí; cokoli jiného je octet-stream.
_EXPORT_CONTENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".zip": "application/zip",
}


def export_content_type(file_name: str | None) -> str:
    suffix = PurePosixPath(file_name or "").suffix.lower()
    return _EXPORT_CONTENT_TYPES.get(suffix, GENERIC_CONTENT_TYPE)


def _not_found(current_user: AuthUserRead, export_id: str) -> HTTPException:
    if not current_user.isSuperAdmin:
        log_cross_tenant_denied(
            logger,
            resource="export_file",
            resource_id=export_id,
            user_id=current_user.id,
            org_id=current_user.organizationId,
        )
    return HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)


@router.get(
    "/files/exports/{export_id}",
    response_class=Response,
    responses=FILE_RESPONSES_DOC,
)
@limiter.limit(get_settings().rate_limit_file_download)
async def download_export_file(
    export_id: str,
    request: Request,
    current_user: AuthUserRead = Depends(require_manager),
    project_service: ProjectService = Depends(get_project_service),
    export_service: ExportService = Depends(get_export_service),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    org_id = resolve_org_id(current_user)
    export = await export_service.get_downloadable_export(
        export_id,
        organization_id=org_id,
        is_superadmin_context=current_user.isSuperAdmin,
    )
    if export is None:
        raise _not_found(current_user, export_id)
    if not current_user.isSuperAdmin:
        project = await project_service.get_project(export.project_id, organization_id=org_id)
        if not project:
            raise _not_found(current_user, export_id)

    storage_key = export.storage_key
    assert storage_key is not None  # get_downloadable_export vrací jen exporty s klíčem
    response = await storage_file_response(
        request_headers=request.headers,
        storage_key=storage_key,
        content_type=export_content_type(export.file_name),
        filename=export.file_name,
        disposition="attachment",
    )
    if response is None:
        logger.error(
            "export.artifact_missing_on_download",
            export_id=export.id,
            project_id=export.project_id,
        )
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)

    if response.status_code in (200, 206):
        await record_audit_entries(
            session,
            [
                AuditEntry(
                    action="export.downloaded",
                    resource_type="export",
                    resource_id=export.id,
                    user_id=current_user.id,
                    user_email=current_user.email,
                    org_id=org_id or current_user.organizationId or None,
                    ip=request.client.host if request.client else None,
                    detail={
                        "caseId": export.project_id,
                        "exportType": export.export_type,
                        "partial": response.status_code == 206,
                        "impersonatedBy": current_user.impersonatedBy,
                    },
                )
            ],
        )
    return response
