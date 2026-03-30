import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import traceback

import structlog
from fastapi import HTTPException

from app.ai import describe_analysis_provider, run_project_analysis
from app.core.config import get_settings
from app.core.metrics import observe_job_outcome, record_duplicate_prevented
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
    ANALYSIS_JOB_STATUS_RUNNING,
    AnalysisRepository,
    AnalysisJobLeaseOwnershipError,
    _normalize_utc_datetime,
    InvalidAnalysisResultPayloadError,
    InvalidAnalysisJobStatusTransition,
)
from app.repositories.photo_repository import PhotoRepository
from app.schemas.analysis import AnalysisResultRead, parse_json_field
from app.worker.queue import get_analysis_job_queue_counts

logger = structlog.get_logger(__name__)

_JOB_TIMEOUT_SECONDS = 180  # 3 minutes — generous upper bound for vision API calls
_MAX_JOB_RETRY_COUNT = 10  # Hard ceiling to prevent runaway cost from AI provider calls
_REPEATED_FAILURE_THRESHOLD = 3  # Emit dead-letter sentinel after this many retries


@dataclass(frozen=True)
class AnalysisJobCreateResult:
    job: AnalysisJob
    created_new: bool


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


def _lease_datetime_from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _job_duration_seconds(job: AnalysisJob) -> float | None:
    if not job.started_at or not job.finished_at:
        return None
    return round(
        (
            _normalize_utc_datetime(job.finished_at)
            - _normalize_utc_datetime(job.started_at)
        ).total_seconds(),
        1,
    )


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

    async def _enforce_tenant_active_job_limit(
        self,
        repository: AnalysisRepository,
        *,
        organization_id: str | None,
    ) -> None:
        if not organization_id:
            return

        settings = get_settings()
        active_jobs = await repository.count_active_jobs_for_organization(organization_id)
        if active_jobs >= settings.analysis_jobs_per_tenant_limit:
            logger.warning(
                "worker.tenant_active_job_limit_reached",
                organization_id=organization_id,
                active_jobs=active_jobs,
                max_active_jobs=settings.analysis_jobs_per_tenant_limit,
            )
            raise HTTPException(
                status_code=429,
                detail=(
                    "Too many active analysis jobs for this tenant. "
                    "Please wait for queued or running jobs to finish."
                ),
            )

    async def _enforce_queue_precheck(self, job_queue) -> None:
        if job_queue is None:
            return

        settings = get_settings()
        queued, processing = await get_analysis_job_queue_counts(job_queue)
        if queued + processing + 1 > settings.analysis_queue_max_depth:
            logger.warning(
                "worker.queue_capacity_reached",
                queued=queued,
                processing=processing,
                max_depth=settings.analysis_queue_max_depth,
            )
            raise HTTPException(
                status_code=429,
                detail="Analysis queue is full. Please retry later.",
            )

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
                         parent_job_id: str | None = None, retry_count: int = 0,
                         job_queue=None) -> AnalysisJobCreateResult:
        """Creates a queued job record, or returns an existing active job (idempotent)."""
        existing = await self.repository.get_active_job_for_project(project.id)
        if existing:
            record_duplicate_prevented("active_job_exists")
            logger.info(
                "worker.job_already_active",
                project_id=project.id,
                tenant_id=getattr(project, "organization_id", None),
                existing_job_id=existing.id,
                status=existing.status,
            )
            return AnalysisJobCreateResult(job=existing, created_new=False)
        await self._enforce_tenant_active_job_limit(
            self.repository,
            organization_id=getattr(project, "organization_id", None),
        )
        await self._enforce_queue_precheck(job_queue)
        job = await self.repository.create_queued_job(
            project,
            user_id=user_id,
            parent_job_id=parent_job_id,
            retry_count=retry_count,
        )
        return AnalysisJobCreateResult(job=job, created_new=True)

    async def execute_job(
        self,
        job_id: str,
        project_id: str,
        organization_id: str | None = None,
        *,
        is_superadmin_context: bool = False,
        lease_token: str | None = None,
        worker_id: str | None = None,
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
        log = logger.bind(
            job_id=job_id,
            project_id=project_id,
            tenant_id=organization_id,
            worker_id=worker_id,
        )

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

            if job.status == ANALYSIS_JOB_STATUS_COMPLETED:
                record_duplicate_prevented("already_completed")
                log.info("worker.job_skipped", reason="already_completed")
                return

            # R-19: idempotency guard — skip if job was already picked up or cancelled
            if job.status != ANALYSIS_JOB_STATUS_QUEUED:
                record_duplicate_prevented("not_queued")
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

            claim_timestamp = datetime.now(UTC)
            try:
                await repo.mark_job_running(
                    job,
                    lease_token=lease_token,
                    worker_id=worker_id,
                    leased_at=claim_timestamp,
                    heartbeat_at=claim_timestamp,
                )
            except InvalidAnalysisJobStatusTransition:
                record_duplicate_prevented("invalid_status_transition")
                log.warning("worker.job_skipped", reason="invalid_status_transition", current_status=job.status)
                return

            if lease_token is not None and worker_id is not None:
                await repo.assert_job_lease_owned(
                    job,
                    lease_token=lease_token,
                    worker_id=worker_id,
                )

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
            status="running",
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
            log.warning(
                "worker.invalid_analysis_payload",
                error=str(exc),
                retry_count=job_retry_count,
                status="failed",
            )
            if job_retry_count >= _REPEATED_FAILURE_THRESHOLD:
                log.warning("worker.job_repeated_failure", retry_count=job_retry_count,
                            max_retry_count=_MAX_JOB_RETRY_COUNT, error=_failure_message)
        except asyncio.TimeoutError:
            _failure_message = f"Analysis timed out after {_JOB_TIMEOUT_SECONDS}s."
            _failure_type = "timeout"
            log.error(
                "worker.job_timeout",
                timeout_seconds=_JOB_TIMEOUT_SECONDS,
                retry_count=job_retry_count,
                status="failed",
            )
            if job_retry_count >= _REPEATED_FAILURE_THRESHOLD:
                log.warning("worker.job_repeated_failure", retry_count=job_retry_count,
                            max_retry_count=_MAX_JOB_RETRY_COUNT, error=_failure_message)
        except Exception as exc:
            _failure_message = str(exc)
            _failure_traceback = traceback.format_exc()
            _failure_type = "exception"
            log.error(
                "worker.job_failed",
                error=str(exc),
                retry_count=job_retry_count,
                status="failed",
                exc_info=True,
            )
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

            if lease_token is not None and worker_id is not None:
                try:
                    await repo.assert_job_lease_owned(
                        job,
                        lease_token=lease_token,
                        worker_id=worker_id,
                    )
                except AnalysisJobLeaseOwnershipError:
                    log.warning(
                        "worker.job_aborted_lost_db_lease",
                        job_id=job_id,
                        lease_token=lease_token,
                        worker_id=worker_id,
                    )
                    raise

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
                    duration = _job_duration_seconds(job)
                    observe_job_outcome(status="failed", duration_seconds=duration)
                    log.error(
                        "worker.job_finished",
                        status="failed",
                        duration_seconds=duration,
                        error_message=_failure_message,
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
                duration = _job_duration_seconds(job)
                observe_job_outcome(status="failed", duration_seconds=duration)
                log.error(
                    "worker.job_finished",
                    status="failed",
                    duration_seconds=duration,
                    error_message="Project not found when persisting analysis result.",
                )
                return

            try:
                await repo.complete_job_with_result(job, project, analysis)
            except InvalidAnalysisJobStatusTransition:
                log.warning("worker.job_complete_rejected", job_id=job_id, current_status=job.status)
                return
            except InvalidAnalysisResultPayloadError as exc:
                # AI returned structurally invalid data — fail the job and stop.
                error_msg = f"Invalid analysis payload: {exc}"
                log.warning(
                    "worker.invalid_analysis_payload",
                    error=str(exc),
                    retry_count=job_retry_count,
                    status="failed",
                )
                if job_retry_count >= _REPEATED_FAILURE_THRESHOLD:
                    log.warning("worker.job_repeated_failure", retry_count=job_retry_count,
                                max_retry_count=_MAX_JOB_RETRY_COUNT, error=error_msg)
                try:
                    await repo.fail_job(job, message=error_msg)
                    duration = _job_duration_seconds(job)
                    observe_job_outcome(status="failed", duration_seconds=duration)
                    log.error(
                        "worker.job_finished",
                        status="failed",
                        duration_seconds=duration,
                        error_message=error_msg,
                    )
                except InvalidAnalysisJobStatusTransition:
                    log.warning("worker.job_fail_rejected_after_invalid_payload",
                                job_id=job_id, current_status=job.status)
                return

            duration = _job_duration_seconds(job)
        # Phase 3 session CLOSED.

        observe_job_outcome(status="completed", duration_seconds=duration)
        log.info(
            "worker.job_finished",
            status="completed",
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
                duration = _job_duration_seconds(job)
                observe_job_outcome(status="failed", duration_seconds=duration)
                logger.error(
                    "worker.job_finished",
                    job_id=job_id,
                    tenant_id=getattr(job, "organization_id", None),
                    worker_id=getattr(job, "worker_id", None),
                    status="failed",
                    duration_seconds=duration,
                )
            except InvalidAnalysisJobStatusTransition:
                logger.warning(
                    "worker.job_failure_rejected",
                    job_id=job_id,
                    current_status=job.status,
                )
                return False
        return True

    async def refresh_job_lease_heartbeat(
        self,
        job_id: str,
        *,
        lease_token: str,
        worker_id: str,
        leased_at_ms: int,
    ) -> bool:
        timestamp = _lease_datetime_from_ms(leased_at_ms)
        async with WorkerAsyncSessionFactory() as session:
            repo = AnalysisRepository(session)
            return await repo.heartbeat_job_lease(
                job_id,
                lease_token=lease_token,
                worker_id=worker_id,
                leased_at=timestamp,
                heartbeat_at=timestamp,
            )

    async def reconcile_expired_lease(self, lease) -> str:
        """Reconcile an expired worker lease against DB state.

        Returns:
            "requeue" for queued/running jobs that should be returned to Redis
            "drop" for missing/final jobs whose payload must be discarded
        """
        lease_acquired_at = _lease_datetime_from_ms(lease.leased_at_ms)
        fresh_after = datetime.now(UTC).timestamp() - lease.lease_timeout_seconds
        async with WorkerAsyncSessionFactory() as session:
            repo = AnalysisRepository(session)
            job = await repo.get_analysis_job(lease.job_id)
            if not job:
                logger.warning("worker.reconcile_missing_job", job_id=lease.job_id)
                return "drop"

            if job.status in ANALYSIS_JOB_FINAL_STATUSES:
                return "drop"

            if job.lease_token != lease.token or job.worker_id != lease.worker_id:
                logger.info(
                    "worker.reconcile_dropped_stale_lease",
                    job_id=lease.job_id,
                    lease_token=lease.token,
                    worker_id=lease.worker_id,
                    db_lease_token=job.lease_token,
                    db_worker_id=job.worker_id,
                )
                return "drop"

            if job.leased_at is not None and job.leased_at > lease_acquired_at:
                logger.info(
                    "worker.reconcile_dropped_renewed_lease",
                    job_id=lease.job_id,
                    lease_token=lease.token,
                )
                return "drop"

            if job.heartbeat_at is not None and job.heartbeat_at.timestamp() >= fresh_after:
                logger.info(
                    "worker.reconcile_kept_fresh_heartbeat",
                    job_id=lease.job_id,
                    lease_token=lease.token,
                    heartbeat_at=job.heartbeat_at.isoformat(),
                )
                return "drop"

            if job.status == ANALYSIS_JOB_STATUS_RUNNING:
                try:
                    await repo.reset_job_to_queued(job)
                except InvalidAnalysisJobStatusTransition:
                    logger.warning(
                        "worker.reconcile_reset_rejected",
                        job_id=lease.job_id,
                        current_status=job.status,
                    )
                    return "drop"
                logger.warning("worker.reconcile_running_job_requeued", job_id=lease.job_id)
                return "requeue"

            if job.status == ANALYSIS_JOB_STATUS_QUEUED:
                return "requeue"

            logger.warning(
                "worker.reconcile_unknown_state",
                job_id=lease.job_id,
                current_status=job.status,
            )
            return "drop"

    async def retry_job(
        self,
        job_id: str,
        organization_id: str | None = None,
        *,
        is_superadmin_context: bool = False,
        job_queue=None,
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

            await self._enforce_tenant_active_job_limit(
                repo_inner,
                organization_id=project.organization_id,
            )
            await self._enforce_queue_precheck(job_queue)

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
