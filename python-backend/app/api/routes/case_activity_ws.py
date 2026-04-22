from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.api.deps import resolve_org_id
from app.db.session import AsyncSessionFactory
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.token_repository import TokenStateBackendUnavailableError
from app.schemas.auth import AuthUserRead
from app.schemas.case_activity import (
    CaseActivitySubscribeCommand,
    ImageStatusChangedEvent,
    JobCompletedEvent,
    JobStatusChangedEvent,
    validate_case_activity_command,
)
from app.services.auth_service import AuthService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["case-activity"])

_POLL_INTERVAL_SECONDS = 1.5
_TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "canceled", "dead_letter"})


@dataclass(frozen=True)
class CaseActivitySubscription:
    case_id: str
    job_id: str | None
    organization_id: str | None
    is_superadmin_context: bool


@dataclass(frozen=True)
class CaseActivitySnapshot:
    job_status: str | None = None
    image_statuses: dict[str, str] = field(default_factory=dict)


def _websocket_app_state(websocket: WebSocket):
    app = websocket.scope.get("app")
    return getattr(app, "state", None)


def _auth_store_for_websocket(websocket: WebSocket):
    state = _websocket_app_state(websocket)
    if state is None:
        return None
    auth_store = getattr(state, "auth_token_store", None)
    if auth_store is not None:
        return auth_store
    return getattr(state, "job_queue", None)


async def _authenticate_socket(websocket: WebSocket) -> tuple[AuthUserRead | None, str | None, int | None]:
    token = (websocket.query_params.get("token") or "").strip()
    if not token:
        return None, "Missing access token.", status.WS_1008_POLICY_VIOLATION

    async with AsyncSessionFactory() as session:
        auth_service = AuthService(session, redis=_auth_store_for_websocket(websocket))
        try:
            user = await auth_service.get_user_by_token(token)
        except TokenStateBackendUnavailableError as exc:
            logger.error(
                "case_activity_ws.auth_unavailable",
                operation=exc.operation,
                error=str(exc),
            )
            return None, "Authentication token validation unavailable.", status.WS_1011_INTERNAL_ERROR

    if user is None:
        return None, "Invalid or expired token.", status.WS_1008_POLICY_VIOLATION

    return user, None, None


async def _validate_subscription(
    command: CaseActivitySubscribeCommand,
    *,
    current_user: AuthUserRead,
) -> tuple[CaseActivitySubscription | None, str | None]:
    organization_id = resolve_org_id(current_user)

    async with AsyncSessionFactory() as session:
        project_repository = ProjectRepository(session)
        project = await project_repository.get_project_lean(
            command.caseId,
            organization_id=organization_id,
        )
        if project is None:
            return None, "Case not found."

        if command.jobId:
            analysis_repository = AnalysisRepository(session)
            if current_user.isSuperAdmin:
                job = await analysis_repository.get_analysis_job(command.jobId)
            else:
                job = await analysis_repository.get_analysis_job_in_org(
                    command.jobId,
                    organization_id,
                )
            if job is None or getattr(job, "project_id", None) != command.caseId:
                return None, "Analysis job not found for the subscribed case."

    return (
        CaseActivitySubscription(
            case_id=command.caseId,
            job_id=command.jobId,
            organization_id=organization_id,
            is_superadmin_context=current_user.isSuperAdmin,
        ),
        None,
    )


async def _load_snapshot(subscription: CaseActivitySubscription) -> CaseActivitySnapshot:
    async with AsyncSessionFactory() as session:
        photo_repository = PhotoRepository(session)
        analysis_repository = AnalysisRepository(session)

        photos = await photo_repository.list_photos_by_project_id(subscription.case_id)
        image_statuses = {
            photo.id: photo.processing_status
            for photo in photos
            if isinstance(photo.id, str) and isinstance(photo.processing_status, str)
        }

        job_status: str | None = None
        if subscription.job_id:
            if subscription.is_superadmin_context:
                job = await analysis_repository.get_analysis_job(subscription.job_id)
            else:
                job = await analysis_repository.get_analysis_job_in_org(
                    subscription.job_id,
                    subscription.organization_id,
                )
            if job is not None and getattr(job, "project_id", None) == subscription.case_id:
                status_value = getattr(job, "status", None)
                if isinstance(status_value, str) and status_value:
                    job_status = status_value

    return CaseActivitySnapshot(
        job_status=job_status,
        image_statuses=image_statuses,
    )


