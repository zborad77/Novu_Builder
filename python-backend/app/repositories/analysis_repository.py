import json
import structlog
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.case_workflow.transitions import TransitionError, execute_transition
from app.models import AnalysisJob, AnalysisResult, Project

logger = structlog.get_logger(__name__)


ANALYSIS_JOB_STATUS_QUEUED = "queued"
ANALYSIS_JOB_STATUS_RUNNING = "running"
ANALYSIS_JOB_STATUS_COMPLETED = "completed"
ANALYSIS_JOB_STATUS_FAILED = "failed"
ANALYSIS_JOB_STATUS_CANCELED = "canceled"
ANALYSIS_JOB_STATUS_DEAD_LETTER = "dead_letter"
ANALYSIS_JOB_TYPE_MANUAL_TRIGGER = "manual_trigger"
ANALYSIS_JOB_TYPE_QUOTE_RECALCULATION = "quote_recalculation"

ANALYSIS_JOB_STATUSES = frozenset({
    ANALYSIS_JOB_STATUS_QUEUED,
    ANALYSIS_JOB_STATUS_RUNNING,
    ANALYSIS_JOB_STATUS_COMPLETED,
    ANALYSIS_JOB_STATUS_FAILED,
    ANALYSIS_JOB_STATUS_CANCELED,
    ANALYSIS_JOB_STATUS_DEAD_LETTER,
})
ANALYSIS_JOB_FINAL_STATUSES = frozenset({
    ANALYSIS_JOB_STATUS_COMPLETED,
    ANALYSIS_JOB_STATUS_FAILED,
    ANALYSIS_JOB_STATUS_CANCELED,
    ANALYSIS_JOB_STATUS_DEAD_LETTER,
})
_ALLOWED_ANALYSIS_JOB_TRANSITIONS = {
    ANALYSIS_JOB_STATUS_QUEUED: frozenset({
        ANALYSIS_JOB_STATUS_RUNNING,
        ANALYSIS_JOB_STATUS_FAILED,
        ANALYSIS_JOB_STATUS_CANCELED,
        ANALYSIS_JOB_STATUS_DEAD_LETTER,
    }),
    ANALYSIS_JOB_STATUS_RUNNING: frozenset({
        ANALYSIS_JOB_STATUS_COMPLETED,
        ANALYSIS_JOB_STATUS_FAILED,
        ANALYSIS_JOB_STATUS_CANCELED,
        ANALYSIS_JOB_STATUS_DEAD_LETTER,
    }),
    ANALYSIS_JOB_STATUS_COMPLETED: frozenset(),
    ANALYSIS_JOB_STATUS_FAILED: frozenset(),
    ANALYSIS_JOB_STATUS_CANCELED: frozenset(),
    ANALYSIS_JOB_STATUS_DEAD_LETTER: frozenset(),
}
_UNSET = object()


class AnalysisJobStatusError(ValueError):
    """Base error for invalid analysis job statuses or transitions."""


class InvalidAnalysisJobStatusError(AnalysisJobStatusError):
    """Raised when a status value is outside the supported domain."""


class InvalidAnalysisJobStatusTransition(AnalysisJobStatusError):
    """Raised when a job transition would violate the allowed lifecycle."""


class InvalidAnalysisResultPayloadError(ValueError):
    """Raised when an analysis payload cannot be safely persisted."""


class AnalysisJobLeaseOwnershipError(RuntimeError):
    """Raised when a worker no longer owns the DB lease for a job."""


class ActiveAnalysisJobConflict(RuntimeError):
    """Raised when DB-level dedup detects an already-active job."""

    def __init__(self, existing_job: AnalysisJob | None = None) -> None:
        super().__init__("An active analysis job already exists.")
        self.existing_job = existing_job


def normalize_analysis_job_status(status: str) -> str:
    if not isinstance(status, str):
        raise InvalidAnalysisJobStatusError("Analysis job status must be a string.")
    normalized = status.strip()
    if normalized not in ANALYSIS_JOB_STATUSES:
        raise InvalidAnalysisJobStatusError(
            f"Unsupported analysis job status '{status}'."
        )
    return normalized


def validate_analysis_job_transition(current_status: str, target_status: str) -> None:
    current = normalize_analysis_job_status(current_status)
    target = normalize_analysis_job_status(target_status)
    if current == target:
        return
    if target not in _ALLOWED_ANALYSIS_JOB_TRANSITIONS[current]:
        raise InvalidAnalysisJobStatusTransition(
            f"Cannot transition analysis job from '{current}' to '{target}'."
        )


