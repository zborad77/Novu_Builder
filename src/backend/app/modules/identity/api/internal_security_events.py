"""Příjem bezpečnostních událostí z gateway (NC-007 etapa 1, kap. 6.4).

``POST /internal/security-events`` existuje jen v zóně gateway (exposure),
kde ``GatewaySignatureMiddleware`` pustí dál pouze požadavek s platným
podpisem gateway. Požadavek s hlavičkou ``Authorization`` dostane 404 (stejné
tělo jako exposure guard), takže se na endpoint nedá dostat s uživatelským
tokenem ani přes průchozí ``/bff/api``. Zápis do ``audit_logs`` jde přes
veřejné API modulu audit: ``action = "gateway.<type>"``,
``resource_type = "web_session"``.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.public import (
    AUDIT_POLICY_SECURITY_CRITICAL,
    AuditEntry,
    SecurityAuditWriteError,
    mark_request_audited,
    record_audit_entries,
)
from app.modules.identity.schemas.security_events import (
    SecurityEventBatch,
    SecurityEventIn,
    SecurityEventsAccepted,
)
from app.platform.config import get_settings
from app.platform.db.session import get_db_session
from app.platform.http.gateway_auth import GATEWAY_KEY_ID_STATE
from app.platform.http.limiter import gateway_key_rate_limit_key, limiter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


async def reject_user_credentials(request: Request) -> None:
    """Jakákoli hlavička ``Authorization`` = 404, ještě před validací těla."""
    if "authorization" in request.headers:
        logger.warning("SECURITY_EVENT: internal_route_with_authorization", path=request.url.path)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _audit_entry(event: SecurityEventIn, *, gateway_key_id: str | None) -> AuditEntry:
    return AuditEntry(
        action=f"gateway.{event.type}",
        resource_type="web_session",
        resource_id=event.sessionRef,
        user_id=event.userId,
        org_id=event.organizationId,
        ip=event.clientIp,
        detail={
            "occurredAt": event.occurredAt.isoformat(),
            "sessionRef": event.sessionRef,
            "requestId": event.requestId,
            "gatewayKeyId": gateway_key_id,
            "event": event.detail,
        },
    )


@router.post(
    "/security-events",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SecurityEventsAccepted,
    dependencies=[Depends(reject_user_credentials)],
)
@limiter.limit(get_settings().rate_limit_security_events, key_func=gateway_key_rate_limit_key)
async def ingest_security_events(
    request: Request,
    payload: SecurityEventBatch,
    session: AsyncSession = Depends(get_db_session),
) -> SecurityEventsAccepted:
    gateway_key_id = getattr(request.state, GATEWAY_KEY_ID_STATE, None)
    entries = [_audit_entry(event, gateway_key_id=gateway_key_id) for event in payload.events]
    try:
        accepted = await record_audit_entries(session, entries, policy=AUDIT_POLICY_SECURITY_CRITICAL)
    except SecurityAuditWriteError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security audit subsystem unavailable. Retry later.",
        ) from exc
    # Řádky zapsala routa; AuditMiddleware nemá přidávat obecný záznam požadavku.
    mark_request_audited(request)
    return SecurityEventsAccepted(accepted=accepted)
