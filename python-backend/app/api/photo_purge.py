"""Permanent photo deletion shared by the tenant and system administration routes."""

from __future__ import annotations

import structlog
from fastapi import HTTPException

from app.core.audit import SecurityAuditWriteError, commit_security_critical_audit
from app.models import ProjectPhoto
from app.schemas.auth import AuthUserRead
from app.schemas.photo import PurgePhotoResponse
from app.services.photo_service import PhotoService

logger = structlog.get_logger(__name__)


async def purge_photo_with_audit(
    photo_service: PhotoService,
    photo: ProjectPhoto,
    *,
    actor: AuthUserRead,
    audit_action: str,
    organization_id: str,
) -> PurgePhotoResponse:
    """Authorise, audit and execute a permanent deletion. Safe to repeat.

    1. ``purge_pending`` + expired case exports are committed together with a
       security-critical audit row; if the audit cannot be written nothing changes.
    2. Storage objects are removed. If storage is unavailable the photo stays
       ``purge_pending`` (hidden, not restorable) and the worker retries.
    A photo already ``deleted`` has no stored objects left and is reported purged.
    """
    # Captured up front: after a rollback the ORM instance is expired.
    photo_id = photo.id
    if photo.status == "deleted":
        return PurgePhotoResponse(imageId=photo_id, status="purged")

    if photo.status != "purge_pending":
        previous_status = photo.status
        session = photo_service.repository.session
        exports_expired = await photo_service.stage_purge(photo, actor_user_id=actor.id)
        try:
            await commit_security_critical_audit(
                session,
                current_user_id=actor.id,
                action=audit_action,
                resource_type="image",
                resource_id=photo.id,
                detail={
                    "case_id": photo.project_id,
                    "target_org": organization_id,
                    "previous_status": previous_status,
                    "exports_expired": exports_expired,
                },
            )
        except SecurityAuditWriteError as exc:
            await session.rollback()
            logger.error("photo.purge_audit_enforcement_failed", photo_id=photo_id, error=str(exc))
            raise HTTPException(status_code=503, detail="Security audit subsystem unavailable. Retry later.") from exc
        # Purge ledger line: survives a database restore in the log archive and is
        # what docs/security/PHOTO_DELETION.md re-applies after restoring a backup.
        logger.warning(
            "photo.purge_authorized",
            photo_id=photo.id,
            case_id=photo.project_id,
            org_id=organization_id,
            actor_id=actor.id,
            action=audit_action,
        )

    purged = await photo_service.complete_purge(photo)
    return PurgePhotoResponse(imageId=photo_id, status="purged" if purged else "purge_pending")
