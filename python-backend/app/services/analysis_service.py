from app.ai import describe_analysis_provider, run_project_analysis
from app.models import AnalysisJob, AnalysisResult, Project
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.photo_repository import PhotoRepository
from app.schemas.analysis import AnalysisResultRead, parse_json_field


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
        workflow=parse_json_field(result.workflow_suggestion_json),
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
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
        "errorMessage": job.error_message,
        "createdAt": job.created_at,
    }


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
        if result is None:
            return None
        return to_read_model(result)

    async def get_analysis_result_by_id(self, analysis_result_id: str) -> AnalysisResultRead | None:
        result = await self.repository.get_analysis_result(analysis_result_id)
        if result is None:
            return None
        return to_read_model(result)

    async def list_jobs(self, project_id: str) -> list[dict]:
        jobs = await self.repository.list_analysis_jobs_by_project_id(project_id)
        return [to_job_read(job) for job in jobs]

    async def get_job(self, job_id: str) -> dict | None:
        job = await self.repository.get_analysis_job(job_id)
        return to_job_read(job) if job else None

    async def trigger_analysis(self, project: Project) -> dict:
        photos = await self.photo_repository.list_photos_by_project_id(project.id)
        analysis = await run_project_analysis(
            provider_key=self.provider_key,
            project={
                "id": project.id,
                "description": project.description,
                "address_label": project.address_label,
            },
            photos=photos,
        )
        job, result = await self.repository.create_analysis_record(project, analysis)
        return {
            "jobId": job.id,
            "status": job.status,
            "provider": analysis.get("providerKey"),
            "modelName": result.model_name,
            "modelVersion": result.model_version,
        }

    async def retry_analysis_job(self, job_id: str, project: Project) -> dict | None:
        job = await self.repository.get_analysis_job(job_id)
        if not job:
            return None
        return await self.trigger_analysis(project)

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
        if updated is None:
            return None
        return to_read_model(updated)

    async def update_manual_selection_by_result_id(self, analysis_result_id: str, changes: dict) -> AnalysisResultRead | None:
        result = await self.repository.get_analysis_result(analysis_result_id)
        if result is None:
            return None
        updated = await self.repository.update_analysis_manual_selection(result, changes)
        return to_read_model(updated)

    def describe_provider(self) -> dict:
        return describe_analysis_provider(self.provider_key)
