import json
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Deque
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_analysis_service, get_auth_redis, get_job_queue, require_admin_capability, require_superadmin
from app.worker.queue import AnalysisJobQueueCapacityExceededError, enqueue_analysis_job
from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.domain import AnalysisJob, AuditLog, Organization, Project, User
from app.schemas.auth import AuthUserRead
from app.schemas.company import (
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserPatch,
    AdminUserRead,
    CompanyCreate,
    CompanyListResponse,
    CompanyPatch,
    CompanyRead,
)
from app.core.limiter import limiter
from app.core.sql_like import LIKE_ESCAPE_CHAR, build_contains_ilike_pattern
from app.core.security import enforce_password_strength
from app.core.audit import SecurityAuditWriteError, commit_security_critical_audit, write_audit_log
from app.repositories.token_repository import SessionTokenRevocation, TokenRepository
from app.services.analysis_service import AnalysisService, to_job_read
from app.services.company_service import CompanyService
from app.services.auth_service import AuthService, hash_password

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def get_company_service(session: AsyncSession = Depends(get_db_session)) -> CompanyService:
    return CompanyService(session)


# ── Companies ──────────────────────────────────────────────────────────────────

@router.get("/companies", response_model=CompanyListResponse)
@limiter.limit(get_settings().rate_limit_admin)
async def list_companies(
    request: Request,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> CompanyListResponse:
    items, total = await service.list_companies(limit=limit, offset=offset)
    return CompanyListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        hasMore=(offset + len(items)) < total,
    )


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().rate_limit_admin_write)
async def create_company(
    request: Request,
    payload: CompanyCreate,
    service: CompanyService = Depends(get_company_service),
    current_user: AuthUserRead = Depends(require_admin_capability("admin:write")),
) -> CompanyRead:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Company name is required.")
    company = await service.create_company(payload)
    await service.write_audit_log(
        current_user_id=current_user.id,
        action="admin.company.create",
        resource_type="company",
        resource_id=company.id,
        detail={"name": company.name},
    )
    return company


