import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class PolygonPoint(BaseModel):
    x: float
    y: float


class AiWorkTypeSuggestionRead(BaseModel):
    workTypeCode: str | None = None
    confidence: float = 0
    isUsable: bool
    objectType: str | None = None
    recommendedScope: str | None = None
    sourceAnalysisId: str
    reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AnalysisResultRead(BaseModel):
    id: str
    projectId: str
    analysisJobId: str | None = None
    workTypeCode: str | None = None
    analysisProfileCode: str | None = None
    analysisProfileVersion: int | None = None
    referencePhotoId: str | None = None
    objectType: str | None = None
    surfaceCondition: str | None = None
    recommendedScope: str | None = None
    estimatedQuantity: float | None = None
    estimatedUnit: str | None = None
    estimatedAreaSqm: float | None = None
    areaConfidence: float | None = None
    selectedRepairPolygon: list[PolygonPoint] | None = None
    manualAreaSqm: float | None = None
    finalAreaSource: str
    maskPolygon: list[dict[str, float]] | None = None
    materials: list[dict[str, Any]] | None = None
    workflowSteps: list[dict[str, Any]] | None = None
    estimatedDurationDays: float | None = None
    laborHoursTotal: float | None = None
    modelName: str | None = None
    modelVersion: str | None = None
    aiWorkTypeSuggestion: AiWorkTypeSuggestionRead | None = None
    createdAt: datetime | None = None


class AnalysisTriggerResponse(BaseModel):
    jobId: str
    status: str
    workTypeCode: str | None = None
    analysisProfileCode: str | None = None
    analysisProfileVersion: int | None = None
    provider: str | None = None
    modelName: str | None = None
    modelVersion: str | None = None


class AnalysisJobCreateRequest(BaseModel):
    workTypeCode: str | None = None


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
