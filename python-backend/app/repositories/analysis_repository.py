import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisJob, AnalysisResult, Project


class AnalysisRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

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

    async def get_analysis_job(self, job_id: str) -> AnalysisJob | None:
        return await self.session.get(AnalysisJob, job_id)

    async def list_analysis_jobs_by_project_id(self, project_id: str) -> list[AnalysisJob]:
        result = await self.session.execute(
            select(AnalysisJob)
            .where(AnalysisJob.project_id == project_id)
            .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        )
        return list(result.scalars().all())

    async def create_queued_job(
        self,
        project: Project,
        *,
        user_id: str | None = None,
        parent_job_id: str | None = None,
        retry_count: int = 0,
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
            status="queued",
            job_type="manual_trigger",
            requested_by_user_id=resolved_user_id,
            parent_job_id=parent_job_id,
            retry_count=retry_count,
            started_at=None,
            finished_at=None,
            error_message=None,
            created_at=timestamp,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def complete_job_with_result(self, job: AnalysisJob, project: Project, analysis: dict) -> tuple[AnalysisJob, AnalysisResult]:
        timestamp = datetime.now(UTC)
        job.status = analysis.get("jobStatus", "completed")
        job.started_at = job.started_at or timestamp
        job.finished_at = timestamp
        job.error_message = analysis.get("errorMessage")

        result = AnalysisResult(
            id=f"ana_{uuid4().hex[:8]}",
            project_id=project.id,
            analysis_job_id=job.id,
            reference_photo_id=analysis.get("referencePhotoId"),
            object_type=analysis.get("objectType", "facade"),
            surface_condition=analysis.get("surfaceCondition", "requires_attention"),
            recommended_scope=analysis.get("recommendedScope", "local_repair"),
            estimated_area_sqm=float(analysis.get("estimatedAreaSqm") or 0),
            area_confidence=float(analysis.get("areaConfidence") or 0),
            selected_repair_polygon_json=json.dumps(analysis["selectedRepairPolygon"]) if analysis.get("selectedRepairPolygon") else None,
            manual_area_sqm=analysis.get("manualAreaSqm"),
            final_area_source=analysis.get("finalAreaSource", "ai"),
            mask_polygon_json=json.dumps(analysis.get("maskPolygon") or []),
            materials_suggestion_json=json.dumps(analysis.get("materials") or []),
            workflow_suggestion_json=json.dumps(analysis.get("workflowSteps") or []),
            estimated_duration_days=float(analysis["estimatedTotalDays"]) if analysis.get("estimatedTotalDays") is not None else None,
            labor_hours_total=float(analysis["laborHoursTotal"]) if analysis.get("laborHoursTotal") is not None else None,
            model_name=analysis.get("modelName", "mock-vision"),
            model_version=analysis.get("modelVersion", "0.1"),
            created_at=timestamp,
        )
        self.session.add(result)

        project.status = "analysed"
        project.property_type = analysis.get("objectType", project.property_type)
        project.repair_scope = analysis.get("recommendedScope", project.repair_scope)
        project.updated_at = timestamp

        await self.session.commit()
        await self.session.refresh(job)
        await self.session.refresh(result)
        return job, result

    async def create_analysis_record(self, project: Project, analysis: dict) -> tuple[AnalysisJob, AnalysisResult]:
        timestamp = datetime.now(UTC)
        job = AnalysisJob(
            id=f"job_{uuid4().hex[:8]}",
            project_id=project.id,
            status=analysis.get("jobStatus", "completed"),
            job_type=analysis.get("jobType", "manual_trigger"),
            requested_by_user_id=project.created_by_user_id or "usr_1",
            started_at=timestamp,
            finished_at=timestamp,
            error_message=analysis.get("errorMessage"),
            created_at=timestamp,
        )
        self.session.add(job)
        await self.session.flush()

        result = AnalysisResult(
            id=f"ana_{uuid4().hex[:8]}",
            project_id=project.id,
            analysis_job_id=job.id,
            reference_photo_id=analysis.get("referencePhotoId"),
            object_type=analysis.get("objectType", "facade"),
            surface_condition=analysis.get("surfaceCondition", "requires_attention"),
            recommended_scope=analysis.get("recommendedScope", "local_repair"),
            estimated_area_sqm=float(analysis.get("estimatedAreaSqm") or 0),
            area_confidence=float(analysis.get("areaConfidence") or 0),
            selected_repair_polygon_json=json.dumps(analysis["selectedRepairPolygon"]) if analysis.get("selectedRepairPolygon") else None,
            manual_area_sqm=analysis.get("manualAreaSqm"),
            final_area_source=analysis.get("finalAreaSource", "ai"),
            mask_polygon_json=json.dumps(analysis.get("maskPolygon") or []),
            materials_suggestion_json=json.dumps(analysis.get("materials") or []),
            workflow_suggestion_json=json.dumps(analysis.get("workflowSteps") or []),
            estimated_duration_days=float(analysis["estimatedTotalDays"]) if analysis.get("estimatedTotalDays") is not None else None,
            labor_hours_total=float(analysis["laborHoursTotal"]) if analysis.get("laborHoursTotal") is not None else None,
            model_name=analysis.get("modelName", "mock-vision"),
            model_version=analysis.get("modelVersion", "0.1"),
            created_at=timestamp,
        )
        self.session.add(result)

        project.status = "analysed"
        project.property_type = analysis.get("objectType", project.property_type)
        project.repair_scope = analysis.get("recommendedScope", project.repair_scope)
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
        job.status = status
        if status in {"canceled", "failed"}:
            job.finished_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(job)
        return job