@router.get("/companies/{company_id}", response_model=CompanyRead)
@limiter.limit(get_settings().rate_limit_admin)
async def get_company(
    request: Request,
    company_id: str,
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> CompanyRead:
    company = await service.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    return company


@router.patch("/companies/{company_id}", response_model=CompanyRead)
@limiter.limit(get_settings().rate_limit_admin_write)
async def patch_company(
    request: Request,
    company_id: str,
    payload: CompanyPatch,
    service: CompanyService = Depends(get_company_service),
    current_user: AuthUserRead = Depends(require_admin_capability("admin:write")),
) -> CompanyRead:
    updated = await service.patch_company(company_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Company not found.")
    await service.write_audit_log(
        current_user_id=current_user.id,
        action="admin.company.patch",
        resource_type="company",
        resource_id=company_id,
        detail={"changes": payload.model_dump(exclude_unset=True)},
    )
    return updated


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=AdminUserListResponse)
@limiter.limit(get_settings().rate_limit_admin)
async def list_users(
    request: Request,
    org_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> AdminUserListResponse:
    items, total = await service.list_users(
        organization_id=org_id,
        limit=limit,
        offset=offset,
    )
    return AdminUserListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        hasMore=(offset + len(items)) < total,
    )


@router.post("/users", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().rate_limit_admin_write)
async def create_user(
    request: Request,
    payload: AdminUserCreate,
    service: CompanyService = Depends(get_company_service),
    current_user: AuthUserRead = Depends(require_admin_capability("admin:write")),
) -> AdminUserRead:
    if payload.password:
        try:
            enforce_password_strength(payload.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        user = await service.create_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=404, detail="Organization not found.")
    await service.write_audit_log(
        current_user_id=current_user.id,
        action="admin.user.create",
        resource_type="user",
        resource_id=user.id,
        detail={"email": user.email, "role": user.role, "target_org": user.organizationId},
    )
    return user


@router.get("/users/{user_id}", response_model=AdminUserRead)
@limiter.limit(get_settings().rate_limit_admin)
async def get_user(
    request: Request,
    user_id: str,
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> AdminUserRead:
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.patch("/users/{user_id}", response_model=AdminUserRead)
@limiter.limit(get_settings().rate_limit_admin_write)
async def patch_user(
    request: Request,
    user_id: str,
    payload: AdminUserPatch,
    service: CompanyService = Depends(get_company_service),
    current_user: AuthUserRead = Depends(require_admin_capability("admin:write")),
) -> AdminUserRead:
    updated = await service.patch_user(user_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    await service.write_audit_log(
        current_user_id=current_user.id,
        action="admin.user.patch",
        resource_type="user",
        resource_id=user_id,
        detail={"changes": payload.model_dump(exclude_unset=True, exclude={"password"})},
    )
    return updated


class ResetPasswordPayload(BaseModel):
    password: str


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(get_settings().rate_limit_admin_sensitive)
async def reset_user_password(
    request: Request,
    user_id: str,
    payload: ResetPasswordPayload,
    current_user: AuthUserRead = Depends(require_admin_capability("admin:write")),
    session: AsyncSession = Depends(get_db_session),
    auth_redis: Annotated[object | None, Depends(get_auth_redis)] = None,
) -> None:
    try:
        enforce_password_strength(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    target = await session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    target.password_hash = hash_password(payload.password)
    reset_timestamp = datetime.now(UTC).replace(microsecond=0)
    token_repository = TokenRepository(session, redis=auth_redis)
    AuthService.invalidate_user_token_state(target, now=reset_timestamp)
    revocations: list[SessionTokenRevocation] = await token_repository.revoke_all_user_sessions(
        target.id,
        now=reset_timestamp,
        commit=False,
    )

    logger.warning(
        "admin.user.reset_password",
        admin_id=current_user.id,
        target_user_id=user_id,
        target_email=target.email,
    )

    try:
        await commit_security_critical_audit(
            session,
            current_user_id=current_user.id,
            action="admin.user.reset_password",
            resource_type="user",
            resource_id=user_id,
            detail={"target_email": target.email, "target_org": target.organization_id},
        )
    except SecurityAuditWriteError as exc:
        await session.rollback()
        logger.error(
            "admin.user.reset_password_audit_enforcement_failed",
            admin_id=current_user.id,
            target_user_id=user_id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="Security audit subsystem unavailable. Retry later.") from exc

    for record in revocations:
        await token_repository.cache_revoked_token(record.jti, record.expires_at)


# ── Analysis Jobs (all orgs) ───────────────────────────────────────────────────

# Maximum length for error messages returned to clients.
# Raw exception text may contain internal file paths or stack details.
_ADMIN_JOB_MAX_ERROR_LEN = 500

# Key name fragments that suggest the value may contain a sensitive path or URL.
# Applied to inputPayload / outputSummary dict keys (case-insensitive substring match).
_SENSITIVE_KEY_FRAGMENTS: frozenset[str] = frozenset({
    "path", "file", "filepath", "storage", "url",
})

# String markers that identify raw filesystem paths in string payloads.
_SENSITIVE_PATH_MARKERS: tuple[str, ...] = ("/app/", "\\")


def _enrich_job(job: AnalysisJob, case_title: str, org_id: str, org_name: str) -> dict:
    base = to_job_read(job)
    base["caseTitle"] = case_title
    base["orgId"] = org_id
    # NOTE:
    # orgName is exposed for admin usability.
    # Be aware it may contain business-sensitive information.
    base["orgName"] = org_name
    return base


def _sanitize_payload(payload: object) -> tuple[object, bool]:
    """Return (sanitized_payload, was_changed).

    dict  — mask values whose key name contains a sensitive fragment.
    str   — replace with "[REDACTED_PATH]" if it looks like a filesystem path.
    other — returned unchanged.
    """
    if payload is None:
        return payload, False

    if isinstance(payload, dict):
        result: dict = {}
        changed = False
        for key, value in payload.items():
            if any(frag in key.lower() for frag in _SENSITIVE_KEY_FRAGMENTS):
                result[key] = "[REDACTED]"
                changed = True
            else:
                result[key] = value
        return result, changed

    if isinstance(payload, str):
        if any(marker in payload for marker in _SENSITIVE_PATH_MARKERS):
            return "[REDACTED_PATH]", True
        return payload, False

    return payload, False


def _sanitize_admin_job(job_dict: dict) -> dict:
    """Strip or truncate fields that expose internal implementation details.

    Changes made (new fields added, none removed except errorTraceback):

    errorTraceback        — removed entirely; full Python stack trace exposes
                            file paths, library versions and code structure.
    errorMessage          — truncated to _ADMIN_JOB_MAX_ERROR_LEN chars if longer;
                            suffix "..." marks the cut.
    errorMessageTruncated — True when errorMessage was cut, False otherwise.
    inputPayload          — dict values whose key suggests a path/URL are masked
                            as "[REDACTED]"; string payloads containing filesystem
                            markers become "[REDACTED_PATH]".
    inputPayloadSanitized — True when any masking was applied to inputPayload.
    outputSummary         — same masking rules as inputPayload.
    outputSummarySanitized — True when any masking was applied to outputSummary.

    All other fields are retained (status, timing, org context, high-level AI
    results) as they are legitimate operational metadata for superadmin use.
    """
    sanitized = {k: v for k, v in job_dict.items() if k != "errorTraceback"}

    # ── errorMessage truncation ──────────────────────────────────────────────
    msg = sanitized.get("errorMessage")
    if msg and len(msg) > _ADMIN_JOB_MAX_ERROR_LEN:
        sanitized["errorMessage"] = msg[:_ADMIN_JOB_MAX_ERROR_LEN] + "..."
        sanitized["errorMessageTruncated"] = True
    else:
        sanitized["errorMessageTruncated"] = False

    # ── inputPayload path/url masking ────────────────────────────────────────
    clean_payload, payload_changed = _sanitize_payload(sanitized.get("inputPayload"))
    sanitized["inputPayload"] = clean_payload
    sanitized["inputPayloadSanitized"] = payload_changed

    # ── outputSummary path/url masking ───────────────────────────────────────
    clean_summary, summary_changed = _sanitize_payload(sanitized.get("outputSummary"))
    sanitized["outputSummary"] = clean_summary
    sanitized["outputSummarySanitized"] = summary_changed

    return sanitized


@router.get("/jobs", response_model=list[dict])
@limiter.limit(get_settings().rate_limit_admin)
async def list_all_jobs(
    request: Request,
    job_status: str | None = Query(default=None, alias="status"),
    org_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    _: AuthUserRead = Depends(require_admin_capability("admin:jobs")),
) -> list[dict]:
    query = (
        select(AnalysisJob, Project.title, Project.organization_id, Organization.name)
        .join(Project, AnalysisJob.project_id == Project.id)
        .join(Organization, Project.organization_id == Organization.id)
        .order_by(AnalysisJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if job_status:
        query = query.where(AnalysisJob.status == job_status)
    if org_id:
        query = query.where(Project.organization_id == org_id)

    result = await session.execute(query)
    rows = result.all()
    return [
        _sanitize_admin_job(_enrich_job(job, case_title, oid, org_name))
        for job, case_title, oid, org_name in rows
    ]


@router.get("/jobs/{job_id}", response_model=dict)
@limiter.limit(get_settings().rate_limit_admin)
async def get_admin_job(
    request: Request,
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
    _: AuthUserRead = Depends(require_admin_capability("admin:jobs")),
) -> dict:
    job = await session.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found.")

    # Enrich with case + org info
    project = await session.get(Project, job.project_id)
    case_title = project.title if project else ""
    org_id = project.organization_id if project else ""
    org_name = ""
    if project:
        org = await session.get(Organization, project.organization_id)
        org_name = org.name if org else ""

    return _sanitize_admin_job(_enrich_job(job, case_title, org_id, org_name))


@router.post("/jobs/{job_id}/retry", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(get_settings().rate_limit_admin_write)
async def admin_retry_job(
    request: Request,
    job_id: str,
    current_user: AuthUserRead = Depends(require_admin_capability("admin:jobs")),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    session: AsyncSession = Depends(get_db_session),
    job_queue=Depends(get_job_queue),
) -> dict:
    # organization_id=None is intentional: superadmin operates across all orgs
    settings = get_settings()
    new_job = await analysis_service.retry_job(
        job_id,
        organization_id=None,
        is_superadmin_context=True,
        job_queue=job_queue,
    )
    if new_job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    if job_queue is not None:
        try:
            await enqueue_analysis_job(
                job_queue,
                job_id=new_job.id,
                project_id=new_job.project_id,
                organization_id=None,
                is_superadmin_context=True,
                max_depth=settings.analysis_queue_max_depth,
            )
        except AnalysisJobQueueCapacityExceededError:
            await analysis_service.cancel_analysis_job(
                new_job.id,
                organization_id=None,
                is_superadmin_context=True,
            )
            raise HTTPException(status_code=429, detail="Analysis queue is full. Please retry later.")
    else:
        logger.warning("job_queue.unavailable", job_id=new_job.id, action="admin_retry_job")

    original = await session.get(AnalysisJob, job_id)
    await write_audit_log(
        session,
        current_user_id=current_user.id,
        action="admin.job.retry",
        resource_type="analysis_job",
        resource_id=job_id,
        detail={
            "new_job_id": new_job.id,
            "retry_count": new_job.retry_count,
            "original_status": original.status if original else None,
        },
    )

    return {"newJobId": new_job.id, "status": new_job.status, "retryCount": new_job.retry_count}


@router.post("/jobs/{job_id}/reprocess", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(get_settings().rate_limit_admin_write)
async def admin_reprocess_dead_letter_job(
    request: Request,
    job_id: str,
    current_user: AuthUserRead = Depends(require_admin_capability("admin:jobs")),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    session: AsyncSession = Depends(get_db_session),
    job_queue=Depends(get_job_queue),
) -> dict:
    settings = get_settings()
    try:
        job = await analysis_service.reprocess_dead_letter_job(
            job_id,
            organization_id=None,
            is_superadmin_context=True,
            job_queue=job_queue,
        )
    except AnalysisJobQueueCapacityExceededError:
        raise HTTPException(status_code=429, detail="Analysis queue is full. Please retry later.")
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    await write_audit_log(
        session,
        current_user_id=current_user.id,
        action="admin.job.reprocess",
        resource_type="analysis_job",
        resource_id=job_id,
        detail={
            "status": job.status,
            "attempt_count": job.attempt_count,
            "queue_max_depth": settings.analysis_queue_max_depth,
        },
    )

    return {"jobId": job.id, "status": job.status, "attemptCount": job.attempt_count}


# ── Logs ───────────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=list[str])
@limiter.limit(get_settings().rate_limit_admin)
async def get_recent_logs(
    request: Request,
    lines: int = Query(default=200, ge=10, le=2000),
    _: AuthUserRead = Depends(require_superadmin),
) -> list[str]:
    settings = get_settings()
    if not settings.log_file:
        raise HTTPException(
            status_code=409,
            detail="Log file not configured. Set LOG_FILE env variable.",
        )
    log_path = Path(settings.log_file)
    if not log_path.exists():
        return []

    # Efficient tail — read last N lines without loading whole file
    with log_path.open("rb") as f:
        recent_lines: Deque[str] = deque(maxlen=lines)
        for line in f:
            recent_lines.append(line.decode("utf-8", errors="replace").rstrip())
    return list(recent_lines)


# ── Audit Trail ────────────────────────────────────────────────────────────────

@router.get("/audit", response_model=list[dict])
@limiter.limit(get_settings().rate_limit_admin)
async def get_audit_log(
    request: Request,
    org_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=10, le=2000),
    session: AsyncSession = Depends(get_db_session),
    _: AuthUserRead = Depends(require_superadmin),
) -> list[dict]:
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if org_id:
        query = query.where(AuditLog.org_id == org_id)
    if action:
        query = query.where(
            AuditLog.action.ilike(
                build_contains_ilike_pattern(action),
                escape=LIKE_ESCAPE_CHAR,
            )
        )
    if user_id:
        query = query.where(AuditLog.user_id == user_id)

    result = await session.execute(query)
    rows = result.scalars().all()

    return [
        {
            "id": row.id,
            "userId": row.user_id,
            "userEmail": row.user_email,
            "orgId": row.org_id,
            "action": row.action,
            "resourceType": row.resource_type,
            "resourceId": row.resource_id,
            "detail": (
                json.dumps(row.detail, ensure_ascii=False)
                if isinstance(row.detail, dict)
                else row.detail
            ),
            "impersonatedBy": row.impersonated_by,
            "ip": row.ip,
            "createdAt": row.created_at.isoformat(),
        }
        for row in rows
    ]


# ── Impersonation ──────────────────────────────────────────────────────────────

class ImpersonateResponse(BaseModel):
    accessToken: str
    userId: str
    userEmail: str
    userFullName: str
    orgId: str
    role: str
    expiresInMinutes: int = 15


@router.post("/impersonate/{user_id}", response_model=ImpersonateResponse)
@limiter.limit(get_settings().rate_limit_admin_sensitive)
async def impersonate_user(
    request: Request,
    user_id: str,
    current_user: AuthUserRead = Depends(require_admin_capability("admin:impersonate")),
    session: AsyncSession = Depends(get_db_session),
) -> ImpersonateResponse:
    """
    Issue a short-lived (15 min) access token scoped to the target user.
    The token carries impersonated_by=<admin_id> for audit trail.
    """
    target = await session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.is_superadmin:
        raise HTTPException(status_code=403, detail="Cannot impersonate another superadmin.")

    settings = get_settings()
    import jwt as pyjwt

    jti = uuid4().hex
    exp = datetime.now(UTC) + timedelta(minutes=15)
    token = pyjwt.encode(
        {
            "sub": target.id,
            "jti": jti,
            "type": "access",
            "exp": exp,
            "ver": AuthService._user_token_version(target),
            "impersonated_by": current_user.id,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    try:
        await commit_security_critical_audit(
            session,
            current_user_id=current_user.id,
            action="admin.impersonate",
            resource_type="user",
            resource_id=target.id,
            detail={
                "impersonated_email": target.email,
                "impersonated_role": target.role,
                "impersonated_org": target.organization_id,
                "expires_minutes": 15,
            },
        )
    except SecurityAuditWriteError as exc:
        await session.rollback()
        logger.error(
            "admin.impersonate_audit_enforcement_failed",
            admin_id=current_user.id,
            target_user_id=target.id,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="Security audit subsystem unavailable. Retry later.") from exc

    return ImpersonateResponse(
        accessToken=token,
        userId=target.id,
        userEmail=target.email,
        userFullName=target.full_name,
        orgId=target.organization_id,
        role=target.role,
        expiresInMinutes=15,
    )
