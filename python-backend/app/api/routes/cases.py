from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import (
    get_case_action_service,
    get_current_user,
    get_project_service,
    require_manager,
    resolve_org_id,
)
from app.case_workflow.case_actions import CaseActionError, CaseActionService
from app.core.config import get_settings
from app.core.limiter import limiter
from app.schemas.auth import AuthUserRead
from app.schemas.project import (
    CaseActionRequest,
    ProjectCreate,
    ProjectCreateResponse,
    ProjectDetail,
    ProjectDuplicateRequest,
    ProjectListResponse,
    ProjectPatch,
    ProjectProposalDraftPatch,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=ProjectListResponse)
@limiter.limit(get_settings().rate_limit_read_list)
async def list_cases(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    org_id: str | None = Query(default=None, description="Super-admin only: filter by organization"),
    limit: int = Query(default=200, ge=1, le=500),
    cursor: str | None = Query(default=None, description="Opaque cursor for next-page navigation"),
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUserRead = Depends(get_current_user),
) -> ProjectListResponse:
    effective_org_id = (org_id if org_id else None) if current_user.isSuperAdmin else current_user.organizationId
    # Server-side hard cap: CASES_PAGE_LIMIT_MAX overrides any client-supplied limit
    # that exceeds the operator-configured ceiling, preventing memory spikes.
    hard_limit = min(limit, get_settings().cases_page_limit_max)
    items, next_cursor = await service.list_projects(
        organization_id=effective_org_id,
        status=status_filter,
        search=search,
        limit=hard_limit,
        cursor=cursor,
    )
    return ProjectListResponse(items=items, total=len(items), next_cursor=next_cursor)


@router.post("", response_model=ProjectCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: ProjectCreate,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUserRead = Depends(get_current_user),
) -> ProjectCreateResponse:
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Case title is required.")
    org_id = resolve_org_id(current_user)
    if org_id is None:
        raise HTTPException(
            status_code=403,
            detail="Super-admin must operate within a specific organization to create a case.",
        )
    case = await service.create_project(
        payload,
        organization_id=org_id,
        created_by_user_id=current_user.id,
    )
    return ProjectCreateResponse(id=case.id, status=case.status)


@router.get("/{case_id}", response_model=ProjectDetail)
@limiter.limit(get_settings().rate_limit_read_detail)
async def get_case(
    case_id: str,
    request: Request,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUserRead = Depends(get_current_user),
) -> ProjectDetail:
    org_id = resolve_org_id(current_user)
    detail = await service.get_project_detail(case_id, organization_id=org_id, actor_role=current_user.role)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    return detail


