from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkTypeParameterOptionRead(BaseModel):
    code: str
    label: str
    sortOrder: int
    isActive: bool


class WorkTypeParameterRead(BaseModel):
    parameterDefinitionId: str
    code: str
    slug: str
    label: str
    effectiveLabel: str
    description: str | None = None
    dataType: str
    unit: str | None = None
    section: str
    sectionLabel: str
    required: bool
    enabled: bool = True
    sortOrder: int
    overrideStatus: str | None = None
    settingVersion: int | None = None
    minNumberValue: float | None = None
    maxNumberValue: float | None = None
    visionExtractable: bool
    manualOverrideAllowed: bool
    defaultTextValue: str | None = None
    defaultNumberValue: float | None = None
    defaultBooleanValue: bool | None = None
    defaultOptionCode: str | None = None
    enumOptions: list[WorkTypeParameterOptionRead] = Field(default_factory=list)


class WorkTypeParameterSectionRead(BaseModel):
    code: str
    label: str
    sortOrder: int
    parameters: list[WorkTypeParameterRead] = Field(default_factory=list)


class AnalysisProfileRead(BaseModel):
    code: str
    name: str
    providerFamily: str
    taskType: str
    outputContractVersion: int
    confidenceThreshold: float | None = None
    maxDetectionsPerPhoto: int
    profileVersion: int


class CatalogPricingProfileRead(BaseModel):
    code: str
    name: str
    pricingStrategy: str
    laborRateSource: str
    materialPricingSource: str
    defaultMarginPct: float | None = None
    defaultMarkupPct: float | None = None
    profileVersion: int


class TenantWorkTypeSettingRead(BaseModel):
    status: str
    customDisplayName: str | None = None
    analysisProfileCode: str | None = None
    catalogPricingProfileCode: str | None = None
    tenantPricingProfileId: str | None = None
    isBillableOverride: bool | None = None
    sortOrderOverride: int | None = None
    configVersion: int | None = None
    updatedAt: datetime | None = None


class TenantWorkTypeParameterOverrideRead(BaseModel):
    parameterCode: str
    overrideStatus: str
    customDisplayName: str | None = None
    sortOrderOverride: int | None = None
    defaultTextValue: str | None = None
    defaultNumberValue: float | None = None
    defaultBooleanValue: bool | None = None
    defaultOptionCode: str | None = None
    configVersion: int | None = None
    updatedAt: datetime | None = None


class WorkCategoryRead(BaseModel):
    code: str
    slug: str
    name: str
    description: str | None = None
    sortOrder: int
    catalogVersion: int


class EffectiveWorkTypeRead(BaseModel):
    code: str
    slug: str
    name: str
    description: str | None = None
    state: str
    isEnabled: bool
    effectiveDisplayName: str
    category: WorkCategoryRead
    defaultUnit: str
    measurementKind: str
    workTypeVersion: int
    settingVersion: int | None = None
    analysisProfile: AnalysisProfileRead | None = None
    catalogPricingProfile: CatalogPricingProfileRead | None = None
    tenantPricingProfileId: str | None = None
    parameters: list[WorkTypeParameterRead] = Field(default_factory=list)
    parameterSections: list[WorkTypeParameterSectionRead] = Field(default_factory=list)
    tenantSetting: TenantWorkTypeSettingRead | None = None
    parameterOverrides: list[TenantWorkTypeParameterOverrideRead] = Field(default_factory=list)


class EffectiveWorkTypeListResponse(BaseModel):
    items: list[EffectiveWorkTypeRead]
    total: int


class TenantWorkTypeSettingUpsert(BaseModel):
    status: str = "enabled"
    customDisplayName: str | None = None
    analysisProfileCode: str | None = None
    catalogPricingProfileCode: str | None = None
    tenantPricingProfileId: str | None = None
    isBillableOverride: bool | None = None
    sortOrderOverride: int | None = None


class TenantWorkTypeParameterOverrideUpsert(BaseModel):
    parameterCode: str
    overrideStatus: str = "inherited"
    customDisplayName: str | None = None
    sortOrderOverride: int | None = None
    defaultTextValue: str | None = None
    defaultNumberValue: float | None = None
    defaultBooleanValue: bool | None = None
    defaultOptionCode: str | None = None


class TenantWorkTypeSettingWithParametersUpsert(TenantWorkTypeSettingUpsert):
    parameterOverrides: list[TenantWorkTypeParameterOverrideUpsert] = Field(default_factory=list)


class ProjectWorkItemValueInput(BaseModel):
    parameterCode: str
    textValue: str | None = None
    numberValue: float | None = None
    booleanValue: bool | None = None
    optionValue: str | None = None
    sourceType: str = "manual"


class ProjectWorkItemCreate(BaseModel):
    workTypeCode: str
    title: str | None = None
    sourceType: str = "manual"
    status: str = "resolved"
    measuredQuantity: float | None = Field(default=None, ge=0)
    measuredUnit: str | None = None
    notes: str | None = None
    values: list[ProjectWorkItemValueInput] = Field(default_factory=list)


class ProjectWorkItemValueRead(BaseModel):
    parameterDefinitionId: str
    parameterCode: str
    parameterSlug: str
    parameterLabel: str
    parameterSection: str | None = None
    dataType: str
    unit: str | None = None
    visionExtractable: bool | None = None
    manualOverrideAllowed: bool | None = None
    textValue: str | None = None
    numberValue: float | None = None
    booleanValue: bool | None = None
    optionValue: str | None = None
    sourceType: str
    updatedAt: datetime | None = None


class VisionDetectionCreate(BaseModel):
    workTypeCode: str
    detectionKey: str
    referencePhotoId: str | None = None
    status: str = "pending"
    confidenceScore: float | None = Field(default=None, ge=0, le=1)
    rawLabel: str | None = None
    rawValue: str | None = None
    detectedQuantity: float | None = Field(default=None, ge=0)
    detectedUnit: str | None = None
    geometryType: str | None = None
    bboxLeft: float | None = None
    bboxTop: float | None = None
    bboxRight: float | None = None
    bboxBottom: float | None = None
    geometry: Any | None = None
    sourceProvider: str | None = None
    sourceModel: str | None = None
    sourceModelVersion: str | None = None
    analysisJobId: str | None = None


class VisionDetectionRead(BaseModel):
    id: str
    detectionKey: str
    workTypeCode: str
    status: str
    referencePhotoId: str | None = None
    confidenceScore: float | None = None
    rawLabel: str | None = None
    rawValue: str | None = None
    detectedQuantity: float | None = None
    detectedUnit: str | None = None
    geometryType: str | None = None
    bboxLeft: float | None = None
    bboxTop: float | None = None
    bboxRight: float | None = None
    bboxBottom: float | None = None
    geometry: Any | None = None
    sourceProvider: str | None = None
    sourceModel: str | None = None
    sourceModelVersion: str | None = None
    createdAt: datetime | None = None


class ProjectWorkItemRead(BaseModel):
    id: str
    projectId: str
    workTypeCode: str
    categoryCode: str
    title: str
    status: str
    sourceType: str
    itemSequence: int
    measuredQuantity: float | None = None
    measuredUnit: str | None = None
    defaultUnit: str
    workTypeVersion: int
    settingVersion: int | None = None
    tenantPricingProfileId: str | None = None
    notes: str | None = None
    values: list[ProjectWorkItemValueRead] = Field(default_factory=list)
    detections: list[VisionDetectionRead] = Field(default_factory=list)
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class ProjectWorkItemListResponse(BaseModel):
    items: list[ProjectWorkItemRead]
    total: int
