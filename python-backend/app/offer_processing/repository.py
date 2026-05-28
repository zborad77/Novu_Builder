"""Offer processing repository — all DB operations for the offer pipeline.

Follows the same session-injection pattern as the rest of the codebase.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Sequence
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.offer_processing import AgentRun, OfferJob, OfferRequest
from app.offer_processing.domain import (
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    OFFER_STATUS_QUEUED,
    OFFER_STATUS_SUBMITTED,
)


class OfferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # OfferRequest
    # -----------------------------------------------------------------------

    async def create_offer_request(
        self,
        *,
        organization_id: str,
        submitted_by_user_id: str,
        idempotency_key: str,
        work_type_code: str,
        title: str,
        parameters: dict,
        photo_ids: list[str],
        client_id: str | None = None,
        auto_send: bool = False,
        auto_review_bypass: bool = False,
        client_version: str | None = None,
    ) -> OfferRequest:
        offer = OfferRequest(
            id=str(uuid4()),
            organization_id=organization_id,
            submitted_by_user_id=submitted_by_user_id,
            idempotency_key=idempotency_key,
            work_type_code=work_type_code,
            title=title,
            parameters=parameters,
            photo_ids=photo_ids,
            client_id=client_id,
            status=OFFER_STATUS_SUBMITTED,
            auto_send=auto_send,
            auto_review_bypass=auto_review_bypass,
            client_version=client_version,
        )
        self._session.add(offer)
        return offer

    async def get_offer_request(
        self, offer_request_id: str, *, organization_id: str
    ) -> OfferRequest | None:
        result = await self._session.execute(
            select(OfferRequest).where(
                OfferRequest.id == offer_request_id,
                OfferRequest.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_offer_request_by_idempotency_key(
        self, idempotency_key: str, *, organization_id: str
    ) -> OfferRequest | None:
        result = await self._session.execute(
            select(OfferRequest).where(
                OfferRequest.idempotency_key == idempotency_key,
                OfferRequest.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_offer_requests(
        self, *, organization_id: str, limit: int = 100
    ) -> Sequence[OfferRequest]:
        result = await self._session.execute(
            select(OfferRequest)
            .where(OfferRequest.organization_id == organization_id)
            .order_by(OfferRequest.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def update_offer_status(
        self,
        offer_request_id: str,
        *,
        new_status: str,
        needs_more_info_payload: dict | None = None,
        result_ready_at: datetime | None = None,
        completed_at: datetime | None = None,
        cancelled_at: datetime | None = None,
        cancelled_by_user_id: str | None = None,
    ) -> None:
        values: dict = {"status": new_status, "updated_at": datetime.now(UTC)}
        if needs_more_info_payload is not None:
            values["needs_more_info_payload"] = needs_more_info_payload
        if result_ready_at is not None:
            values["result_ready_at"] = result_ready_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        if cancelled_at is not None:
            values["cancelled_at"] = cancelled_at
        if cancelled_by_user_id is not None:
            values["cancelled_by_user_id"] = cancelled_by_user_id
        await self._session.execute(
            update(OfferRequest)
            .where(OfferRequest.id == offer_request_id)
            .values(**values)
        )

    # -----------------------------------------------------------------------
    # OfferJob
    # -----------------------------------------------------------------------

    async def create_offer_job(
        self,
        *,
        offer_request_id: str,
        organization_id: str,
        idempotency_key: str,
        attempt: int = 1,
        max_retries: int = 3,
    ) -> OfferJob:
        job = OfferJob(
            id=str(uuid4()),
            offer_request_id=offer_request_id,
            organization_id=organization_id,
            idempotency_key=idempotency_key,
            status=JOB_STATUS_QUEUED,
            attempt=attempt,
            max_retries=max_retries,
        )
        self._session.add(job)
        return job

    async def get_offer_job(self, job_id: str) -> OfferJob | None:
        result = await self._session.execute(
            select(OfferJob).where(OfferJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_job_for_request(
        self, offer_request_id: str
    ) -> OfferJob | None:
        result = await self._session.execute(
            select(OfferJob)
            .where(OfferJob.offer_request_id == offer_request_id)
            .order_by(OfferJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_job_running(
        self, job_id: str, *, worker_id: str, leased_until: datetime
    ) -> int:
        """Mark job as running and increment the lease fencing token.

        Returns the new lease_version. The caller must pass this value to
        persist_job_result() so stale workers are detected and aborted.
        """
        result = await self._session.execute(
            update(OfferJob)
            .where(OfferJob.id == job_id)
            .values(
                status=JOB_STATUS_RUNNING,
                worker_id=worker_id,
                leased_until=leased_until,
                lease_version=OfferJob.lease_version + 1,
                started_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            .returning(OfferJob.lease_version)
        )
        row = result.fetchone()
        return row[0] if row else 1

    async def update_job_status_fenced(
        self,
        job_id: str,
        *,
        expected_lease_version: int,
        status: str,
        last_error_code: str | None = None,
        last_error_detail: str | None = None,
        retry_count: int | None = None,
        error_repeat_count: int | None = None,
        next_retry_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> bool:
        """Update job status only if lease_version matches.

        Returns True if the row was updated (this worker still owns the lease).
        Returns False if a different worker has taken over (fencing violation).
        """
        values: dict = {"status": status, "updated_at": datetime.now(UTC)}
        if last_error_code is not None:
            values["last_error_code"] = last_error_code
        if last_error_detail is not None:
            values["last_error_detail"] = last_error_detail
        if retry_count is not None:
            values["retry_count"] = retry_count
        if error_repeat_count is not None:
            values["error_repeat_count"] = error_repeat_count
        if next_retry_at is not None:
            values["next_retry_at"] = next_retry_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        result = await self._session.execute(
            update(OfferJob)
            .where(
                OfferJob.id == job_id,
                OfferJob.lease_version == expected_lease_version,
            )
            .values(**values)
        )
        return result.rowcount > 0

    async def update_job_status(
        self,
        job_id: str,
        *,
        status: str,
        last_error_code: str | None = None,
        last_error_detail: str | None = None,
        retry_count: int | None = None,
        next_retry_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        values: dict = {"status": status, "updated_at": datetime.now(UTC)}
        if last_error_code is not None:
            values["last_error_code"] = last_error_code
        if last_error_detail is not None:
            values["last_error_detail"] = last_error_detail
        if retry_count is not None:
            values["retry_count"] = retry_count
        if next_retry_at is not None:
            values["next_retry_at"] = next_retry_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        await self._session.execute(
            update(OfferJob).where(OfferJob.id == job_id).values(**values)
        )

    # -----------------------------------------------------------------------
    # AgentRun
    # -----------------------------------------------------------------------

    async def create_agent_run(
        self,
        *,
        offer_job_id: str,
        offer_request_id: str,
        organization_id: str,
        provider_key: str,
        input_snapshot_key: str | None = None,
        input_snapshot_hash: str | None = None,
        snapshot_version_context: dict | None = None,
        agent_model: str | None = None,
        agent_model_build: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            id=str(uuid4()),
            offer_job_id=offer_job_id,
            offer_request_id=offer_request_id,
            organization_id=organization_id,
            provider_key=provider_key,
            input_snapshot_key=input_snapshot_key,
            input_snapshot_hash=input_snapshot_hash,
            snapshot_version_context=snapshot_version_context,
            agent_model=agent_model,
            agent_model_build=agent_model_build,
        )
        self._session.add(run)
        return run

    async def update_agent_run(
        self,
        run_id: str,
        *,
        status: str,
        outcome: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        estimated_cost_usd=None,
        raw_output: dict | None = None,
        parsed_output: dict | None = None,
        validation_errors: list | None = None,
        error_detail: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        values: dict = {"status": status}
        for field, val in [
            ("outcome", outcome),
            ("prompt_tokens", prompt_tokens),
            ("completion_tokens", completion_tokens),
            ("estimated_cost_usd", estimated_cost_usd),
            ("raw_output", raw_output),
            ("parsed_output", parsed_output),
            ("validation_errors", validation_errors),
            ("error_detail", error_detail),
            ("started_at", started_at),
            ("completed_at", completed_at),
        ]:
            if val is not None:
                values[field] = val
        await self._session.execute(
            update(AgentRun).where(AgentRun.id == run_id).values(**values)
        )
