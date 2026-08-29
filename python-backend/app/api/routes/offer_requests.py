"""REST endpoints for the offer-request pipeline.

Consumed by Qt desktop client — additive-only API contract.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_org_id
from app.db.session import get_db_session
from app.offer_processing.domain import InvalidOfferTransitionError
from app.offer_processing.service import (
    OfferAlreadyExistsError,
    OfferLockedError,
    OfferNotFoundError,
    OfferService,
    OfferTerminalError,
)
from app.schemas.auth import AuthUserRead
from app.schemas.offer_requests import (
    MoreInfoSubmit,
    OfferApprove,
    OfferRequestCreate,
    OfferRequestRead,
    OfferResultRead,
    OfferStatusRead,
    OfferSubmitResponse,
)

router = APIRouter(prefix="/offer-requests", tags=["offer-requests"])


# ---------------------------------------------------------------------------
# Service dependency
# ---------------------------------------------------------------------------


def get_offer_service(session: AsyncSession = Depends(get_db_session)) -> OfferService:
    return OfferService(session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _not_found(offer_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Offer request '{offer_id}' not found.")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=409, detail=detail)


def _locked(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    summary="Submit a new offer request (idempotent by idempotency_key)",
    status_code=status.HTTP_201_CREATED,
)
async def submit_offer_request(
    payload: OfferRequestCreate,
    response: Response,
    current_user: AuthUserRead = Depends(get_current_user),
    offer_svc: OfferService = Depends(get_offer_service),
) -> OfferSubmitResponse:
    org_id = require_org_id(current_user)
    try:
        offer = await offer_svc.submit_offer_request(
            organization_id=org_id,
            submitted_by_user_id=current_user.id,
            idempotency_key=payload.idempotency_key,
            work_type_code=payload.work_type_code,
            title=payload.title,
            parameters=payload.parameters,
            photo_ids=payload.photo_ids,
            client_id=payload.client_id,
            auto_send=payload.auto_send,
            auto_review_bypass=payload.auto_review_bypass,
            client_version=payload.client_version,
        )
        return OfferSubmitResponse(id=offer.id, status=offer.status, created=True)
    except OfferAlreadyExistsError as exc:
        # Idempotent replay — downgrade to 200
        existing = exc.existing
        response.status_code = status.HTTP_200_OK
        return OfferSubmitResponse(id=existing.id, status=existing.status, created=False)


@router.get(
    "/{offer_id}",
    response_model=OfferRequestRead,
    summary="Get full offer request detail",
)
async def get_offer_request(
    offer_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    offer_svc: OfferService = Depends(get_offer_service),
) -> OfferRequestRead:
    org_id = require_org_id(current_user)
    try:
        offer = await offer_svc.get_offer_request(offer_id, organization_id=org_id)
    except OfferNotFoundError:
        raise _not_found(offer_id)
    return OfferRequestRead.model_validate(offer)


@router.get(
    "/{offer_id}/status",
    response_model=OfferStatusRead,
    summary="Lightweight status polling (preferred for Qt polling loop)",
)
async def get_offer_status(
    offer_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    offer_svc: OfferService = Depends(get_offer_service),
) -> OfferStatusRead:
    org_id = require_org_id(current_user)
    try:
        offer = await offer_svc.get_offer_request(offer_id, organization_id=org_id)
    except OfferNotFoundError:
        raise _not_found(offer_id)
    return OfferStatusRead.model_validate(offer)


@router.get(
    "/{offer_id}/result",
    response_model=OfferResultRead,
    summary="Retrieve AI-generated offer result (only available in needs_review or completed)",
)
async def get_offer_result(
    offer_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    offer_svc: OfferService = Depends(get_offer_service),
) -> OfferResultRead:
    org_id = require_org_id(current_user)
    try:
        offer = await offer_svc.get_offer_result(offer_id, organization_id=org_id)
    except OfferNotFoundError:
        raise _not_found(offer_id)
    except OfferLockedError as exc:
        raise _locked(str(exc))
    return OfferResultRead.model_validate(offer)


@router.post(
    "/{offer_id}/cancel",
    response_model=OfferStatusRead,
    summary="Cancel a non-terminal offer request",
)
async def cancel_offer_request(
    offer_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    offer_svc: OfferService = Depends(get_offer_service),
) -> OfferStatusRead:
    org_id = require_org_id(current_user)
    try:
        offer = await offer_svc.cancel_offer_request(
            offer_id,
            organization_id=org_id,
            cancelled_by_user_id=current_user.id,
        )
    except OfferNotFoundError:
        raise _not_found(offer_id)
    except OfferTerminalError as exc:
        raise _conflict(str(exc))
    except InvalidOfferTransitionError as exc:
        raise _conflict(str(exc))
    return OfferStatusRead.model_validate(offer)


@router.post(
    "/{offer_id}/more-info",
    response_model=OfferStatusRead,
    summary="Submit additional information when AI requested more data",
)
async def submit_more_info(
    offer_id: str,
    payload: MoreInfoSubmit,
    current_user: AuthUserRead = Depends(get_current_user),
    offer_svc: OfferService = Depends(get_offer_service),
) -> OfferStatusRead:
    org_id = require_org_id(current_user)
    try:
        _offer, _new_job_id = await offer_svc.submit_more_info(
            offer_id,
            organization_id=org_id,
            additional_parameters=payload.additional_parameters,
            additional_photo_ids=payload.additional_photo_ids,
        )
    except OfferNotFoundError:
        raise _not_found(offer_id)
    except OfferLockedError as exc:
        raise _locked(str(exc))
    # Re-fetch to get the updated status written by submit_more_info
    updated = await offer_svc.get_offer_request(offer_id, organization_id=org_id)
    return OfferStatusRead.model_validate(updated)


@router.patch(
    "/{offer_id}",
    response_model=OfferStatusRead,
    summary="Operator: approve an offer in needs_review status",
)
async def approve_offer(
    offer_id: str,
    payload: OfferApprove,
    current_user: AuthUserRead = Depends(get_current_user),
    offer_svc: OfferService = Depends(get_offer_service),
) -> OfferStatusRead:
    org_id = require_org_id(current_user)
    try:
        offer = await offer_svc.approve_offer(
            offer_id,
            organization_id=org_id,
            approved_by_user_id=current_user.id,
        )
    except OfferNotFoundError:
        raise _not_found(offer_id)
    except InvalidOfferTransitionError as exc:
        raise _conflict(str(exc))
    return OfferStatusRead.model_validate(offer)