def _build_snapshot_events(
    subscription: CaseActivitySubscription,
    previous: CaseActivitySnapshot,
    current: CaseActivitySnapshot,
) -> list[dict]:
    timestamp = datetime.now(UTC)
    events: list[dict] = []

    if subscription.job_id and current.job_status and current.job_status != previous.job_status:
        if current.job_status in _TERMINAL_JOB_STATUSES:
            events.append(
                JobCompletedEvent(
                    type="job_completed",
                    caseId=subscription.case_id,
                    jobId=subscription.job_id,
                    status=current.job_status,
                    timestamp=timestamp,
                ).model_dump(mode="json")
            )
        else:
            events.append(
                JobStatusChangedEvent(
                    type="job_status_changed",
                    caseId=subscription.case_id,
                    jobId=subscription.job_id,
                    status=current.job_status,
                    timestamp=timestamp,
                ).model_dump(mode="json")
            )

    current_items = sorted(current.image_statuses.items())
    for image_id, image_status in current_items:
        if previous.image_statuses.get(image_id) == image_status:
            continue
        events.append(
            ImageStatusChangedEvent(
                type="image_status_changed",
                caseId=subscription.case_id,
                imageId=image_id,
                jobId=subscription.job_id,
                status=image_status,
                timestamp=timestamp,
            ).model_dump(mode="json")
        )

    return events


async def _receive_command_or_timeout(websocket: WebSocket):
    try:
        payload = await asyncio.wait_for(websocket.receive_json(), timeout=_POLL_INTERVAL_SECONDS)
    except asyncio.TimeoutError:
        return None
    except WebSocketDisconnect:
        raise
    except Exception as exc:
        raise ValueError("Invalid websocket payload.") from exc

    try:
        return validate_case_activity_command(payload)
    except ValidationError as exc:
        raise ValueError("Invalid case activity command.") from exc


@router.websocket("/ws/case-activity")
async def case_activity_websocket(websocket: WebSocket) -> None:
    current_user, auth_error, close_code = await _authenticate_socket(websocket)
    if current_user is None:
        await websocket.close(
            code=close_code or status.WS_1008_POLICY_VIOLATION,
            reason=auth_error or "Authentication failed.",
        )
        return

    await websocket.accept()
    logger.info(
        "case_activity_ws.connected",
        user_id=current_user.id,
        organization_id=current_user.organizationId,
        is_superadmin=current_user.isSuperAdmin,
    )

    subscription: CaseActivitySubscription | None = None
    previous_snapshot = CaseActivitySnapshot()

    try:
        while True:
            try:
                command = await _receive_command_or_timeout(websocket)
            except ValueError as exc:
                logger.warning(
                    "case_activity_ws.invalid_command",
                    user_id=current_user.id,
                    error=str(exc),
                )
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="Invalid case activity command.",
                )
                return

            if command is not None:
                if command.type == "unsubscribe":
                    subscription = None
                    previous_snapshot = CaseActivitySnapshot()
                    continue

                validated_subscription, error_message = await _validate_subscription(
                    command,
                    current_user=current_user,
                )
                if validated_subscription is None:
                    logger.warning(
                        "case_activity_ws.subscription_rejected",
                        user_id=current_user.id,
                        case_id=command.caseId,
                        job_id=command.jobId,
                        reason=error_message,
                    )
                    await websocket.close(
                        code=status.WS_1008_POLICY_VIOLATION,
                        reason=error_message or "Subscription rejected.",
                    )
                    return

                subscription = validated_subscription
                previous_snapshot = CaseActivitySnapshot()

            if subscription is None:
                continue

            current_snapshot = await _load_snapshot(subscription)
            events = _build_snapshot_events(subscription, previous_snapshot, current_snapshot)
            previous_snapshot = current_snapshot

            for event in events:
                await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info(
            "case_activity_ws.disconnected",
            user_id=current_user.id,
            case_id=subscription.case_id if subscription else None,
            job_id=subscription.job_id if subscription else None,
        )
    except Exception:
        logger.exception(
            "case_activity_ws.failed",
            user_id=current_user.id,
            case_id=subscription.case_id if subscription else None,
            job_id=subscription.job_id if subscription else None,
        )
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Realtime stream failed.")
        except Exception:
            return