@router.post("/{case_id}/duplicate", response_model=ProjectCreateResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_case(
    case_id: str,
    payload: ProjectDuplicateRequest,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectCreateResponse:
    org_id = resolve_org_id(current_user)
    try:
        duplicated = await service.duplicate_project(case_id, payload, organization_id=org_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not duplicated:
        raise HTTPException(status_code=404, detail="Case not found.")
    return ProjectCreateResponse(id=duplicated.id, status=duplicated.status)


@router.patch("/{case_id}", response_model=ProjectDetail)
async def patch_case(
    case_id: str,
    payload: ProjectPatch,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectDetail:
    org_id = resolve_org_id(current_user)
    updated = await service.update_project(case_id, payload.model_dump(exclude_unset=True), organization_id=org_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found.")
    return updated


@router.patch("/{case_id}/proposal-draft", response_model=ProjectDetail)
async def patch_case_proposal_draft(
    case_id: str,
    payload: ProjectProposalDraftPatch,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectDetail:
    org_id = resolve_org_id(current_user)
    updated = await service.update_proposal_draft(case_id, payload.model_dump(exclude_unset=True), organization_id=org_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found.")
    return updated


@router.post("/{case_id}/final-proposal", response_model=ProjectDetail)
async def create_case_final_proposal(
    case_id: str,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectDetail:
    org_id = resolve_org_id(current_user)
    try:
        updated = await service.create_final_proposal(case_id, organization_id=org_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found.")
    return updated


# ---------------------------------------------------------------------------
# State-machine action endpoints
# All transitions go through CaseActionService → apply_transition().
# Direct status writes via PATCH are rejected (status removed from ProjectPatch).
# ---------------------------------------------------------------------------

def _action_404(case_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail="Case not found.")


def _action_409(exc: CaseActionError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.post("/{case_id}/submit", response_model=ProjectDetail)
async def submit_case(
    case_id: str,
    body: CaseActionRequest = CaseActionRequest(),
    actions: CaseActionService = Depends(get_case_action_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectDetail:
    """draft → intake.  Confirm the case is ready for processing."""
    org_id = resolve_org_id(current_user)
    try:
        result = await actions.submit(case_id, organization_id=org_id, actor_user_id=current_user.id, actor_role=current_user.role, reason=body.reason)
    except CaseActionError as exc:
        raise _action_409(exc) from exc
    if not result:
        raise _action_404(case_id)
    return result


@router.post("/{case_id}/start-analysis", response_model=ProjectDetail)
async def start_analysis(
    case_id: str,
    body: CaseActionRequest = CaseActionRequest(),
    actions: CaseActionService = Depends(get_case_action_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectDetail:
    """intake → analyzing.  Photos confirmed, analysis queued."""
    org_id = resolve_org_id(current_user)
    try:
        result = await actions.start_analysis(case_id, organization_id=org_id, actor_user_id=current_user.id, actor_role=current_user.role, reason=body.reason)
    except CaseActionError as exc:
        raise _action_409(exc) from exc
    if not result:
        raise _action_404(case_id)
    return result


@router.post("/{case_id}/approve-proposal", response_model=ProjectDetail)
async def approve_proposal(
    case_id: str,
    body: CaseActionRequest = CaseActionRequest(),
    actions: CaseActionService = Depends(get_case_action_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectDetail:
    """proposal_ready → quote_ready.  Manager signs off on the AI proposal."""
    org_id = resolve_org_id(current_user)
    try:
        result = await actions.approve_proposal(case_id, organization_id=org_id, actor_user_id=current_user.id, actor_role=current_user.role, reason=body.reason)
    except CaseActionError as exc:
        raise _action_409(exc) from exc
    if not result:
        raise _action_404(case_id)
    return result


@router.post("/{case_id}/send", response_model=ProjectDetail)
async def send_case(
    case_id: str,
    body: CaseActionRequest = CaseActionRequest(),
    actions: CaseActionService = Depends(get_case_action_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectDetail:
    """quote_ready → sent.  Quote delivered to the client.

    Guard: a final proposal must exist.
    """
    org_id = resolve_org_id(current_user)
    try:
        result = await actions.send_quote(case_id, organization_id=org_id, actor_user_id=current_user.id, actor_role=current_user.role, reason=body.reason)
    except CaseActionError as exc:
        raise _action_409(exc) from exc
    if not result:
        raise _action_404(case_id)
    return result


@router.post("/{case_id}/archive", response_model=ProjectDetail)
async def archive_case(
    case_id: str,
    body: CaseActionRequest = CaseActionRequest(),
    actions: CaseActionService = Depends(get_case_action_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectDetail:
    """sent → archived.  Work completed / accepted."""
    org_id = resolve_org_id(current_user)
    try:
        result = await actions.complete(case_id, organization_id=org_id, actor_user_id=current_user.id, actor_role=current_user.role, reason=body.reason)
    except CaseActionError as exc:
        raise _action_409(exc) from exc
    if not result:
        raise _action_404(case_id)
    return result


@router.post("/{case_id}/return-to-draft", response_model=ProjectDetail)
async def return_case_to_draft(
    case_id: str,
    body: CaseActionRequest = CaseActionRequest(),
    actions: CaseActionService = Depends(get_case_action_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectDetail:
    """any valid → draft.  Unlock for edits or re-submission."""
    org_id = resolve_org_id(current_user)
    try:
        result = await actions.return_to_draft(case_id, organization_id=org_id, actor_user_id=current_user.id, actor_role=current_user.role, reason=body.reason)
    except CaseActionError as exc:
        raise _action_409(exc) from exc
    if not result:
        raise _action_404(case_id)
    return result


@router.post("/{case_id}/cancel", response_model=ProjectDetail)
async def cancel_case(
    case_id: str,
    body: CaseActionRequest = CaseActionRequest(),
    actions: CaseActionService = Depends(get_case_action_service),
    current_user: AuthUserRead = Depends(require_manager),
) -> ProjectDetail:
    """any valid → cancelled.  Explicitly abandon the case."""
    org_id = resolve_org_id(current_user)
    try:
        result = await actions.cancel(case_id, organization_id=org_id, actor_user_id=current_user.id, actor_role=current_user.role, reason=body.reason)
    except CaseActionError as exc:
        raise _action_409(exc) from exc
    if not result:
        raise _action_404(case_id)
    return result


# ---------------------------------------------------------------------------
# Timeline (read-only — now pulls real status_history in addition to events)
# ---------------------------------------------------------------------------

@router.get("/{case_id}/timeline", response_model=list[dict])
@limiter.limit(get_settings().rate_limit_read_detail)
async def get_case_timeline(
    case_id: str,
    request: Request,
    service: ProjectService = Depends(get_project_service),
    current_user: AuthUserRead = Depends(get_current_user),
) -> list[dict]:
    org_id = resolve_org_id(current_user)
    detail = await service.get_project_detail(case_id, organization_id=org_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    timeline = [
        {"type": "case_created", "label": "Pripad zalozen", "at": detail.createdAt},
    ]
    if detail.latestAnalysis:
        timeline.append({"type": "analysis_completed", "label": "Analyza dokoncena", "at": detail.latestAnalysis.get("createdAt")})
    if detail.quoteVariants:
        timeline.append({"type": "estimate_ready", "label": "Pripraveny odhad nabidky", "at": detail.quoteVariants[0].get("createdAt")})
    return timeline
