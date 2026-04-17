from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MARKER_TYPES = frozenset({"defect", "note", "ai_detection", "measurement"})


class MarkerCreate(BaseModel):
    caseId: str
    imageId: str | None = None
    markerType: Literal["defect", "note", "ai_detection", "measurement"]
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float | None = Field(default=None, ge=0.0, le=1.0)
    height: float | None = Field(default=None, ge=0.0, le=1.0)
    label: str = Field(min_length=1, max_length=512)
    severity: str | None = None

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 32:
            raise ValueError("severity must be 32 characters or fewer")
        return v


class MarkerRead(BaseModel):
    id: str
    caseId: str
    imageId: str | None = None
    markerType: str
    markerSource: str
    x: float
    y: float
    width: float | None = None
    height: float | None = None
    label: str
    severity: str | None = None
    createdBy: str | None = None
    createdAt: datetime


class MarkerListResponse(BaseModel):
    items: list[MarkerRead]


class MarkerDeleteResponse(BaseModel):
    message: str