def _resolve_completed_job_status(job_status: str | None) -> str:
    resolved = (
        ANALYSIS_JOB_STATUS_COMPLETED
        if job_status is None
        else normalize_analysis_job_status(job_status)
    )
    if resolved != ANALYSIS_JOB_STATUS_COMPLETED:
        raise InvalidAnalysisJobStatusError(
            "complete_job_with_result only accepts a completed analysis job status."
        )
    return resolved


def _resolve_terminal_record_status(job_status: str | None) -> str:
    resolved = (
        ANALYSIS_JOB_STATUS_COMPLETED
        if job_status is None
        else normalize_analysis_job_status(job_status)
    )
    if resolved not in ANALYSIS_JOB_FINAL_STATUSES:
        raise InvalidAnalysisJobStatusError(
            "create_analysis_record only accepts terminal analysis job statuses."
        )
    return resolved


def _require_analysis_mapping(analysis: object) -> Mapping[str, object]:
    if not isinstance(analysis, Mapping):
        raise InvalidAnalysisResultPayloadError(
            "Analysis payload must be a JSON object."
        )
    return analysis


def _optional_string(
    payload: Mapping[str, object],
    key: str,
    *,
    default: str | None = None,
) -> str | None:
    value = payload.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidAnalysisResultPayloadError(
            f"{key} must be a string when provided."
        )
    return value


def _coerce_float(
    payload: Mapping[str, object],
    key: str,
    *,
    default: float | None,
) -> float | None:
    value = payload.get(key, default)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidAnalysisResultPayloadError(
            f"{key} must be numeric when provided."
        ) from exc


def _coerce_int(
    payload: Mapping[str, object],
    key: str,
    *,
    default: int | None,
) -> int | None:
    value = payload.get(key, default)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidAnalysisResultPayloadError(
            f"{key} must be an integer when provided."
        ) from exc


