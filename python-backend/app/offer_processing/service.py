"""Offer processing service — business logic and state machine.

Entry points:
    submit_offer_request()   — called by POST /offer-requests
    cancel_offer_request()   — called by POST /offer-requests/:id/cancel
    get_offer_status()       — called by GET /offer-requests/:id/status
    get_offer_result()       — called by GET /offer-requests/:id/result
    submit_more_info()       — called by POST /offer-requests/:id/more-info
    approve_offer()          — called by PATCH /offer-requests/:id (operator)
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.offer_processing import OfferRequest
from app.offer_processing.domain import (
    OFFER_STATUS_CANCELLED,
    OFFER_STATUS_COMPLETED,
    OFFER_STATUS_NEEDS_MORE_INFO,
    OFFER_STATUS_NEEDS_REVIEW,
    OFFER_STATUS_QUEUED,
    OFFER_TERMINAL_STATUSES,
    require_offer_transition,
)
from app.offer_processing.outbox import build_offer_status_changed_event
from app.offer_processing.repository import OfferRepository

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class OfferNotFoundError(LookupError):
    pass


class OfferAlreadyExistsError(Exception):
    """Raised on idempotent re-submission — caller returns existing state."""
    def __init__(self, existing: OfferRequest) -> None:
        super().__init__(f"Offer request {existing.id} already exists.")
        self.existing = existing


class OfferLockedError(Exception):
    """Operation rejected because the offer is in a locked status."""
    pass


class OfferTerminalError(Exception):
    """Operation rejected because the offer is in a terminal status."""
    pass


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OfferService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = OfferRepository(session)

    # -----------------------------------------------------------------------
    # Submit (idempotent)
    # -----------------------------------------------------------------------

    async def submit_offer_request(
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
        """Create a new offer request (idempotent by idempotency_key + org).

        If the same idempotency_key already exists for this org, raises
        OfferAlreadyExistsError with the existing offer — caller returns 200.
        """
        existing = await self._repo.get_offer_request_by_idempotency_key(
            idempotency_key, organization_id=organization_id
        )
        if existing is not None:
            raise OfferAlreadyExistsError(existing)

        offer = await self._repo.create_offer_request(
            organization_id=organization_id,
            submitted_by_user_id=submitted_by_user_id,
            idempotency_key=idempotency_key,
            work_type_code=work_type_code,
            title=title,
            parameters=parameters,
            photo_ids=photo_ids,
            client_id=client_id,
            auto_send=auto_send,
            auto_review_bypass=auto_review_bypass,
            client_version=client_version,
        )

        # Create the initial job
        job_idempotency = f"{idempotency_key}:attempt:1"
        job = await self._repo.create_offer_job(
            offer_request_id=offer.id,
            organization_id=organization_id,
            idempotency_key=job_idempotency,
        )

        # Transition to queued + write outbox event (same transaction)
        await self._repo.update_offer_status(offer.id, new_status=OFFER_STATUS_QUEUED)
        self._session.add(
            build_offer_status_changed_event(
                offer_request_id=offer.id,
                organization_id=organization_id,
                job_id=job.id,
                status=OFFER_STATUS_QUEUED,
            )
        )

        logger.info(
            "offer.submitted",
            offer_request_id=offer.id,
            job_id=job.id,
            organization_id=organization_id,
            work_type_code=work_type_code,
        )

        await self._session.flush()
        return offer

    # -----------------------------------------------------------------------
    # Status + Result
    # -----------------------------------------------------------------------

    async def get_offer_request(
        self, offer_request_id: str, *, organization_id: str
    ) -> OfferRequest:
        offer = await self._repo.get_offer_request(offer_request_id, organization_id=organization_id)
        if offer is None:
            raise OfferNotFoundError(offer_request_id)
        return offer

    async def get_offer_result(
        self, offer_request_id: str, *, organization_id: str
    ) -> OfferRequest:
        offer = await self.get_offer_request(offer_request_id, organization_id=organization_id)
        if offer.status not in {OFFER_STATUS_NEEDS_REVIEW, OFFER_STATUS_COMPLETED}:
            raise OfferLockedError(
                f"Result not available in status '{offer.status}'. "
                "Wait for needs_review or completed."
            )
        return offer

    # -----------------------------------------------------------------------
    # Cancel
    # -----------------------------------------------------------------------

    async def cancel_offer_request(
        self,
        offer_request_id: str,
        *,
        organization_id: str,
        cancelled_by_user_id: str,
    ) -> OfferRequest:
        offer = await self.get_offer_request(offer_request_id, organization_id=organization_id)

        if offer.status in OFFER_TERMINAL_STATUSES:
            raise OfferTerminalError(
                f"Cannot cancel offer in terminal status '{offer.status}'."
            )

        require_offer_transition(offer.status, OFFER_STATUS_CANCELLED)

        now = datetime.now(UTC)
        await self._repo.update_offer_status(
            offer_request_id,
            new_status=OFFER_STATUS_CANCELLED,
            cancelled_at=now,
            cancelled_by_user_id=cancelled_by_user_id,
        )

        job = await self._repo.get_latest_job_for_request(offer_request_id)
        self._session.add(
            build_offer_status_changed_event(
                offer_request_id=offer_request_id,
                organization_id=organization_id,
                job_id=job.id if job else None,
                status=OFFER_STATUS_CANCELLED,
            )
        )
        return offer

    # -----------------------------------------------------------------------
    # Approve (operator action, or auto_review_bypass)
    # -----------------------------------------------------------------------

    async def approve_offer(
        self,
        offer_request_id: str,
        *,
        organization_id: str,
        approved_by_user_id: str,
    ) -> OfferRequest:
        offer = await self.get_offer_request(offer_request_id, organization_id=organization_id)
        require_offer_transition(offer.status, OFFER_STATUS_COMPLETED)

        now = datetime.now(UTC)
        await self._repo.update_offer_status(
            offer_request_id,
            new_status=OFFER_STATUS_COMPLETED,
            completed_at=now,
        )
        job = await self._repo.get_latest_job_for_request(offer_request_id)
        self._session.add(
            build_offer_status_changed_event(
                offer_request_id=offer_request_id,
                organization_id=organization_id,
                job_id=job.id if job else None,
                status=OFFER_STATUS_COMPLETED,
                extra={"approved_by_user_id": approved_by_user_id},
            )
        )
        return offer

    # -----------------------------------------------------------------------
    # More info submission
    # -----------------------------------------------------------------------

    async def submit_more_info(
        self,
        offer_request_id: str,
        *,
        organization_id: str,
        additional_parameters: dict,
        additional_photo_ids: list[str],
    ) -> tuple[OfferRequest, str]:
        """Accept additional data from Qt and requeue for processing.

        Returns (updated_offer, new_job_id).
        """
        offer = await self.get_offer_request(offer_request_id, organization_id=organization_id)

        if offer.status != OFFER_STATUS_NEEDS_MORE_INFO:
            raise OfferLockedError(
                f"more-info accepted only in needs_more_info status, got '{offer.status}'."
            )

        # Merge new parameters into existing
        merged_params = {**(offer.parameters or {}), **additional_parameters}
        merged_photos = list({*(offer.photo_ids or []), *additional_photo_ids})

        # Determine next attempt number
        existing_job = await self._repo.get_latest_job_for_request(offer_request_id)
        next_attempt = (existing_job.attempt + 1) if existing_job else 2

        job_idempotency = f"{offer.idempotency_key}:attempt:{next_attempt}"
        new_job = await self._repo.create_offer_job(
            offer_request_id=offer_request_id,
            organization_id=organization_id,
            idempotency_key=job_idempotency,
            attempt=next_attempt,
        )

        # Update offer with merged data + transition back to queued
        from sqlalchemy import update  # noqa: PLC0415
        from app.models.offer_processing import OfferRequest as _OR  # noqa: PLC0415
        await self._session.execute(
            update(_OR)
            .where(_OR.id == offer_request_id)
            .values(
                parameters=merged_params,
                photo_ids=merged_photos,
                status=OFFER_STATUS_QUEUED,
                needs_more_info_payload=None,
                updated_at=datetime.now(UTC),
            )
        )

        self._session.add(
            build_offer_status_changed_event(
                offer_request_id=offer_request_id,
                organization_id=organization_id,
                job_id=new_job.id,
                status=OFFER_STATUS_QUEUED,
                extra={"requeued_attempt": next_attempt},
            )
        )

        await self._session.flush()
        return offer, new_job.id
