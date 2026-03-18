import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class PolygonPoint(BaseModel):
    x: float
    y: float


class AnalysisResultRead(BaseModel):
    id: str
    projectId: str
    analysisJobId: str | None = None
    referencePhotoId: str | None = None
    objectType: str | None = None
    surfaceCondition: str | None = None
    recommendedScope: str | None = None
    estimatedAreaSqm: float | None = None
    areaConfidence: float | None = None
    selectedRepairPolygon: list[PolygonPoint] | None = None
    manualAreaSqm: float | None = None
    finalAreaSource: str
    maskPolygon: list[dict[str, float]] | None = None
    materials: list[dict[str, Any]] | None = None
    workflow: list[str] | None = None
    modelName: str | None = None
    modelVersion: str | None = None
    createdAt: datetime | None = None


class AnalysisTriggerResponse(BaseModel):
    jobId: str
    status: str
    provider: str | None = None
    modelName: str | None = None
    modelVersion: str | None = None


class AnalysisPatch(BaseModel):
    referencePhotoId: str | None = None
    selectedRepairPolygon: list[PolygonPoint] | None = None
    manualAreaSqm: float | None = Field(default=None, gt=0)
    finalAreaSource: Literal["ai", "manual"] | None = None

    @field_validator("selectedRepairPolygon")
    @classmethod
    def validate_polygon(cls, value: list[PolygonPoint] | None):
        if value is not None and len(value) < 3:
            raise ValueError("selectedRepairPolygon must contain at least 3 points.")
        return value


def parse_json_field(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None
