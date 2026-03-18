from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field, field_validator


class MeasurementPolygonPoint(BaseModel):
    x: float
    y: float


class MeasurementRead(BaseModel):
    id: str
    caseId: str
    referenceImageId: str | None = None
    selectedRepairPolygon: list[MeasurementPolygonPoint] | None = None
    aiAreaSqm: float | None = None
    manualAreaSqm: float | None = None
    finalAreaSource: str
    confirmed: bool
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class MeasurementUpsert(BaseModel):
    referenceImageId: str | None = Field(
        default=None,
        validation_alias=AliasChoices("referenceImageId", "referencePhotoId"),
    )
    selectedRepairPolygon: list[MeasurementPolygonPoint] | None = None
    manualAreaSqm: float | None = Field(default=None, gt=0)
    finalAreaSource: str | None = None

    @field_validator("selectedRepairPolygon")
    @classmethod
    def validate_polygon(cls, value: list[MeasurementPolygonPoint] | None):
        if value is not None and len(value) < 3:
            raise ValueError("selectedRepairPolygon must contain at least 3 points.")
        return value
