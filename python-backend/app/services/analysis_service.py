import asyncio
import json
import traceback
from datetime import UTC, datetime

import structlog

from app.ai import describe_analysis_provider, run_project_analysis
from app.db.session import AsyncSessionFactory
from app.models import AnalysisJob, AnalysisResult, Project
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.photo_repository import PhotoRepository
from app.schemas.analysis import AnalysisResultRead, parse_json_field

logger = structlog.get_logger(__name__)

_JOB_TIMEOUT_SECONDS = 180  # 3 minutes — generous upper bound for vision API calls


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

    async def get_analysis_result_by_id(self, analysis_result_id: str) -> AnalysisResultRead | None:
        result = await self.repository.get_analysis_result(analysis_result_id)
        return to_read_model(result) if result else None

    async def list_jobs(self, project_id: str) -> list[dict]:
        jobs = await self.repository.list_analysis_jobs_by_project_id(project_id)
        return [to_job_read(job) for job in jobs]

    async def get_job(self, job_id: str) -> dict | None:
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

    async def execute_job(self, job_id: str, project_id: str) -> None:
        """Runs the analysis in the background. Uses its own DB session."""
        log = logger.bind(job_id=job_id, project_id=project_id)

        async with AsyncSessionFactory() as session:
            repo = AnalysisRepository(session)
            photo_repo = PhotoRepository(session)

            job = await repo.get_analysis_job(job_id)
            if not job:
                log.error("worker.job_not_found")
                return

            project = await session.get(Project, project_id)
            if not project:
                job.status = "failed"
                job.error_message = "Project not found."
                job.finished_at = datetime.now(UTC)
                await session.commit()
                log.error("worker.project_not_found")
                return

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

    async def retry_job(self, job_id: str) -> AnalysisJob | None:
        """
        Creates a new queued job that is a retry of the given job.
        The caller (route) must schedule execute_job via BackgroundTasks.
        Returns the new job or None if original not found.
        """
        original = await self.repository.get_analysis_job(job_id)
        if not original:
            return None

        async with AsyncSessionFactory() as session:
            project = await session.get(Project, original.project_id)
            if not project:
                return None

        new_retry_count = (original.retry_count or 0) + 1
        new_job = await self.repository.create_queued_job(
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

    async def cancel_analysis_job(self, job_id: str) -> dict | None:
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
