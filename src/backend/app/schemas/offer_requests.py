"""Pydantic schemas for the offer-request API surface.

Qt desktop client additive contract:
    - Never remove or rename response fields
    - Never change field semantics
    - Only add new optional fields
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class OfferRequestCreate(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    work_type_code: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    parameters: dict[str, Any] = Field(default_factory=dict)
    photo_ids: list[str] = Field(default_factory=list)
    client_id: str | None = None
    auto_send: bool = False
    auto_review_bypass: bool = False
    client_version: str | None = None

    @field_validator("idempotency_key")
    @classmethod
    def _strip_idempotency_key(cls, v: str) -> str:
        return v.strip()

    @field_validator("work_type_code")
    @classmethod
    def _strip_work_type_code(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("work_type_code must not be empty")
        return v


class MoreInfoSubmit(BaseModel):
    additional_parameters: dict[str, Any] = Field(default_factory=dict)
    additional_photo_ids: list[str] = Field(default_factory=list)


class OfferApprove(BaseModel):
    action: str = Field(..., pattern="^approve$")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class OfferRequestRead(BaseModel):
    id: str
    organization_id: str
    work_type_code: str
    title: str
    status: str
    parameters: dict[str, Any]
    photo_ids: list[str]
    client_id: str | None
    auto_send: bool
    auto_review_bypass: bool
    needs_more_info_payload: dict[str, Any] | None
    result_ready_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    client_version: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OfferStatusRead(BaseModel):
    id: str
    status: str
    needs_more_info_payload: dict[str, Any] | None
    result_ready_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class OfferResultRead(BaseModel):
    id: str
    status: str
    work_type_code: str
    title: str
    parameters: dict[str, Any]
    result_ready_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class OfferSubmitResponse(BaseModel):
    id: str
    status: str
    created: bool = Field(
        ...,
        description="True if a new offer was created (201), False if idempotent replay (200).",
    )
