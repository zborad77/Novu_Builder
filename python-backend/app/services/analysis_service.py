import asyncio
import json
import traceback
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException

from app.ai import describe_analysis_provider, run_project_analysis
from app.db.session import AsyncSessionFactory
from app.models import AnalysisJob, AnalysisResult, Project
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.photo_repository import PhotoRepository
from app.schemas.analysis import AnalysisResultRead, parse_json_field

logger = structlog.get_logger(__name__)

_JOB_TIMEOUT_SECONDS = 180  # 3 minutes — generous upper bound for vision API calls
_MAX_JOB_RETRY_COUNT = 10  # Hard ceiling to prevent runaway cost from AI provider calls


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
    session,
    *,
    message: str,
    status_code: int,
    detail: str,
) -> None:
    """Mark job as failed, commit, then raise HTTPException. Never returns."""
    job.status = "failed"
    job.error_message = message
    job.finished_at = datetime.now(UTC)
    await session.commit()
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
        """Runs the analysis in the background. Uses its own DB session.

        organization_id=None is the superadmin cross-tenant path. Callers MUST
        set is_superadmin_context=True when intentionally omitting organization_id;
        otherwise a 403 is raised to prevent accidental tenant-isolation bypass.
        """
        log = logger.bind(job_id=job_id, project_id=project_id)

        if organization_id is None and not is_superadmin_context:
            log.warning(
                "SECURITY_EVENT: execute_job_missing_org_id",
                job_id=job_id,
                project_id=project_id,
            )
            raise HTTPException(
                status_code=403,
                detail="organization_id is required for non-superadmin context.",
            )

        async with AsyncSessionFactory() as session:
            repo = AnalysisRepository(session)
            photo_repo = PhotoRepository(session)

            job = await repo.get_analysis_job(job_id)
            if not job:
                log.error("worker.job_not_found")
                raise HTTPException(status_code=404, detail="Analysis job not found.")

            # R-19: idempotency guard — skip if job was already picked up or cancelled
            if job.status != "queued":
                log.warning("worker.job_skipped", reason="not_queued", current_status=job.status)
                return

            if job.project_id != project_id:
                log.error("worker.job_project_mismatch", job_project_id=job.project_id, expected_project_id=project_id)
                log.warning("SECURITY_EVENT: job_project_mismatch", job_id=job_id, job_project_id=job.project_id, requested_project_id=project_id)
                await _fail_job_and_raise(job, session, message=f"Job {job_id} belongs to project {job.project_id}, not {project_id}.", status_code=403, detail="Job project mismatch.")

            if organization_id is None:
                # Superadmin path — no org filter; observable via log
                log.info("worker.superadmin_bypass", job_id=job_id, project_id=project_id)

            if organization_id is not None:
                project = await repo.get_project_in_org(project_id, organization_id)
            else:
                project = await session.get(Project, project_id)

            if not project:
                log.error("worker.project_not_found", organization_id=organization_id)
                log.warning("SECURITY_EVENT: org_mismatch", project_id=project_id, organization_id=organization_id)
                await _fail_job_and_raise(job, session, message="Project not found.", status_code=403, detail="Project not found.")

            job.status = "running"
            job.started_at = datetime.now(UTC)
            await session.commit()

            # Build and persist input payload for debugging
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
            await session.commit()

            log.info(
                "worker.job_started",
                provider=self.provider_key,
                photo_count=len(photos),
                retry_count=job.retry_count,
            )

            try:
                analysis = await asyncio.wait_for(
                    run_project_analysis(
                        provider_key=self.provider_key,
                        project={
                            "id": project.id,
                            "title": project.title,
                            "description": project.description,
                            "address_label": project.address_label,
                            "property_type": project.property_type,
                            "repair_scope": project.repair_scope,
                        },
                        photos=photos,
                    ),
                    timeout=_JOB_TIMEOUT_SECONDS,
                )

                await repo.complete_job_with_result(job, project, analysis)

                # Persist output summary
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
                job.output_summary = json.dumps(output_summary, ensure_ascii=False)
                await session.commit()

                log.info(
                    "worker.job_completed",
                    duration_seconds=duration,
                    model=analysis.get("modelName"),
                    object_type=analysis.get("objectType"),
                    estimated_area=analysis.get("estimatedAreaSqm"),
                )

                # Non-critical: recalculate quote variants
                try:
                    from app.repositories.quote_variant_repository import QuoteVariantRepository
                    from app.services.quote_variant_service import QuoteVariantService
                    await QuoteVariantService(QuoteVariantRepository(session)).recalculate_quote_variants(project_id)
                    log.info("worker.quote_variants_recalculated")
                except Exception as qe:
                    log.warning("worker.quote_variants_failed", error=str(qe))

            except asyncio.TimeoutError:
                job.status = "failed"
                job.error_message = f"Analysis timed out after {_JOB_TIMEOUT_SECONDS}s."
                job.finished_at = datetime.now(UTC)
                await session.commit()
                log.error("worker.job_timeout", timeout_seconds=_JOB_TIMEOUT_SECONDS)

            except Exception as exc:
                tb = traceback.format_exc()
                job.status = "failed"
                job.error_message = str(exc)
                job.error_traceback = tb
                job.finished_at = datetime.now(UTC)
                await session.commit()

                log.error(
                    "worker.job_failed",
                    error=str(exc),
                    retry_count=job.retry_count,
                    exc_info=True,
                )

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
        if original.status not in ("failed", "canceled"):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot retry a job in '{original.status}' state. "
                    "Only failed or canceled jobs can be retried."
                ),
            )

        # Enforce a hard ceiling to prevent runaway AI provider cost.
        if (original.retry_count or 0) >= _MAX_JOB_RETRY_COUNT:
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
        if job.status == "completed":
            return to_job_read(job)
        updated = await self.repository.update_analysis_job_status(job, "canceled")
        return to_job_read(updated)

    async def update_manual_selection(self, project_id: str, changes: dict) -> AnalysisResultRead | None:
        updated = await self.repository.update_latest_analysis_manual_selection(project_id, changes)
        return to_read_model(updated) if updated else None

    async def update_manual_selection_by_result_id(self, analysis_result_id: str, changes: dict) -> AnalysisResultRead | None:
        result = await self.repository.get_analysis_result(analysis_result_id)
        if result is None:
            return None
        updated = await self.repository.update_analysis_manual_selection(result, changes)
        return to_read_model(updated)

    def describe_provider(self) -> dict:
        return describe_analysis_provider(self.provider_key)
