"""Převod RBAC rozhodnutí na HTTP chyby a security-critical audit commit pro správu uživatelů a firem.

Sdílí ho systémová administrace (modul admin) i firemní administrace (D-10, org_users).
"""

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.schemas.auth import AuthUserRead
from app.modules.audit.audit_log import SecurityAuditWriteError, commit_security_critical_audit
from app.modules.identity.rbac import (
    Decision,
)


logger = structlog.get_logger(__name__)

_PERMISSION_DENIED = "Permission denied."
_AUDIT_UNAVAILABLE = "Security audit subsystem unavailable. Retry later."

def enforce_rbac_decision(
    decision: Decision,
    *,
    current_user: AuthUserRead,
    operation: str,
    resource_id: str,
    not_found_detail: str = "Not found.",
) -> None:
    """Translate an app.modules.identity.rbac decision into an HTTP error.

    Targets outside the caller's tenant (or superadmin accounts seen by a company
    admin) answer 404 exactly like a missing record, so the response never
    confirms that another company's user or organization exists.
    """
    if decision == "allow":
        return
    logger.warning(
        "SECURITY_EVENT: admin_operation_denied",
        operation=operation,
        decision=decision,
        user_id=current_user.id,
        role=current_user.role,
        org_id=current_user.organizationId,
        resource_id=resource_id,
    )
    if decision == "not_found":
        raise HTTPException(status_code=404, detail=not_found_detail)
    raise HTTPException(status_code=403, detail=_PERMISSION_DENIED)


async def commit_security_critical_audit_or_503(
    session: AsyncSession,
    *,
    current_user: AuthUserRead,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict,
) -> None:
    """Commit staged changes together with their audit row, or roll both back."""
    try:
        await commit_security_critical_audit(
            session,
            current_user_id=current_user.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
        )
    except SecurityAuditWriteError as exc:
        await session.rollback()
        logger.error(
            "admin.security_audit_enforcement_failed",
            action=action,
            admin_id=current_user.id,
            resource_id=resource_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail=_AUDIT_UNAVAILABLE) from exc
