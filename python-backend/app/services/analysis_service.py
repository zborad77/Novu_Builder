import asyncio
import json
import traceback

import structlog
from fastapi import HTTPException

from app.ai import describe_analysis_provider, run_project_analysis
from app.db.session import (
    AsyncSessionFactory,        # HTTP-originated ops (retry_job, etc.)
    WorkerAsyncSessionFactory,  # background runner only (execute_job, fail_job_before_processing)
)
from app.models import AnalysisJob, AnalysisResult, Project
from app.repositories.analysis_repository import (
    ANALYSIS_JOB_STATUS_CANCELED,
    ANALYSIS_JOB_STATUS_COMPLETED,
    ANALYSIS_JOB_STATUS_FAILED,
    ANALYSIS_JOB_FINAL_STATUSES,
    ANALYSIS_JOB_STATUS_QUEUED,
    AnalysisRepository,
    InvalidAnalysisResultPayloadError,
    InvalidAnalysisJobStatusTransition,
)
from app.repositories.photo_repository import PhotoRepository
from app.schemas.analysis import AnalysisResultRead, parse_json_field

logger = structlog.get_logger(__name__)

_JOB_TIMEOUT_SECONDS = 180  # 3 minutes — generous upper bound for vision API calls
_MAX_JOB_RETRY_COUNT = 10  # Hard ceiling to prevent runaway cost from AI provider calls
_REPEATED_FAILURE_THRESHOLD = 3  # Emit dead-letter sentinel after this many retries


def to_read_model(result: AnalysisResult) -> AnalysisResultRead:
    return AnalysisResultRead(
        id=result.id,
        projectId=result.project_id,
        analysisJobId=result.analysis_job_id,
        referencePhotoId=result.reference_photo_id,
        objectType=result.object_type,
        surfaceCondition=result.surface_condition,
        recommendedScope=result.recommended_scope,
        estimatedAreaSqm=result.estimated_area_sqm,
        areaConfidence=result.area_confidence,
        selectedRepairPolygon=parse_json_field(result.selected_repair_polygon_json),
        manualAreaSqm=result.manual_area_sqm,
        finalAreaSource=result.final_area_source,
        maskPolygon=parse_json_field(result.mask_polygon_json),
        materials=parse_json_field(result.materials_suggestion_json),
        workflowSteps=parse_json_field(result.workflow_suggestion_json),
        estimatedDurationDays=result.estimated_duration_days,
        laborHoursTotal=result.labor_hours_total,
        modelName=result.model_name,
        modelVersion=result.model_version,
        createdAt=result.created_at,
    )


def to_job_read(job: AnalysisJob) -> dict:
    return {
        "id": job.id,
        "projectId": job.project_id,
        "status": job.status,
        "jobType": job.job_type,
        "requestedByUserId": job.requested_by_user_id,
        "parentJobId": job.parent_job_id,
        "retryCount": job.retry_count,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
        "durationSeconds": (
            round((job.finished_at - job.started_at).total_seconds(), 1)
            if job.started_at and job.finished_at
            else None
        ),
        "errorMessage": job.error_message,
        "errorTraceback": job.error_traceback,
        "inputPayload": _safe_json_load(job.input_payload),
        "outputSummary": _safe_json_load(job.output_summary),
        "createdAt": job.created_at,
    }


def _safe_json_load(value: str | None) -> dict | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


async def _fail_job_and_raise(
    job: AnalysisJob,
    repo: AnalysisRepository,
    *,
    message: str,
    status_code: int,
    detail: str,
) -> None:
    """Mark job as failed, commit, then raise HTTPException. Never returns."""
    job.status = ANALYSIS_JOB_STATUS_FAILED
    job.error_message = message
    await repo.fail_job(job, message=message)
    raise HTTPException(status_code=status_code, detail=detail)