def _optional_json(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise InvalidAnalysisResultPayloadError(
            f"{field_name} must be JSON-serializable."
        ) from exc


def _prepare_analysis_result_values(analysis: object) -> dict[str, object]:
    payload = _require_analysis_mapping(analysis)
    return {
        "resolved_work_type_code": _optional_string(payload, "resolvedWorkTypeCode"),
        "analysis_profile_code": _optional_string(payload, "analysisProfileCode"),
        "analysis_profile_version": _coerce_int(payload, "analysisProfileVersion", default=None),
        "reference_photo_id": _optional_string(payload, "referencePhotoId"),
        "object_type": _optional_string(payload, "objectType", default="facade") or "facade",
        "surface_condition": _optional_string(payload, "surfaceCondition", default="requires_attention")
        or "requires_attention",
        "recommended_scope": _optional_string(payload, "recommendedScope", default="local_repair")
        or "local_repair",
        "estimated_quantity": _coerce_float(payload, "estimatedQuantity", default=None),
        "estimated_unit": _optional_string(payload, "estimatedUnit", default=None),
        "estimated_area_sqm": _coerce_float(payload, "estimatedAreaSqm", default=None),
        "area_confidence": _coerce_float(payload, "areaConfidence", default=None),
        "selected_repair_polygon_json": _optional_json(
            payload.get("selectedRepairPolygon"),
            "selectedRepairPolygon",
        ),
        "manual_area_sqm": _coerce_float(payload, "manualAreaSqm", default=None),
        "final_area_source": _optional_string(payload, "finalAreaSource", default="ai") or "ai",
        "mask_polygon_json": _optional_json(payload.get("maskPolygon", []), "maskPolygon") or json.dumps([]),
        "materials_suggestion_json": _optional_json(payload.get("materials", []), "materials") or json.dumps([]),
        "workflow_suggestion_json": _optional_json(payload.get("workflowSteps", []), "workflowSteps") or json.dumps([]),
        "estimated_duration_days": _coerce_float(payload, "estimatedTotalDays", default=None),
        "labor_hours_total": _coerce_float(payload, "laborHoursTotal", default=None),
        "model_name": _optional_string(payload, "modelName", default="mock-vision") or "mock-vision",
        "model_version": _optional_string(payload, "modelVersion", default="0.1") or "0.1",
    }


def _build_output_summary(analysis: object, *, duration_seconds: float | None) -> str:
    payload = _require_analysis_mapping(analysis)
    summary = {
        "provider": payload.get("providerKey"),
        "work_type_code": payload.get("resolvedWorkTypeCode"),
        "analysis_profile_code": payload.get("analysisProfileCode"),
        "analysis_profile_version": payload.get("analysisProfileVersion"),
        "model_name": payload.get("modelName"),
        "object_type": payload.get("objectType"),
        "estimated_quantity": payload.get("estimatedQuantity"),
        "estimated_unit": payload.get("estimatedUnit"),
        "estimated_area_sqm": payload.get("estimatedAreaSqm"),
        "area_confidence": payload.get("areaConfidence"),
        "validation_warnings": payload.get("validationWarnings"),
        "duration_seconds": duration_seconds,
    }
    return json.dumps(summary, ensure_ascii=False)


def _normalize_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AnalysisRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _set_job_status(
        self,
        job: AnalysisJob,
        status: str,
        *,
        timestamp: datetime | None = None,
        error_message=_UNSET,
        error_traceback=_UNSET,
    ) -> None:
        now = timestamp or datetime.now(UTC)
        current_status = normalize_analysis_job_status(job.status)
        target_status = normalize_analysis_job_status(status)
        if current_status == target_status:
            return
        validate_analysis_job_transition(current_status, target_status)

        job.status = target_status
        if target_status == ANALYSIS_JOB_STATUS_RUNNING:
            job.started_at = job.started_at or now
            job.finished_at = None
        elif target_status in ANALYSIS_JOB_FINAL_STATUSES:
            job.finished_at = now

        if error_message is not _UNSET:
            job.error_message = error_message
        elif target_status == ANALYSIS_JOB_STATUS_COMPLETED:
            job.error_message = None

        if error_traceback is not _UNSET:
            job.error_traceback = error_traceback
        elif target_status == ANALYSIS_JOB_STATUS_COMPLETED:
            job.error_traceback = None

        if target_status in ANALYSIS_JOB_FINAL_STATUSES:
            job.lease_token = None
            job.worker_id = None
            job.leased_at = None
            job.heartbeat_at = None

    async def get_project_in_org(self, project_id: str, organization_id: str) -> Project | None:
        result = await self.session.execute(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_analysis_result(self, project_id: str) -> AnalysisResult | None:
        result = await self.session.execute(
            select(AnalysisResult)
            .where(AnalysisResult.project_id == project_id)
            .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_analysis_result(self, analysis_result_id: str) -> AnalysisResult | None:
        return await self.session.get(AnalysisResult, analysis_result_id)

    async def get_analysis_result_in_org(self, result_id: str, organization_id: str) -> AnalysisResult | None:
        """Fetch an AnalysisResult only if its parent project belongs to organization_id."""
        result = await self.session.execute(
            select(AnalysisResult)
            .join(Project, Project.id == AnalysisResult.project_id)
            .where(AnalysisResult.id == result_id, Project.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def get_analysis_job(self, job_id: str) -> AnalysisJob | None:
        return await self.session.get(AnalysisJob, job_id)

    async def get_analysis_result_by_job_id(self, job_id: str) -> AnalysisResult | None:
        result = await self.session.execute(
            select(AnalysisResult)
            .where(AnalysisResult.analysis_job_id == job_id)
            .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_analysis_result_by_job_id_in_org(
        self,
        job_id: str,
        organization_id: str,
    ) -> AnalysisResult | None:
        result = await self.session.execute(
            select(AnalysisResult)
            .join(Project, Project.id == AnalysisResult.project_id)
            .where(
                AnalysisResult.analysis_job_id == job_id,
                Project.organization_id == organization_id,
            )
            .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_analysis_job_in_org(self, job_id: str, organization_id: str) -> AnalysisJob | None:
        """Fetch an AnalysisJob only if its parent project belongs to organization_id."""
        result = await self.session.execute(
            select(AnalysisJob)
            .join(Project, Project.id == AnalysisJob.project_id)
            .where(AnalysisJob.id == job_id, Project.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def get_active_job_for_project(self, project_id: str) -> AnalysisJob | None:
        """Return the most recent queued or running job for this project, or None."""
        return await self.get_active_job_for_project_by_type(project_id)

    async def get_active_job_for_project_by_type(
        self,
        project_id: str,
        *,
        job_type: str | None = None,
    ) -> AnalysisJob | None:
        """Return the most recent queued or running job for this project and optional job type."""
        query = (
            select(AnalysisJob)
            .where(
                AnalysisJob.project_id == project_id,
                AnalysisJob.status.in_((
                    ANALYSIS_JOB_STATUS_QUEUED,
                    ANALYSIS_JOB_STATUS_RUNNING,
                )),
            )
            .order_by(AnalysisJob.created_at.desc())
            .limit(1)
        )
        if job_type is not None:
            query = query.where(AnalysisJob.job_type == job_type)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def count_active_jobs_for_organization(
        self,
        organization_id: str,
        *,
        job_type: str | None = None,
    ) -> int:
        query = (
            select(func.count())
            .select_from(AnalysisJob)
            .join(Project, Project.id == AnalysisJob.project_id)
            .where(
                Project.organization_id == organization_id,
                AnalysisJob.status.in_(
                    (
                        ANALYSIS_JOB_STATUS_QUEUED,
                        ANALYSIS_JOB_STATUS_RUNNING,
                    )
                ),
            )
        )
        if job_type is not None:
            query = query.where(AnalysisJob.job_type == job_type)

        result = await self.session.execute(query)
        return int(result.scalar_one() or 0)

    async def count_retry_inflight_jobs(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(AnalysisJob)
            .where(
                AnalysisJob.status.in_(
                    (
                        ANALYSIS_JOB_STATUS_QUEUED,
                        ANALYSIS_JOB_STATUS_RUNNING,
                    )
                ),
                (
                    (func.coalesce(AnalysisJob.retry_count, 0) > 0)
                    | (func.coalesce(AnalysisJob.attempt_count, 0) > 1)
                ),
            )
        )
        return int(result.scalar_one() or 0)

    async def list_analysis_jobs_by_project_id(self, project_id: str) -> list[AnalysisJob]:
        result = await self.session.execute(
            select(AnalysisJob)
            .where(AnalysisJob.project_id == project_id)
            .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        )
        return list(result.scalars().all())

    async def list_active_jobs(self) -> list[AnalysisJob]:
        result = await self.session.execute(
            select(AnalysisJob)
            .where(
                AnalysisJob.status.in_(
                    (
                        ANALYSIS_JOB_STATUS_QUEUED,
                        ANALYSIS_JOB_STATUS_RUNNING,
                    )
                )
            )
            .order_by(AnalysisJob.created_at.asc(), AnalysisJob.id.asc())
        )
        return list(result.scalars().all())

    async def list_active_jobs_with_organization_id(self) -> list[tuple[AnalysisJob, str]]:
        result = await self.session.execute(
            select(AnalysisJob, Project.organization_id)
            .join(Project, Project.id == AnalysisJob.project_id)
            .where(
                AnalysisJob.status.in_(
                    (
                        ANALYSIS_JOB_STATUS_QUEUED,
                        ANALYSIS_JOB_STATUS_RUNNING,
                    )
                )
            )
            .order_by(AnalysisJob.created_at.asc(), AnalysisJob.id.asc())
        )
        return [(job, organization_id) for job, organization_id in result.all()]

    async def get_project_organization_id(self, project_id: str) -> str | None:
        result = await self.session.execute(
            select(Project.organization_id).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def create_queued_job(
        self,
        project: Project,
        *,
        user_id: str | None = None,
        parent_job_id: str | None = None,
        retry_count: int = 0,
        job_type: str = ANALYSIS_JOB_TYPE_MANUAL_TRIGGER,
        input_payload: str | None = None,
        requested_work_type_code: str | None = None,
        analysis_profile_id: str | None = None,
        resolved_analysis_profile_code: str | None = None,
        resolved_analysis_profile_version: int | None = None,
    ) -> AnalysisJob:
        resolved_user_id = user_id or project.created_by_user_id
        if resolved_user_id is None:
            raise ValueError(
                f"Cannot create analysis job for project {project.id}: "
                "requestor user_id is required but was not provided."
            )
        timestamp = datetime.now(UTC)
        job = AnalysisJob(
            id=f"job_{uuid4().hex[:8]}",
            project_id=project.id,
            status=ANALYSIS_JOB_STATUS_QUEUED,
            job_type=job_type,
            requested_work_type_code=requested_work_type_code,
            analysis_profile_id=analysis_profile_id,
            resolved_analysis_profile_code=resolved_analysis_profile_code,
            resolved_analysis_profile_version=resolved_analysis_profile_version,
            requested_by_user_id=resolved_user_id,
            parent_job_id=parent_job_id,
            retry_count=retry_count,
            attempt_count=0,
            lease_token=None,
            worker_id=None,
            leased_at=None,
            heartbeat_at=None,
            started_at=None,
            finished_at=None,
            error_message=None,
            input_payload=input_payload,
            created_at=timestamp,
        )
        self.session.add(job)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            existing = await self.get_active_job_for_project_by_type(
                project.id,
                job_type=job_type,
            )
            raise ActiveAnalysisJobConflict(existing) from exc
        await self.session.refresh(job)
        return job

    async def complete_job_without_result(
        self,
        job: AnalysisJob,
        *,
        output_summary: dict[str, object] | None = None,
    ) -> AnalysisJob:
        current_status = normalize_analysis_job_status(job.status)
        if current_status == ANALYSIS_JOB_STATUS_COMPLETED:
            await self.session.refresh(job)
            return job

        timestamp = datetime.now(UTC)
        self._set_job_status(
            job,
            ANALYSIS_JOB_STATUS_COMPLETED,
            timestamp=timestamp,
            error_message=None,
            error_traceback=None,
        )
        job.output_summary = (
            json.dumps(output_summary, ensure_ascii=False)
            if output_summary is not None
            else None
        )
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def complete_job_with_result(self, job: AnalysisJob, project: Project, analysis: dict) -> tuple[AnalysisJob, AnalysisResult]:
        current_status = normalize_analysis_job_status(job.status)
        if current_status == ANALYSIS_JOB_STATUS_COMPLETED:
            existing_result = await self.get_analysis_result_by_job_id(job.id)
            if existing_result is not None:
                await self.session.refresh(job)
                await self.session.refresh(existing_result)
                return job, existing_result
            raise InvalidAnalysisJobStatusTransition(
                f"Analysis job '{job.id}' is already completed but has no stored result."
            )

        timestamp = datetime.now(UTC)
        payload = _require_analysis_mapping(analysis)
        completed_status = _resolve_completed_job_status(_optional_string(payload, "jobStatus"))
        result_values = _prepare_analysis_result_values(payload)
        error_message = _optional_string(payload, "errorMessage")
        started_at = _normalize_utc_datetime(job.started_at)
        duration_seconds = (
            round((timestamp - started_at).total_seconds(), 1)
            if started_at is not None
            else None
        )

        existing_result = await self.get_analysis_result_by_job_id(job.id)
        if existing_result is not None:
            if current_status != ANALYSIS_JOB_STATUS_COMPLETED:
                raise InvalidAnalysisJobStatusTransition(
                    f"Analysis job '{job.id}' already has a persisted result."
                )
            await self.session.refresh(job)
            await self.session.refresh(existing_result)
            return job, existing_result

        self._set_job_status(
            job,
            completed_status,
            timestamp=timestamp,
            error_message=error_message,
            error_traceback=None,
        )
        job.output_summary = _build_output_summary(analysis, duration_seconds=duration_seconds)

        result = AnalysisResult(
            id=f"ana_{uuid4().hex[:8]}",
            project_id=project.id,
            analysis_job_id=job.id,
            resolved_work_type_code=result_values["resolved_work_type_code"] or job.requested_work_type_code,
            analysis_profile_id=job.analysis_profile_id,
            resolved_analysis_profile_code=result_values["analysis_profile_code"] or job.resolved_analysis_profile_code,
            resolved_analysis_profile_version=(
                int(result_values["analysis_profile_version"])
                if result_values["analysis_profile_version"] is not None
                else job.resolved_analysis_profile_version
            ),
            reference_photo_id=result_values["reference_photo_id"],
            object_type=result_values["object_type"],
            surface_condition=result_values["surface_condition"],
            recommended_scope=result_values["recommended_scope"],
            estimated_quantity=result_values["estimated_quantity"],
            estimated_unit=result_values["estimated_unit"],
            estimated_area_sqm=result_values["estimated_area_sqm"],
            area_confidence=result_values["area_confidence"],
            selected_repair_polygon_json=result_values["selected_repair_polygon_json"],
            manual_area_sqm=result_values["manual_area_sqm"],
            final_area_source=result_values["final_area_source"],
            mask_polygon_json=result_values["mask_polygon_json"],
            materials_suggestion_json=result_values["materials_suggestion_json"],
            workflow_suggestion_json=result_values["workflow_suggestion_json"],
            estimated_duration_days=result_values["estimated_duration_days"],
            labor_hours_total=result_values["labor_hours_total"],
            model_name=result_values["model_name"],
            model_version=result_values["model_version"],
            created_at=timestamp,
        )
        self.session.add(result)

        # Transition project through the state machine.
        # Target: quote_ready (simple path) — proposal_ready used when work_type.proposal_step=True.
        # Guard: if the case was returned to draft while the worker ran, log and skip;
        # the analysis result is still persisted so no work is lost.
        try:
            await execute_transition(
                project,
                "quote_ready",
                actor_user_id=None,   # system / worker — no human actor
                reason="Analysis completed by worker",
                session=self.session,
            )
        except TransitionError:
            logger.warning(
                "analysis.worker.status_transition_skipped",
                project_id=project.id,
                current_status=project.status,
                reason="Case left 'analyzing' state before worker callback — status unchanged",
            )
        project.property_type = result_values["object_type"] or project.property_type
        project.repair_scope = result_values["recommended_scope"] or project.repair_scope
        project.updated_at = timestamp

        await self.session.commit()
        await self.session.refresh(job)
        await self.session.refresh(result)
        return job, result

    async def create_analysis_record(self, project: Project, analysis: dict) -> tuple[AnalysisJob, AnalysisResult]:
        if project.created_by_user_id is None:
            raise ValueError(
                f"Cannot create analysis record for project {project.id}: "
                "created_by_user_id is required but was not provided."
            )
        timestamp = datetime.now(UTC)
        payload = _require_analysis_mapping(analysis)
        terminal_status = _resolve_terminal_record_status(_optional_string(payload, "jobStatus"))
        result_values = _prepare_analysis_result_values(payload)
        error_message = _optional_string(payload, "errorMessage")
        job_type = _optional_string(payload, "jobType", default="manual_trigger") or "manual_trigger"
        job = AnalysisJob(
            id=f"job_{uuid4().hex[:8]}",
            project_id=project.id,
            status=terminal_status,
            job_type=job_type,
            requested_work_type_code=result_values["resolved_work_type_code"],
            analysis_profile_id=None,
            resolved_analysis_profile_code=result_values["analysis_profile_code"],
            resolved_analysis_profile_version=(
                int(result_values["analysis_profile_version"])
                if result_values["analysis_profile_version"] is not None
                else None
            ),
            requested_by_user_id=project.created_by_user_id,
            retry_count=0,
            attempt_count=1,
            lease_token=None,
            worker_id=None,
            leased_at=None,
            heartbeat_at=None,
            started_at=timestamp,
            finished_at=timestamp,
            error_message=error_message,
            created_at=timestamp,
        )
        self.session.add(job)
        await self.session.flush()

        result = AnalysisResult(
            id=f"ana_{uuid4().hex[:8]}",
            project_id=project.id,
            analysis_job_id=job.id,
            resolved_work_type_code=result_values["resolved_work_type_code"],
            analysis_profile_id=job.analysis_profile_id,
            resolved_analysis_profile_code=result_values["analysis_profile_code"],
            resolved_analysis_profile_version=(
                int(result_values["analysis_profile_version"])
                if result_values["analysis_profile_version"] is not None
                else None
            ),
            reference_photo_id=result_values["reference_photo_id"],
            object_type=result_values["object_type"],
            surface_condition=result_values["surface_condition"],
            recommended_scope=result_values["recommended_scope"],
            estimated_quantity=result_values["estimated_quantity"],
            estimated_unit=result_values["estimated_unit"],
            estimated_area_sqm=result_values["estimated_area_sqm"],
            area_confidence=result_values["area_confidence"],
            selected_repair_polygon_json=result_values["selected_repair_polygon_json"],
            manual_area_sqm=result_values["manual_area_sqm"],
            final_area_source=result_values["final_area_source"],
            mask_polygon_json=result_values["mask_polygon_json"],
            materials_suggestion_json=result_values["materials_suggestion_json"],
            workflow_suggestion_json=result_values["workflow_suggestion_json"],
            estimated_duration_days=result_values["estimated_duration_days"],
            labor_hours_total=result_values["labor_hours_total"],
            model_name=result_values["model_name"],
            model_version=result_values["model_version"],
            created_at=timestamp,
        )
        self.session.add(result)

        # Transition project through the state machine.
        # Target: quote_ready (simple path) — proposal_ready used when work_type.proposal_step=True.
        # Guard: if the case was returned to draft while the worker ran, log and skip;
        # the analysis result is still persisted so no work is lost.
        try:
            await execute_transition(
                project,
                "quote_ready",
                actor_user_id=None,   # system / worker — no human actor
                reason="Analysis completed by worker",
                session=self.session,
            )
        except TransitionError:
            logger.warning(
                "analysis.worker.status_transition_skipped",
                project_id=project.id,
                current_status=project.status,
                reason="Case left 'analyzing' state before worker callback — status unchanged",
            )
        project.property_type = result_values["object_type"] or project.property_type
        project.repair_scope = result_values["recommended_scope"] or project.repair_scope
        project.updated_at = timestamp

        await self.session.commit()
        await self.session.refresh(job)
        await self.session.refresh(result)
        return job, result

    async def update_latest_analysis_manual_selection(self, project_id: str, changes: dict) -> AnalysisResult | None:
        latest = await self.get_latest_analysis_result(project_id)
        if latest is None:
            return None
        return await self.update_analysis_manual_selection(latest, changes)

    async def update_analysis_manual_selection(self, analysis_result: AnalysisResult, changes: dict) -> AnalysisResult:
        latest = analysis_result

        if "referencePhotoId" in changes:
            latest.reference_photo_id = changes["referencePhotoId"]

        if "selectedRepairPolygon" in changes:
            polygon = changes["selectedRepairPolygon"]
            latest.selected_repair_polygon_json = json.dumps(polygon) if polygon else None

        if "manualAreaSqm" in changes:
            latest.manual_area_sqm = changes["manualAreaSqm"]

        if "finalAreaSource" in changes:
            latest.final_area_source = changes["finalAreaSource"]

        if latest.manual_area_sqm is None:
            latest.final_area_source = "ai"
        elif not latest.final_area_source:
            latest.final_area_source = "manual"

        await self.session.commit()
        await self.session.refresh(latest)
        return latest

    async def update_analysis_job_status(self, job: AnalysisJob, status: str) -> AnalysisJob:
        self._set_job_status(job, status)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def mark_job_running(
        self,
        job: AnalysisJob,
        *,
        lease_token: str | None = None,
        worker_id: str | None = None,
        leased_at: datetime | None = None,
        heartbeat_at: datetime | None = None,
    ) -> AnalysisJob:
        timestamp = datetime.now(UTC)
        lease_timestamp = leased_at or timestamp
        heartbeat_timestamp = heartbeat_at or lease_timestamp
        result = await self.session.execute(
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job.id,
                AnalysisJob.status == ANALYSIS_JOB_STATUS_QUEUED,
            )
            .values(
                status=ANALYSIS_JOB_STATUS_RUNNING,
                started_at=func.coalesce(AnalysisJob.started_at, timestamp),
                finished_at=None,
                attempt_count=func.coalesce(AnalysisJob.attempt_count, 0) + 1,
                lease_token=lease_token,
                worker_id=worker_id,
                leased_at=lease_timestamp,
                heartbeat_at=heartbeat_timestamp,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            await self.session.refresh(job)
            raise InvalidAnalysisJobStatusTransition(
                f"Cannot transition analysis job from '{job.status}' to '{ANALYSIS_JOB_STATUS_RUNNING}'."
            )
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def assert_job_lease_owned(
        self,
        job: AnalysisJob,
        *,
        lease_token: str,
        worker_id: str,
    ) -> AnalysisJob:
        await self.session.refresh(job)
        if (
            normalize_analysis_job_status(job.status) != ANALYSIS_JOB_STATUS_RUNNING
            or job.lease_token != lease_token
            or job.worker_id != worker_id
        ):
            raise AnalysisJobLeaseOwnershipError(
                f"Analysis job '{job.id}' is no longer owned by worker {worker_id!r} "
                f"with lease {lease_token!r}."
            )
        return job

    async def heartbeat_job_lease(
        self,
        job_id: str,
        *,
        lease_token: str,
        worker_id: str,
        leased_at: datetime,
        heartbeat_at: datetime,
    ) -> bool:
        result = await self.session.execute(
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job_id,
                AnalysisJob.status == ANALYSIS_JOB_STATUS_RUNNING,
                AnalysisJob.lease_token == lease_token,
                AnalysisJob.worker_id == worker_id,
            )
            .values(
                leased_at=leased_at,
                heartbeat_at=heartbeat_at,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            await self.session.rollback()
            return False
        await self.session.commit()
        return True

    async def reset_job_to_queued(self, job: AnalysisJob) -> AnalysisJob:
        current_status = normalize_analysis_job_status(job.status)
        if current_status == ANALYSIS_JOB_STATUS_QUEUED:
            await self.session.refresh(job)
            return job
        if current_status != ANALYSIS_JOB_STATUS_RUNNING:
            raise InvalidAnalysisJobStatusTransition(
                f"Cannot transition analysis job from '{job.status}' to '{ANALYSIS_JOB_STATUS_QUEUED}'."
            )

        result = await self.session.execute(
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job.id,
                AnalysisJob.status == ANALYSIS_JOB_STATUS_RUNNING,
            )
            .values(
                status=ANALYSIS_JOB_STATUS_QUEUED,
                lease_token=None,
                worker_id=None,
                leased_at=None,
                heartbeat_at=None,
                started_at=None,
                finished_at=None,
                error_message=None,
                error_traceback=None,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            await self.session.refresh(job)
            raise InvalidAnalysisJobStatusTransition(
                f"Cannot transition analysis job from '{job.status}' to '{ANALYSIS_JOB_STATUS_QUEUED}'."
            )
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def schedule_job_retry(
        self,
        job: AnalysisJob,
        *,
        message: str,
        error_traceback: str | None = None,
    ) -> AnalysisJob:
        result = await self.session.execute(
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job.id,
                AnalysisJob.status == ANALYSIS_JOB_STATUS_RUNNING,
            )
            .values(
                status=ANALYSIS_JOB_STATUS_QUEUED,
                started_at=None,
                finished_at=None,
                error_message=message,
                error_traceback=error_traceback,
                output_summary=None,
                lease_token=None,
                worker_id=None,
                leased_at=None,
                heartbeat_at=None,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            await self.session.refresh(job)
            raise InvalidAnalysisJobStatusTransition(
                f"Cannot transition analysis job from '{job.status}' to '{ANALYSIS_JOB_STATUS_QUEUED}'."
            )
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def mark_job_dead_letter(
        self,
        job: AnalysisJob,
        *,
        message: str,
        error_traceback: str | None = None,
    ) -> AnalysisJob:
        self._set_job_status(
            job,
            ANALYSIS_JOB_STATUS_DEAD_LETTER,
            error_message=message,
            error_traceback=error_traceback,
        )
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def requeue_dead_letter_job(self, job: AnalysisJob) -> AnalysisJob:
        current_status = normalize_analysis_job_status(job.status)
        if current_status != ANALYSIS_JOB_STATUS_DEAD_LETTER:
            raise InvalidAnalysisJobStatusTransition(
                f"Cannot transition analysis job from '{job.status}' to '{ANALYSIS_JOB_STATUS_QUEUED}'."
            )

        result = await self.session.execute(
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job.id,
                AnalysisJob.status == ANALYSIS_JOB_STATUS_DEAD_LETTER,
            )
            .values(
                status=ANALYSIS_JOB_STATUS_QUEUED,
                attempt_count=0,
                started_at=None,
                finished_at=None,
                error_message=None,
                error_traceback=None,
                output_summary=None,
                lease_token=None,
                worker_id=None,
                leased_at=None,
                heartbeat_at=None,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            await self.session.refresh(job)
            raise InvalidAnalysisJobStatusTransition(
                f"Cannot transition analysis job from '{job.status}' to '{ANALYSIS_JOB_STATUS_QUEUED}'."
            )
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def fail_job(
        self,
        job: AnalysisJob,
        *,
        message: str,
        error_traceback: str | None = None,
    ) -> AnalysisJob:
        self._set_job_status(
            job,
            ANALYSIS_JOB_STATUS_FAILED,
            error_message=message,
            error_traceback=error_traceback,
        )
        await self.session.commit()
        await self.session.refresh(job)
        return job
