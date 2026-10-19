"""Offer processing worker — dequeues offer jobs and calls the AI pipeline.

Session lifecycle (prevents pool starvation during long AI calls):
    Phase 1  open session → fetch + mark_job_running → get lease_version → CLOSE
    Phase 2  AI call (no DB connection held — may take 10-60 s)
    Phase 3  open session → fencing check → persist result → commit → CLOSE

Lease fencing:
    mark_job_running() increments lease_version and returns the new value.
    Phase-3 persist uses update_job_status_fenced(expected_lease_version=N).
    If 0 rows updated → a new worker took over → this stale worker aborts.

Budget lifecycle:
    reserve(job_id)       → atomic counter + reservation row (crash-safe)
    release(job_id)       → credit back on controlled failure
    record_actual(job_id) → mark consumed + adjust delta on success
    BudgetSweeper         → expires reservation rows forgotten by kill-9

Observability:
    Every log line from run() carries:
        job_id, offer_request_id, worker_id, attempt, work_type_code,
        organization_id, lease_version, agent_run_id, provider_key, model_id

    Timing logged at job completion:
        queue_wait_ms     — from job created_at to worker pickup
        ai_latency_ms     — pure AI provider call duration
        persist_latency_ms
        total_job_ms

Run as a standalone process:
    python -m app.worker.offer_runner
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from enum import Enum
import secrets
import sys
import time
from datetime import UTC, datetime, timedelta

import structlog

from app.core.config import get_settings, startup_failure_message
from app.core.logging import configure_logging
from app.core.redis_client import build_queue_redis_client_from_settings
from app.db.session import WorkerAsyncSessionFactory
from app.offer_processing.budget import (
    BudgetExhaustedError,
    BudgetService,
    DEFAULT_TOKEN_ESTIMATE,
    estimate_cost_usd,
)
from app.offer_processing.budget_sweeper import BudgetSweeper
from app.offer_processing.reconciler import OfferReconciler
from app.offer_processing.domain import (
    AGENT_OUTCOME_INSUFFICIENT_DATA,
    AGENT_OUTCOME_OFFER_GENERATED,
    ERROR_BUDGET_EXHAUSTED,
    ERROR_PROVIDER_RATE_LIMITED,
    ERROR_PROVIDER_UNAVAILABLE,
    ERROR_SNAPSHOT_BUILD_FAILED,
    ERROR_VALIDATION_FAILED,
    ERROR_UNKNOWN,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    OFFER_STATUS_FAILED,
    OFFER_STATUS_NEEDS_MORE_INFO,
    OFFER_STATUS_NEEDS_REVIEW,
    OFFER_STATUS_PROCESSING,
    OFFER_STATUS_QUEUED,
    POISON_THRESHOLD,
    RETRY_BACKOFF_SECONDS,
)
from app.offer_processing.outbox import OutboxPublisher, build_offer_status_changed_event
from app.offer_processing.provider import (
    AgentRuntime,
    ProviderError,
    ProviderRateLimitedError,
    ProviderRequest,
    ProviderUnavailableError,
    build_agent_runtime,
)
from app.offer_processing.repository import OfferRepository
from app.offer_processing.snapshot import build_input_snapshot
from app.repositories.photo_repository import PhotoRepository
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.storage.backend import generate_presigned_url
from app.offer_processing.validation import (
    InsufficientDataResult,
    OfferOutputValidator,
    OfferValidationError,
)
from app.worker.offer_queue import (
    DequeuedOfferJob,
    ack_offer_job,
    dequeue_offer_job,
)

logger = structlog.get_logger(__name__)

_POLL_INTERVAL_S  = 1.0
_LEASE_DURATION_S = 5 * 60
_DRAIN_TIMEOUT_S  = 30.0  # max seconds to wait for graceful background-task drain


class _AiInputResolutionError(RuntimeError):
    """Raised when mandatory AI inputs (the work-type whitelist) cannot be resolved.

    Fail-closed (Constitution Art. 6 & 9): the job must not proceed to validate AI
    output against a missing / permissive whitelist.
    """


class _WorkerState(str, Enum):
    STARTING      = "starting"
    HEALTHY       = "healthy"
    DRAINING      = "draining"
    SHUTTING_DOWN = "shutting_down"


# ---------------------------------------------------------------------------
# Single-job processor
# ---------------------------------------------------------------------------


class OfferJobProcessor:
    """Processes one dequeued offer job end-to-end."""

    def __init__(
        self,
        *,
        dequeued: DequeuedOfferJob,
        worker_id: str,
        agent_runtime: AgentRuntime,
        redis,
    ) -> None:
        self._dequeued = dequeued
        self._worker_id = worker_id
        self._agent_runtime = agent_runtime
        self._redis = redis
        self._payload = dequeued.payload
        self._job_start_ms = int(time.monotonic() * 1000)

    async def _resolve_ai_inputs(
        self, *, log
    ) -> tuple[list[str], dict, frozenset[str]]:
        """Resolve presigned photo URLs, the work-type definition, and the code whitelist.

        Fail-closed (Constitution Art. 6 & 9): the work-type whitelist is MANDATORY. If the
        catalog cannot be resolved, this raises ``_AiInputResolutionError`` so the job fails
        rather than validating AI output against a permissive (missing) whitelist. An empty
        catalog yields an empty whitelist, which the validator treats as "reject every code"
        — also fail-closed.

        Photo resolution is non-critical: an unreadable photo degrades the input (fewer
        images) and is logged (Art. 10), but does not fail the job.
        """
        photo_urls: list[str] = []
        work_type_def: dict = {}

        async with WorkerAsyncSessionFactory() as session:
            wc_repo = WorkCatalogRepository(session)
            try:
                work_type = await wc_repo.get_work_type_by_code(
                    self._payload.work_type_code
                )
                if work_type is not None:
                    work_type_def = {
                        "code": work_type.code,
                        "name": getattr(work_type, "name_cs", None)
                        or getattr(work_type, "name", ""),
                    }
                known_codes = frozenset(
                    wt.code for wt in await wc_repo.list_work_types_global()
                )
            except Exception as exc:  # noqa: BLE001 — logged, then re-raised fail-closed
                log.warning("offer_runner.catalog_resolution_failed", error=str(exc))
                raise _AiInputResolutionError(
                    "Work-type catalog resolution failed; refusing to validate AI "
                    "output without a whitelist."
                ) from exc

            photo_repo = PhotoRepository(session)
            for photo_id in self._payload.photo_ids:
                try:
                    photo = await photo_repo.get_photo_by_id_in_org(
                        photo_id, organization_id=self._payload.organization_id
                    )
                    if photo is not None and photo.storage_key:
                        photo_urls.append(generate_presigned_url(photo.storage_key))
                except Exception as exc:  # noqa: BLE001 — non-critical, logged, degrade
                    log.warning(
                        "offer_runner.photo_resolution_failed",
                        photo_id=photo_id,
                        error=str(exc),
                    )
                    continue

        return photo_urls, work_type_def, known_codes

    async def run(self) -> None:
        # Full context on every log line from this job
        log = logger.bind(
            job_id=self._payload.job_id,
            offer_request_id=self._payload.offer_request_id,
            worker_id=self._worker_id,
            attempt=self._payload.attempt,
            work_type_code=self._payload.work_type_code,
            organization_id=self._payload.organization_id,
            priority=self._payload.priority,
        )

        # -------------------------------------------------------------------
        # Phase 1: fetch job metadata + mark running + capture fencing token
        # -------------------------------------------------------------------
        leased_until = datetime.now(UTC) + timedelta(seconds=_LEASE_DURATION_S)
        lease_version: int
        queue_wait_ms: int = 0

        async with WorkerAsyncSessionFactory() as session:
            repo = OfferRepository(session)

            # Fetch job before marking running so we can compute queue_wait_ms
            # and read error_repeat_count for poison detection.
            job = await repo.get_offer_job(self._payload.job_id)
            if job and job.created_at:
                queue_wait_ms = int(
                    (datetime.now(UTC) - job.created_at).total_seconds() * 1000
                )
            _prior_error_code = job.last_error_code if job else None
            _prior_error_repeat = job.error_repeat_count if job else 0

            lease_version = await repo.mark_job_running(
                self._payload.job_id,
                worker_id=self._worker_id,
                leased_until=leased_until,
            )
            await repo.update_offer_status(
                self._payload.offer_request_id,
                new_status=OFFER_STATUS_PROCESSING,
            )
            session.add(
                build_offer_status_changed_event(
                    offer_request_id=self._payload.offer_request_id,
                    organization_id=self._payload.organization_id,
                    job_id=self._payload.job_id,
                    status=OFFER_STATUS_PROCESSING,
                )
            )
            await session.commit()

        # Rebind with lease_version + queue_wait_ms (available after Phase 1)
        log = log.bind(lease_version=lease_version, queue_wait_ms=queue_wait_ms)
        log.info("offer_runner.job_started")

        # -------------------------------------------------------------------
        # Budget pre-flight
        # -------------------------------------------------------------------
        budget_reserved = False
        actual_tokens = 0
        actual_cost = Decimal("0")

        try:
            async with WorkerAsyncSessionFactory() as session:
                budget = BudgetService(session)
                await budget.reserve(
                    self._payload.organization_id,
                    job_id=self._payload.job_id,
                )
                await session.commit()
            budget_reserved = True
        except BudgetExhaustedError:
            log.warning("offer_runner.budget_exhausted")
            await self._fail_job(
                error_code=ERROR_BUDGET_EXHAUSTED,
                error_detail="Daily AI budget exhausted.",
                retryable=False,
                lease_version=lease_version,
                log=log,
                prior_error_code=_prior_error_code,
                prior_error_repeat=_prior_error_repeat,
            )
            return

        # -------------------------------------------------------------------
        # Phase 2: build snapshot + create agent run record + AI call
        # -------------------------------------------------------------------
        run_id: str = ""
        known_codes: frozenset[str] | None = None
        t_ai_start = time.monotonic()

        try:
            # Resolve presigned photo URLs, the work-type definition, and the
            # code whitelist BEFORE the AI call (no DB session held during it).
            photo_urls, work_type_def, known_codes = await self._resolve_ai_inputs(log=log)

            snapshot = await build_input_snapshot(
                work_type_code=self._payload.work_type_code,
                parameters=self._payload.parameters,
                photo_presigned_urls=photo_urls,
                work_type_definition=work_type_def,
                pricing_context={},
                model_id=self._agent_runtime.primary.model_id,
                model_build=getattr(
                    self._agent_runtime.primary, "model_id", "unknown"
                ),
            )

            provider_req = ProviderRequest(
                work_type_code=self._payload.work_type_code,
                parameters=self._payload.parameters,
                photo_urls=photo_urls,
                work_type_definition=work_type_def,
                pricing_context={},
            )

            async with WorkerAsyncSessionFactory() as session:
                repo = OfferRepository(session)
                agent_run = await repo.create_agent_run(
                    offer_job_id=self._payload.job_id,
                    offer_request_id=self._payload.offer_request_id,
                    organization_id=self._payload.organization_id,
                    provider_key=self._agent_runtime.primary.key,
                    input_snapshot_hash=snapshot.sha256(),
                    snapshot_version_context=snapshot.version_context.as_dict(),
                    agent_model=self._agent_runtime.primary.model_id,
                )
                run_id = agent_run.id
                await session.commit()

            log = log.bind(
                agent_run_id=run_id,
                provider_key=self._agent_runtime.primary.key,
                model_id=self._agent_runtime.primary.model_id,
            )

            # AI call — no DB session open during this
            response = await self._agent_runtime.run(provider_req)
            ai_latency_ms = int((time.monotonic() - t_ai_start) * 1000)
            actual_tokens = response.prompt_tokens + response.completion_tokens
            actual_cost = estimate_cost_usd(actual_tokens)

        except _AiInputResolutionError as exc:
            # Fail-closed: could not resolve the mandatory work-type whitelist.
            await self._release_budget(budget_reserved, log=log)
            await self._fail_job(
                error_code=ERROR_SNAPSHOT_BUILD_FAILED,
                error_detail=str(exc),
                retryable=True,
                lease_version=lease_version,
                log=log,
                prior_error_code=_prior_error_code,
                prior_error_repeat=_prior_error_repeat,
            )
            return
        except ProviderRateLimitedError as exc:
            await self._release_budget(budget_reserved, log=log)
            await self._fail_job(
                error_code=ERROR_PROVIDER_RATE_LIMITED,
                error_detail=str(exc),
                retryable=True,
                lease_version=lease_version,
                log=log,
                prior_error_code=_prior_error_code,
                prior_error_repeat=_prior_error_repeat,
            )
            return
        except ProviderUnavailableError as exc:
            await self._release_budget(budget_reserved, log=log)
            await self._fail_job(
                error_code=ERROR_PROVIDER_UNAVAILABLE,
                error_detail=str(exc),
                retryable=True,
                lease_version=lease_version,
                log=log,
                prior_error_code=_prior_error_code,
                prior_error_repeat=_prior_error_repeat,
            )
            return
        except ProviderError as exc:
            await self._release_budget(budget_reserved, log=log)
            await self._fail_job(
                error_code=ERROR_UNKNOWN,
                error_detail=str(exc),
                retryable=False,
                lease_version=lease_version,
                log=log,
                prior_error_code=_prior_error_code,
                prior_error_repeat=_prior_error_repeat,
            )
            return

        ai_latency_ms = int((time.monotonic() - t_ai_start) * 1000)

        # -------------------------------------------------------------------
        # Validate AI output — security boundary, never bypass
        # -------------------------------------------------------------------
        validator = OfferOutputValidator(known_work_type_codes=known_codes)
        try:
            validated = validator.validate(response.raw_output)
        except OfferValidationError as exc:
            log.warning(
                "offer_runner.validation_failed",
                errors=exc.errors,
                ai_latency_ms=ai_latency_ms,
            )
            async with WorkerAsyncSessionFactory() as session:
                repo = OfferRepository(session)
                await repo.update_agent_run(
                    run_id,
                    status="failed",
                    outcome="validation_error",
                    raw_output=response.raw_output,
                    validation_errors=exc.errors,
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    completed_at=datetime.now(UTC),
                )
                await session.commit()
            # Tokens were consumed even though validation failed
            await self._record_budget(
                actual_tokens, actual_cost, budget_reserved,
                job_id=self._payload.job_id, log=log,
            )
            await self._fail_job(
                error_code=ERROR_VALIDATION_FAILED,
                error_detail="; ".join(exc.errors),
                retryable=False,
                lease_version=lease_version,
                log=log,
                prior_error_code=_prior_error_code,
                prior_error_repeat=_prior_error_repeat,
            )
            return

        # -------------------------------------------------------------------
        # Phase 3: persist result with fencing check
        # -------------------------------------------------------------------
        t_persist = time.monotonic()

        async with WorkerAsyncSessionFactory() as session:
            repo = OfferRepository(session)

            if isinstance(validated, InsufficientDataResult):
                owned = await self._handle_needs_more_info(
                    repo=repo,
                    run_id=run_id,
                    response=response,
                    validated=validated,
                    session=session,
                    lease_version=lease_version,
                )
            else:
                owned = await self._handle_offer_generated(
                    repo=repo,
                    run_id=run_id,
                    response=response,
                    validated=validated,
                    session=session,
                    lease_version=lease_version,
                )

            if not owned:
                log.error(
                    "offer_runner.fencing_violation",
                    lease_version=lease_version,
                    hint="lease expired and was taken by another worker",
                )
                await self._record_budget(
                    actual_tokens, actual_cost, budget_reserved,
                    job_id=self._payload.job_id, log=log,
                )
                return

            budget = BudgetService(session)
            await budget.record_actual(
                self._payload.organization_id,
                job_id=self._payload.job_id,
                estimated_tokens=DEFAULT_TOKEN_ESTIMATE,
                actual_tokens=actual_tokens,
                cost_usd=actual_cost,
            )
            budget_reserved = False
            await session.commit()

        persist_latency_ms = int((time.monotonic() - t_persist) * 1000)
        total_job_ms = int(time.monotonic() * 1000) - self._job_start_ms

        await ack_offer_job(
            self._redis,
            lease_token=self._dequeued.lease_token,
            worker_id=self._worker_id,
        )

        log.info(
            "offer_runner.job_completed",
            total_tokens=actual_tokens,
            cost_usd=str(actual_cost),
            ai_latency_ms=ai_latency_ms,
            persist_latency_ms=persist_latency_ms,
            total_job_ms=total_job_ms,
        )

    # -----------------------------------------------------------------------
    # Persist helpers
    # -----------------------------------------------------------------------

    async def _handle_needs_more_info(
        self, *, repo, run_id, response, validated, session, lease_version
    ) -> bool:
        now = datetime.now(UTC)
        await repo.update_agent_run(
            run_id,
            status=JOB_STATUS_COMPLETED,
            outcome=AGENT_OUTCOME_INSUFFICIENT_DATA,
            raw_output=response.raw_output,
            parsed_output={"questions": validated.questions},
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            estimated_cost_usd=float(estimate_cost_usd(
                response.prompt_tokens + response.completion_tokens
            )),
            started_at=self._dequeued.leased_at,
            completed_at=now,
        )
        owned = await repo.update_job_status_fenced(
            self._payload.job_id,
            expected_lease_version=lease_version,
            status=JOB_STATUS_COMPLETED,
            completed_at=now,
        )
        if not owned:
            return False
        await repo.update_offer_status(
            self._payload.offer_request_id,
            new_status=OFFER_STATUS_NEEDS_MORE_INFO,
            needs_more_info_payload={"questions": validated.questions},
        )
        session.add(
            build_offer_status_changed_event(
                offer_request_id=self._payload.offer_request_id,
                organization_id=self._payload.organization_id,
                job_id=self._payload.job_id,
                status=OFFER_STATUS_NEEDS_MORE_INFO,
                extra={"questions": validated.questions},
            )
        )
        return True

    async def _handle_offer_generated(
        self, *, repo, run_id, response, validated, session, lease_version
    ) -> bool:
        now = datetime.now(UTC)
        await repo.update_agent_run(
            run_id,
            status=JOB_STATUS_COMPLETED,
            outcome=AGENT_OUTCOME_OFFER_GENERATED,
            raw_output=response.raw_output,
            parsed_output={
                "measurements": [
                    item.model_dump(mode="json") for item in validated.measurements
                ],
                "overall_confidence": validated.overall_confidence,
                "warnings": validated.warnings,
                # Prices are computed downstream by the catalog pricing engine.
                "pricing_status": "pending",
            },
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            estimated_cost_usd=float(estimate_cost_usd(
                response.prompt_tokens + response.completion_tokens
            )),
            started_at=self._dequeued.leased_at,
            completed_at=now,
        )
        owned = await repo.update_job_status_fenced(
            self._payload.job_id,
            expected_lease_version=lease_version,
            status=JOB_STATUS_COMPLETED,
            completed_at=now,
        )
        if not owned:
            return False
        await repo.update_offer_status(
            self._payload.offer_request_id,
            new_status=OFFER_STATUS_NEEDS_REVIEW,
            result_ready_at=now,
        )
        session.add(
            build_offer_status_changed_event(
                offer_request_id=self._payload.offer_request_id,
                organization_id=self._payload.organization_id,
                job_id=self._payload.job_id,
                status=OFFER_STATUS_NEEDS_REVIEW,
            )
        )
        return True

    # -----------------------------------------------------------------------
    # Budget helpers — all idempotent, safe to call in finally blocks
    # -----------------------------------------------------------------------

    async def _release_budget(self, budget_reserved: bool, *, log) -> None:
        if not budget_reserved:
            return
        try:
            async with WorkerAsyncSessionFactory() as session:
                budget = BudgetService(session)
                await budget.release(
                    self._payload.organization_id,
                    job_id=self._payload.job_id,
                )
                await session.commit()
        except Exception:
            log.exception("offer_runner.budget_release_failed")

    async def _record_budget(
        self,
        actual_tokens: int,
        actual_cost: Decimal,
        budget_reserved: bool,
        *,
        job_id: str,
        log,
    ) -> None:
        if not budget_reserved:
            return
        try:
            async with WorkerAsyncSessionFactory() as session:
                budget = BudgetService(session)
                await budget.record_actual(
                    self._payload.organization_id,
                    job_id=job_id,
                    estimated_tokens=DEFAULT_TOKEN_ESTIMATE,
                    actual_tokens=actual_tokens,
                    cost_usd=actual_cost,
                )
                await session.commit()
        except Exception:
            log.exception("offer_runner.budget_record_failed")

    # -----------------------------------------------------------------------
    # Failure helper
    # -----------------------------------------------------------------------

    async def _fail_job(
        self,
        *,
        error_code: str,
        error_detail: str,
        retryable: bool,
        lease_version: int,
        log,
        # Passed from Phase 1 cache to avoid re-fetching the job row
        prior_error_code: str | None = None,
        prior_error_repeat: int = 0,
    ) -> None:
        attempt = self._payload.attempt

        async with WorkerAsyncSessionFactory() as session:
            repo = OfferRepository(session)

            # Only fetch if caller didn't pass Phase 1 cache
            if prior_error_code is None:
                job = await repo.get_offer_job(self._payload.job_id)
                max_retries = job.max_retries if job else 3
                retry_count = (job.retry_count or 0) + 1 if job else 1
                prior_error_code = job.last_error_code if job else None
                prior_error_repeat = job.error_repeat_count if job else 0
            else:
                job = await repo.get_offer_job(self._payload.job_id)
                max_retries = job.max_retries if job else 3
                retry_count = (job.retry_count or 0) + 1 if job else 1

            # Compute consecutive same-error count for poison detection
            new_error_repeat = (
                prior_error_repeat + 1
                if prior_error_code == error_code
                else 1
            )

            # Poison detection: same retryable error repeated >= POISON_THRESHOLD
            is_poison = retryable and new_error_repeat >= POISON_THRESHOLD
            if is_poison:
                retryable = False
                error_detail = (
                    f"[POISON:{new_error_repeat}x {error_code}] {error_detail}"
                )
                log.error(
                    "offer_runner.poison_job_detected",
                    error_code=error_code,
                    error_repeat_count=new_error_repeat,
                    poison_threshold=POISON_THRESHOLD,
                )

            if retryable and retry_count < max_retries:
                delay_s = RETRY_BACKOFF_SECONDS[
                    min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)
                ]
                next_retry_at = datetime.now(UTC) + timedelta(seconds=delay_s)
                owned = await repo.update_job_status_fenced(
                    self._payload.job_id,
                    expected_lease_version=lease_version,
                    status=OFFER_STATUS_QUEUED,
                    last_error_code=error_code,
                    last_error_detail=error_detail[:1000],
                    retry_count=retry_count,
                    error_repeat_count=new_error_repeat,
                    next_retry_at=next_retry_at,
                )
                if owned:
                    await repo.update_offer_status(
                        self._payload.offer_request_id,
                        new_status=OFFER_STATUS_QUEUED,
                    )
                log.warning(
                    "offer_runner.job_will_retry",
                    error_code=error_code,
                    retry_in_s=delay_s,
                    retry_count=retry_count,
                    error_repeat_count=new_error_repeat,
                    lease_owned=owned,
                )
            else:
                owned = await repo.update_job_status_fenced(
                    self._payload.job_id,
                    expected_lease_version=lease_version,
                    status=JOB_STATUS_FAILED,
                    last_error_code=error_code,
                    last_error_detail=error_detail[:1000],
                    retry_count=retry_count,
                    error_repeat_count=new_error_repeat,
                )
                if owned:
                    await repo.update_offer_status(
                        self._payload.offer_request_id,
                        new_status=OFFER_STATUS_FAILED,
                    )
                    session.add(
                        build_offer_status_changed_event(
                            offer_request_id=self._payload.offer_request_id,
                            organization_id=self._payload.organization_id,
                            job_id=self._payload.job_id,
                            status=OFFER_STATUS_FAILED,
                            extra={
                                "error_code": error_code,
                                "poison": is_poison,
                                "error_repeat_count": new_error_repeat,
                            },
                        )
                    )
                log.error(
                    "offer_runner.job_failed_permanently",
                    error_code=error_code,
                    retry_count=retry_count,
                    max_retries=max_retries,
                    error_repeat_count=new_error_repeat,
                    is_poison=is_poison,
                    lease_owned=owned,
                    total_job_ms=int(time.monotonic() * 1000) - self._job_start_ms,
                )
            await session.commit()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def run_offer_worker(
    *,
    worker_id: str,
    redis,
    agent_runtime: AgentRuntime,
    poll_interval_s: float = _POLL_INTERVAL_S,
) -> None:
    log = logger.bind(worker_id=worker_id, state=_WorkerState.STARTING)
    log.info("offer_worker.state_change", state=_WorkerState.STARTING)

    # Keep object references so we can call .stop() for cooperative drain
    outbox_publisher = OutboxPublisher(session_factory=WorkerAsyncSessionFactory, redis=redis)
    outbox_task = asyncio.create_task(outbox_publisher.start())

    sweeper = BudgetSweeper(session_factory=WorkerAsyncSessionFactory)
    sweeper_task = asyncio.create_task(sweeper.start())

    reconciler = OfferReconciler(session_factory=WorkerAsyncSessionFactory, redis=redis)
    reconciler_task = asyncio.create_task(reconciler.start())

    bg_tasks = (outbox_task, sweeper_task, reconciler_task)
    bg_services = (outbox_publisher, sweeper, reconciler)

    log = log.bind(state=_WorkerState.HEALTHY)
    log.info("offer_worker.state_change", state=_WorkerState.HEALTHY)

    try:
        while True:
            try:
                dequeued = await dequeue_offer_job(redis, worker_id=worker_id)
            except Exception as exc:
                log.error("offer_worker.dequeue_error", error=str(exc))
                await asyncio.sleep(poll_interval_s)
                continue

            if dequeued is None:
                await asyncio.sleep(poll_interval_s)
                continue

            processor = OfferJobProcessor(
                dequeued=dequeued,
                worker_id=worker_id,
                agent_runtime=agent_runtime,
                redis=redis,
            )
            try:
                await processor.run()
            except Exception as exc:
                log.exception(
                    "offer_worker.unhandled_error",
                    job_id=dequeued.payload.job_id,
                    error=str(exc),
                )

    except asyncio.CancelledError:
        log = log.bind(state=_WorkerState.DRAINING)
        log.info("offer_worker.state_change", state=_WorkerState.DRAINING)

        # Cooperative stop: signal each loop to exit after its current iteration
        for svc in bg_services:
            svc.stop()

        # Wait up to _DRAIN_TIMEOUT_S for all loops to finish gracefully
        done, pending = await asyncio.wait(list(bg_tasks), timeout=_DRAIN_TIMEOUT_S)

        log = log.bind(state=_WorkerState.SHUTTING_DOWN)
        log.info(
            "offer_worker.state_change",
            state=_WorkerState.SHUTTING_DOWN,
            drained=len(done),
            force_cancelled=len(pending),
        )

        # Hard-cancel any task that didn't drain in time
        for task in pending:
            task.cancel()

        raise


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_file, settings.log_error_file)

    if not settings.redis_url:
        print(
            startup_failure_message("redis", "REDIS_URL is required for offer worker."),
            file=sys.stderr,
        )
        sys.exit(1)

    worker_id = f"offer-worker-{secrets.token_hex(6)}"
    provider_key = getattr(settings, "ai_offer_provider", "mock")
    agent_runtime = build_agent_runtime(provider_key, settings)

    async def _run():
        redis = build_queue_redis_client_from_settings(
            settings, client_name=worker_id
        )
        try:
            await run_offer_worker(
                worker_id=worker_id,
                redis=redis,
                agent_runtime=agent_runtime,
            )
        finally:
            await redis.aclose()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