class AnalysisService:
    def __init__(
        self,
        *,
        repository: AnalysisRepository,
        photo_repository: PhotoRepository,
        provider_key: str,
    ):
        self.repository = repository
        self.photo_repository = photo_repository
        self.provider_key = provider_key

    async def get_latest_result(self, project_id: str) -> AnalysisResultRead | None:
        result = await self.repository.get_latest_analysis_result(project_id)
        return to_read_model(result) if result else None

    async def get_analysis_result_by_id(
        self, analysis_result_id: str, *, organization_id: str | None = None
    ) -> AnalysisResultRead | None:
        if organization_id is not None:
            result = await self.repository.get_analysis_result_in_org(analysis_result_id, organization_id)
        else:
            result = await self.repository.get_analysis_result(analysis_result_id)
        return to_read_model(result) if result else None

    async def list_jobs(self, project_id: str) -> list[dict]:
        jobs = await self.repository.list_analysis_jobs_by_project_id(project_id)
        return [to_job_read(job) for job in jobs]

    async def get_job(self, job_id: str, *, organization_id: str | None = None) -> dict | None:
        if organization_id is not None:
            job = await self.repository.get_analysis_job_in_org(job_id, organization_id)
        else:
            job = await self.repository.get_analysis_job(job_id)
        return to_job_read(job) if job else None

    async def create_job(self, project: Project, *, user_id: str | None = None,
                         parent_job_id: str | None = None, retry_count: int = 0) -> AnalysisJob:
        """Creates a queued job record, or returns an existing active job (idempotent)."""
        existing = await self.repository.get_active_job_for_project(project.id)
        if existing:
            logger.info(
                "worker.job_already_active",
                project_id=project.id,
                existing_job_id=existing.id,
                status=existing.status,
            )
            return existing
        return await self.repository.create_queued_job(
            project, user_id=user_id,
            parent_job_id=parent_job_id,
            retry_count=retry_count,
        )

    async def execute_job(
        self,
        job_id: str,
        project_id: str,
        organization_id: str | None = None,
        *,
        is_superadmin_context: bool = False,
    ) -> None:
        """Runs the analysis in the background using the worker DB pool.

        Session lifecycle (eliminates pool starvation under concurrent load):
          Phase 1  fetch job, validate, mark running, build input  → short session, CLOSED
          Phase 2  AI analysis (run_project_analysis)              → NO DB connection held
          Phase 3  persist result or failure                       → short session, CLOSED

        organization_id=None is the superadmin cross-tenant path. Callers MUST
        set is_superadmin_context=True when intentionally omitting organization_id;
        otherwise a 403 is raised to prevent accidental tenant-isolation bypass.
        """
        log = logger.bind(job_id=job_id, project_id=project_id)

        # Security check before opening any session.
        if organization_id is None and not is_superadmin_context:
            log.warning(
                "SECURITY_EVENT: execute_job_missing_org_id",
                job_id=job_id,
                project_id=project_id,
            )
            await self.fail_job_before_processing(
                job_id,
                message="Invalid worker payload: organization_id is required for non-superadmin context.",
            )
            raise HTTPException(
                status_code=403,
                detail="organization_id is required for non-superadmin context.",
            )

        # ------------------------------------------------------------------
        # Phase 1: Fetch job data, validate, mark running — short DB session.
        # All data needed for Phase 2 is serialised to plain Python objects
        # before the session closes so no DB connection is held during the AI call.
        # ------------------------------------------------------------------
        project_dict: dict
        photos: list
        job_retry_count: int

        async with WorkerAsyncSessionFactory() as session:
            repo = AnalysisRepository(session)
            photo_repo = PhotoRepository(session)

            job = await repo.get_analysis_job(job_id)
            if not job:
                log.error("worker.job_not_found")
                raise HTTPException(status_code=404, detail="Analysis job not found.")

            # R-19: idempotency guard — skip if job was already picked up or cancelled
            if job.status != ANALYSIS_JOB_STATUS_QUEUED:
                log.warning("worker.job_skipped", reason="not_queued", current_status=job.status)
                return

            if job.project_id != project_id:
                log.error("worker.job_project_mismatch", job_project_id=job.project_id, expected_project_id=project_id)
                log.warning("SECURITY_EVENT: job_project_mismatch", job_id=job_id, job_project_id=job.project_id, requested_project_id=project_id)
                await _fail_job_and_raise(job, repo, message=f"Job {job_id} belongs to project {job.project_id}, not {project_id}.", status_code=403, detail="Job project mismatch.")

            if organization_id is None:
                log.info("worker.superadmin_bypass", job_id=job_id, project_id=project_id)

            if organization_id is not None:
                project = await repo.get_project_in_org(project_id, organization_id)
            else:
                project = await session.get(Project, project_id)

            if not project:
                log.error("worker.project_not_found", organization_id=organization_id)
                log.warning("SECURITY_EVENT: org_mismatch", project_id=project_id, organization_id=organization_id)
                await _fail_job_and_raise(job, repo, message="Project not found.", status_code=403, detail="Project not found.")

            try:
                await repo.mark_job_running(job)
            except InvalidAnalysisJobStatusTransition:
                log.warning("worker.job_skipped", reason="invalid_status_transition", current_status=job.status)
                return

            photos = await photo_repo.list_photos_by_project_id(project_id)
            input_data = {
                "provider": self.provider_key,
                "project_id": project.id,
                "title": project.title,
                "property_type": project.property_type,
                "repair_scope": project.repair_scope,
                "photo_count": len(photos),
            }
            job.input_payload = json.dumps(input_data, ensure_ascii=False)

            # Capture all primitives needed for Phase 2 & 3 before session closes.
            # expire_on_commit=False keeps ORM attribute values accessible on
            # detached objects, so photos list is safe to pass to run_project_analysis.
            job_retry_count = job.retry_count
            project_dict = {
                "id": project.id,
                "title": project.title,
                "description": project.description,
                "address_label": project.address_label,
                "property_type": project.property_type,
                "repair_scope": project.repair_scope,
            }

            await session.commit()
        # Phase 1 session CLOSED — no DB connection held from this point.

        log.info(
            "worker.job_started",
            provider=self.provider_key,
            photo_count=len(photos),
            retry_count=job_retry_count,
        )

        # ------------------------------------------------------------------
        # Phase 2: AI analysis — no DB connection held for up to 180 s.
        # Errors are captured as plain values; DB writes happen in Phase 3.
        # ------------------------------------------------------------------
        analysis: dict | None = None
        _failure_message: str | None = None
        _failure_traceback: str | None = None
        _failure_type: str | None = None  # "invalid_payload" | "timeout" | "exception"

        try:
            analysis = await asyncio.wait_for(
                run_project_analysis(
                    provider_key=self.provider_key,
                    project=project_dict,
                    photos=photos,  # detached ORM objects; attrs cached (expire_on_commit=False)
                ),
                timeout=_JOB_TIMEOUT_SECONDS,
            )
        except InvalidAnalysisResultPayloadError as exc:
            _failure_message = f"Invalid analysis payload: {exc}"
            _failure_type = "invalid_payload"
            log.warning("worker.invalid_analysis_payload", error=str(exc), retry_count=job_retry_count)
            if job_retry_count >= _REPEATED_FAILURE_THRESHOLD:
                log.warning("worker.job_repeated_failure", retry_count=job_retry_count,
                            max_retry_count=_MAX_JOB_RETRY_COUNT, error=_failure_message)
        except asyncio.TimeoutError:
            _failure_message = f"Analysis timed out after {_JOB_TIMEOUT_SECONDS}s."
            _failure_type = "timeout"
            log.error("worker.job_timeout", timeout_seconds=_JOB_TIMEOUT_SECONDS, retry_count=job_retry_count)
            if job_retry_count >= _REPEATED_FAILURE_THRESHOLD:
                log.warning("worker.job_repeated_failure", retry_count=job_retry_count,
                            max_retry_count=_MAX_JOB_RETRY_COUNT, error=_failure_message)
        except Exception as exc:
            _failure_message = str(exc)
            _failure_traceback = traceback.format_exc()
            _failure_type = "exception"
            log.error("worker.job_failed", error=str(exc), retry_count=job_retry_count, exc_info=True)
            if job_retry_count >= _REPEATED_FAILURE_THRESHOLD:
                log.warning("worker.job_repeated_failure", retry_count=job_retry_count,
                            max_retry_count=_MAX_JOB_RETRY_COUNT, error=str(exc))

        # ------------------------------------------------------------------
        # Phase 3: Persist result or failure — new short DB session.
        # Re-fetch the job: it may have been externally cancelled during Phase 2.
        # ------------------------------------------------------------------
        duration: float | None = None

        async with WorkerAsyncSessionFactory() as session:
            repo = AnalysisRepository(session)

            job = await repo.get_analysis_job(job_id)
            if not job:
                log.error("worker.job_disappeared_before_result")
                return

            # Honour external cancellation that happened while Phase 2 ran.
            if job.status == ANALYSIS_JOB_STATUS_CANCELED:
                log.info("worker.job_cancelled_during_analysis", job_id=job_id)
                return

            if _failure_type is not None:
                # Failure path — persist the error and exit.
                try:
                    await repo.fail_job(
                        job,
                        message=_failure_message,
                        error_traceback=_failure_traceback,
                    )
                except InvalidAnalysisJobStatusTransition:
                    log.warning("worker.job_fail_rejected", job_id=job_id, current_status=job.status)
                return

            # Success path — re-fetch project for complete_job_with_result.
            if organization_id is not None:
                project = await repo.get_project_in_org(project_id, organization_id)
            else:
                project = await session.get(Project, project_id)

            if not project:
                log.error("worker.project_disappeared_before_result", project_id=project_id)
                await repo.fail_job(job, message="Project not found when persisting analysis result.")
                return

            try:
                await repo.complete_job_with_result(job, project, analysis)
            except InvalidAnalysisJobStatusTransition:
                log.warning("worker.job_complete_rejected", job_id=job_id, current_status=job.status)
                return
            except InvalidAnalysisResultPayloadError as exc:
                # AI returned structurally invalid data — fail the job and stop.
                error_msg = f"Invalid analysis payload: {exc}"
                log.warning("worker.invalid_analysis_payload", error=str(exc), retry_count=job_retry_count)
                if job_retry_count >= _REPEATED_FAILURE_THRESHOLD:
                    log.warning("worker.job_repeated_failure", retry_count=job_retry_count,
                                max_retry_count=_MAX_JOB_RETRY_COUNT, error=error_msg)
                try:
                    await repo.fail_job(job, message=error_msg)
                except InvalidAnalysisJobStatusTransition:
                    log.warning("worker.job_fail_rejected_after_invalid_payload",
                                job_id=job_id, current_status=job.status)
                return

            # expire_on_commit=False: job.finished_at / started_at are still
            # accessible after the commit inside complete_job_with_result.
            duration = (
                round((job.finished_at - job.started_at).total_seconds(), 1)
                if job.started_at and job.finished_at else None
            )
            output_summary = {
                "provider": analysis.get("providerKey"),
                "model_name": analysis.get("modelName"),
                "object_type": analysis.get("objectType"),
                "estimated_area_sqm": analysis.get("estimatedAreaSqm"),
                "area_confidence": analysis.get("areaConfidence"),
                "duration_seconds": duration,
            }
            try:
                job.output_summary = json.dumps(output_summary, ensure_ascii=False)
                await session.commit()
            except Exception as exc:
                log.warning("worker.output_summary_persist_failed", error=str(exc))
        # Phase 3 session CLOSED.

        log.info(
            "worker.job_completed",
            duration_seconds=duration,
            model=analysis.get("modelName"),
            object_type=analysis.get("objectType"),
            estimated_area=analysis.get("estimatedAreaSqm"),
        )

        # Non-critical: recalculate quote variants in a dedicated short session.
        try:
            async with WorkerAsyncSessionFactory() as qv_session:
                from app.repositories.quote_variant_repository import QuoteVariantRepository
                from app.services.quote_variant_service import QuoteVariantService
                await QuoteVariantService(QuoteVariantRepository(qv_session)).recalculate_quote_variants(project_id)
            log.info("worker.quote_variants_recalculated")
        except Exception as qe:
            log.warning("worker.quote_variants_failed", error=str(qe))

    async def fail_job_before_processing(
        self,
        job_id: str,
        *,
        message: str,
        error_traceback: str | None = None,
    ) -> bool:
        async with WorkerAsyncSessionFactory() as session:
            repo = AnalysisRepository(session)
            job = await repo.get_analysis_job(job_id)
            if not job:
                logger.warning("worker.job_not_found_for_failure", job_id=job_id)
                return False
            try:
                await repo.fail_job(job, message=message, error_traceback=error_traceback)
            except InvalidAnalysisJobStatusTransition:
                logger.warning(
                    "worker.job_failure_rejected",
                    job_id=job_id,
                    current_status=job.status,
                )
                return False
        return True

    async def retry_job(
        self,
        job_id: str,
        organization_id: str | None = None,
        *,
        is_superadmin_context: bool = False,
    ) -> AnalysisJob | None:
        """
        Creates a new queued job that is a retry of the given job.
        The caller (route) must enqueue the returned job.
        Raises HTTPException on org mismatch (403), job not found (404),
        or invalid state / retry limit exceeded (409).

        organization_id=None is the superadmin cross-tenant path. Callers MUST
        set is_superadmin_context=True when intentionally omitting organization_id.
        """
        if organization_id is None and not is_superadmin_context:
            logger.warning(
                "SECURITY_EVENT: retry_job_missing_org_id",
                job_id=job_id,
            )
            raise HTTPException(
                status_code=403,
                detail="organization_id is required for non-superadmin context.",
            )

        if organization_id is None:
            # Superadmin path — no org filter; observable via log
            logger.info("worker.superadmin_bypass", job_id=job_id)

        original = await self.repository.get_analysis_job(job_id)
        if not original:
            raise HTTPException(status_code=404, detail="Analysis job not found.")

        # Only terminal states can be retried — prevent two active jobs for the same project.
        if original.status not in (ANALYSIS_JOB_STATUS_FAILED, ANALYSIS_JOB_STATUS_CANCELED):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot retry a job in '{original.status}' state. "
                    "Only failed or canceled jobs can be retried."
                ),
            )

        # Enforce a hard ceiling to prevent runaway AI provider cost.
        if (original.retry_count or 0) >= _MAX_JOB_RETRY_COUNT:
            logger.warning(
                "worker.job_dead_letter",
                job_id=job_id,
                project_id=original.project_id,
                retry_count=original.retry_count,
                max_retry_count=_MAX_JOB_RETRY_COUNT,
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Maximum retry count ({_MAX_JOB_RETRY_COUNT}) reached for job {job_id}. "
                    "Contact an administrator to force-reset the job."
                ),
            )

        # Single session for both the org-scope project fetch and new job creation,
        # avoiding detached-instance access when project is used outside its session.
        async with AsyncSessionFactory() as session:
            repo_inner = AnalysisRepository(session)
            if organization_id is not None:
                project = await repo_inner.get_project_in_org(original.project_id, organization_id)
            else:
                project = await session.get(Project, original.project_id)
            if not project:
                logger.warning(
                    "SECURITY_EVENT: org_mismatch",
                    project_id=original.project_id,
                    organization_id=organization_id,
                )
                raise HTTPException(status_code=403, detail="Project not found.")

            new_retry_count = (original.retry_count or 0) + 1
            new_job = await repo_inner.create_queued_job(
                project,
                user_id=original.requested_by_user_id,
                parent_job_id=original.id,
                retry_count=new_retry_count,
            )

        logger.info(
            "worker.retry_queued",
            original_job_id=job_id,
            new_job_id=new_job.id,
            retry_count=new_retry_count,
        )
        return new_job

    async def cancel_analysis_job(self, job_id: str, *, organization_id: str | None = None) -> dict | None:
        if organization_id is not None:
            job = await self.repository.get_analysis_job_in_org(job_id, organization_id)
        else:
            job = await self.repository.get_analysis_job(job_id)
        if not job:
            return None
        if job.status in ANALYSIS_JOB_FINAL_STATUSES:
            return to_job_read(job)
        updated = await self.repository.update_analysis_job_status(job, ANALYSIS_JOB_STATUS_CANCELED)
        return to_job_read(updated)

    async def update_manual_selection(self, project_id: str, changes: dict) -> AnalysisResultRead | None:
        updated = await self.repository.update_latest_analysis_manual_selection(project_id, changes)
        return to_read_model(updated) if updated else None

    async def update_manual_selection_by_result_id(
        self,
        analysis_result_id: str,
        changes: dict,
        *,
        organization_id: str | None = None,
    ) -> AnalysisResultRead | None:
        if organization_id is not None:
            result = await self.repository.get_analysis_result_in_org(analysis_result_id, organization_id)
        else:
            result = await self.repository.get_analysis_result(analysis_result_id)
        if result is None:
            return None
        updated = await self.repository.update_analysis_manual_selection(result, changes)
        return to_read_model(updated)

    def describe_provider(self) -> dict:
        return describe_analysis_provider(self.provider_key)
