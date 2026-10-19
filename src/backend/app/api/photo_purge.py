"""Permanent photo deletion shared by the tenant and system administration routes."""

from __future__ import annotations

import structlog
from fastapi import HTTPException

from app.core.audit import SecurityAuditWriteError, commit_security_critical_audit
from app.core.config import get_settings
from app.core.purge_ledger import PurgeLedgerError, append_purge_entry
from app.models import ProjectPhoto
from app.schemas.auth import AuthUserRead
from app.schemas.photo import PurgePhotoResponse
from app.services.photo_service import PhotoService

logger = structlog.get_logger(__name__)

_LEDGER_UNAVAILABLE = "Photo purge ledger unavailable. Retry later."


async def purge_photo_with_audit(
    photo_service: PhotoService,
    photo: ProjectPhoto,
    *,
    actor: AuthUserRead,
    audit_action: str,
    organization_id: str,
) -> PurgePhotoResponse:
    """Authorise, record, audit and execute a permanent deletion. Safe to repeat.

    1. The purge is appended to the out-of-database ledger (fsync), then
       ``purge_pending``, expired case exports and removed markers are committed
       together with a security-critical audit row. If the ledger or the audit
       cannot be written nothing changes (503). A ledger entry whose commit then
       fails only records an authorised intent; re-applying it is harmless.
    2. Storage objects are removed. If storage is unavailable the photo stays
       ``purge_pending`` (hidden, not restorable) and the worker retries.
    A photo already ``deleted`` has no stored objects left and is reported purged.
    """
    # Captured up front: after a rollback the ORM instance is expired.
    photo_id = photo.id
    case_id = photo.project_id
    if photo.status == "deleted":
        return PurgePhotoResponse(imageId=photo_id, status="purged")

    if photo.status != "purge_pending":
        settings = get_settings()
        ledger_path = settings.photo_purge_ledger_path.strip()
        if not ledger_path and not settings.is_development:
            logger.error("photo.purge_ledger_not_configured", photo_id=photo_id)
            raise HTTPException(status_code=503, detail=_LEDGER_UNAVAILABLE)

        previous_status = photo.status
        session = photo_service.repository.session
        staged = await photo_service.stage_purge(photo, actor_user_id=actor.id)
        if ledger_path:
            try:
                append_purge_entry(
                    ledger_path,
                    {
                        "photo_id": photo_id,
                        "case_id": case_id,
                        "org_id": organization_id,
                        "actor_id": actor.id,
                        "action": audit_action,
                    },
                )
            except PurgeLedgerError as exc:
                await session.rollback()
                logger.error("photo.purge_ledger_write_failed", photo_id=photo_id, error=str(exc))
                raise HTTPException(status_code=503, detail=_LEDGER_UNAVAILABLE) from exc
        try:
            await commit_security_critical_audit(
                session,
                current_user_id=actor.id,
                action=audit_action,
                resource_type="image",
                resource_id=photo_id,
                detail={
                    "case_id": case_id,
                    "target_org": organization_id,
                    "previous_status": previous_status,
                    **staged,
                },
            )
        except SecurityAuditWriteError as exc:
            await session.rollback()
            logger.error("photo.purge_audit_enforcement_failed", photo_id=photo_id, error=str(exc))
            raise HTTPException(status_code=503, detail="Security audit subsystem unavailable. Retry later.") from exc
        # Also in the application log archive (second, independent copy).
        logger.warning(
            "photo.purge_authorized",
            photo_id=photo_id,
            case_id=case_id,
            org_id=organization_id,
            actor_id=actor.id,
            action=audit_action,
        )

    purged = await photo_service.complete_purge(photo)
    return PurgePhotoResponse(imageId=photo_id, status="purged" if purged else "purge_pending")
