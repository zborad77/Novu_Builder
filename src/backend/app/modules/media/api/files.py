"""Streamování fotek klientům (NC-007 etapa 1, kap. 6.1).

``GET /files/images/{image_id}/{variant}`` čte variantu fotky z aktivního
úložiště po blocích a vrací ji přímo – žádné přesměrování a žádná URL
úložiště. Klíč úložiště se bere jen z DB.

Oprávnění: přihlášený uživatel, fotka patří jeho firmě a je aktivní
(``PhotoRepository.get_photo_by_id_in_org`` filtruje ``status == "active"``).
Cizí firma, smazaná, purgnutá i neexistující fotka, neznámá i nehotová
varianta vrací stejnou 404.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import Response

from app.modules.audit.public import log_cross_tenant_denied
from app.modules.identity.public import AuthUserRead, get_current_user, resolve_org_id
from app.modules.media.api.deps import get_photo_service
from app.modules.media.photo_service import PHOTO_FILE_VARIANTS, PhotoService, variant_storage_key
from app.platform.config import get_settings
from app.platform.http.file_streaming import (
    FILE_RESPONSES_DOC,
    Disposition,
    image_content_type,
    storage_file_response,
)
from app.platform.http.limiter import limiter

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["files"])

_NOT_FOUND_DETAIL = "Image not found."


async def stream_photo_variant(
    *,
    request: Request,
    image_id: str,
    variant: str,
    current_user: AuthUserRead,
    photo_service: PhotoService,
    resource: str,
    fallback_to_original: bool = False,
) -> Response:
    """Ověří firmu a stav fotky a streamuje požadovanou variantu (jinak 404).

    ``fallback_to_original`` používá jen starý ``/images/{id}/preview``: dokud
    náhled není hotový, vrací originál (stejně jako dřív ``preview.url or url``).
    """
    if variant not in PHOTO_FILE_VARIANTS:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    org_id = resolve_org_id(current_user)
    photo = await photo_service.get_active_photo_in_org(image_id, organization_id=org_id)
    if photo is None:
        if not current_user.isSuperAdmin:
            log_cross_tenant_denied(
                logger,
                resource=resource,
                resource_id=image_id,
                user_id=current_user.id,
                org_id=current_user.organizationId,
            )
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)

    served_variant = variant
    storage_key = variant_storage_key(photo, variant)
    if storage_key is None and fallback_to_original:
        served_variant = "original"
        storage_key = variant_storage_key(photo, served_variant)
    if storage_key is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)

    disposition: Disposition = "attachment" if served_variant == "original" and not fallback_to_original else "inline"
    response = await storage_file_response(
        request_headers=request.headers,
        storage_key=storage_key,
        content_type=image_content_type(photo.mime_type),
        filename=photo.original_filename,
        disposition=disposition,
    )
    if response is None:
        logger.warning(
            "photo.file_missing_in_storage",
            photo_id=photo.id,
            project_id=photo.project_id,
            variant=served_variant,
        )
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    return response


@router.get(
    "/files/images/{image_id}/{variant}",
    response_class=Response,
    responses=FILE_RESPONSES_DOC,
)
@limiter.limit(get_settings().rate_limit_file_download)
async def download_image_file(
    image_id: str,
    variant: str,
    request: Request,
    current_user: AuthUserRead = Depends(get_current_user),
    photo_service: PhotoService = Depends(get_photo_service),
) -> Response:
    return await stream_photo_variant(
        request=request,
        image_id=image_id,
        variant=variant,
        current_user=current_user,
        photo_service=photo_service,
        resource="image_file",
    )
