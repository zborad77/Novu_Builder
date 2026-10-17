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
    parameterScope: str = "global"
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


class AnalysisProfileTargetObjectRead(BaseModel):
    code: str
    label: str
    description: str | None = None
    objectRole: str
    isRequired: bool
    sortOrder: int


class AnalysisProfileIgnoredObjectRead(BaseModel):
    code: str
    label: str
    reason: str | None = None
    sortOrder: int


class AnalysisProfileExtractionRuleRead(BaseModel):
    attributeCode: str
    label: str
    description: str | None = None
    dataType: str
    unit: str | None = None
    targetParameterCode: str
    sourceObjectCode: str
    required: bool
    manualReviewOnMissing: bool
    sortOrder: int


class AnalysisProfileValidationRuleRead(BaseModel):
    code: str
    ruleType: str
    severity: str
    targetAttributeCode: str | None = None
    targetParameterCode: str | None = None
    minNumberValue: float | None = None
    maxNumberValue: float | None = None
    message: str
    sortOrder: int


class AnalysisProfileConfidenceThresholdRead(BaseModel):
    attributeCode: str
    targetObjectCode: str | None = None
    minConfidence: float
    preferredConfidence: float
    actionBelowThreshold: str
    sortOrder: int


class AnalysisProfileOutputMappingRead(BaseModel):
    code: str
    targetEntity: str
    targetField: str
    sourceAttributeCode: str
    targetParameterCode: str | None = None
    required: bool
    sortOrder: int


class AnalysisProfileFallbackBehaviorRead(BaseModel):
    mode: str
    instructions: str | None = None
    requiresManualReview: bool


class AnalysisProfileRead(BaseModel):
    code: str
    name: str
    status: str
    providerFamily: str
    taskType: str
    outputContractVersion: int
    confidenceThreshold: float | None = None
    maxDetectionsPerPhoto: int
    scopeCode: str
    scopeLabel: str
    scopeDescription: str | None = None
    fallbackBehavior: AnalysisProfileFallbackBehaviorRead
    profileVersion: int
    targetObjects: list[AnalysisProfileTargetObjectRead] = Field(default_factory=list)
    ignoredObjects: list[AnalysisProfileIgnoredObjectRead] = Field(default_factory=list)
    extractionRules: list[AnalysisProfileExtractionRuleRead] = Field(default_factory=list)
    validationRules: list[AnalysisProfileValidationRuleRead] = Field(default_factory=list)
    confidenceThresholds: list[AnalysisProfileConfidenceThresholdRead] = Field(default_factory=list)
    outputMappings: list[AnalysisProfileOutputMappingRead] = Field(default_factory=list)


class CatalogPricingProfileRequiredInputRead(BaseModel):
    code: str
    label: str
    description: str | None = None
    sourceType: str
    sourceKey: str
    required: bool
    sortOrder: int


class CatalogPricingProfileLaborAssumptionRead(BaseModel):
    code: str
    label: str
    description: str | None = None
    quantitySourceType: str
    quantitySourceKey: str | None = None
    hoursPerUnit: float
    crewSize: int | None = None
    sortOrder: int


class CatalogPricingProfileMaterialAssumptionRead(BaseModel):
    code: str
    label: str
    description: str | None = None
    quantitySourceType: str
    quantitySourceKey: str | None = None
    quantityPerUnit: float
    unit: str
    defaultUnitCost: float | None = None
    wasteFactorPct: float | None = None
    sortOrder: int


class CatalogPricingProfileBaseRuleRead(BaseModel):
    code: str
    label: str
    description: str | None = None
    lineType: str
    calculationMethod: str
    quantitySourceType: str
    quantitySourceKey: str | None = None
    quantityMultiplier: float
    unit: str
    rateSource: str
    rateValue: float | None = None
    laborAssumptionCode: str | None = None
    materialAssumptionCode: str | None = None
    sortOrder: int


class CatalogPricingProfileAdjustmentRuleRead(BaseModel):
    code: str
    label: str
    description: str | None = None
    targetScope: str
    targetLineType: str | None = None
    targetBaseRuleCode: str | None = None
    operation: str
    adjustmentValue: float
    conditionSourceType: str
    conditionSourceKey: str
    conditionOperator: str
    conditionTextValue: str | None = None
    conditionNumberValue: float | None = None
    conditionBooleanValue: bool | None = None
    conditionOptionCode: str | None = None
    sortOrder: int


class CatalogPricingProfileRead(BaseModel):
    code: str
    name: str
    status: str
    pricingBasis: str
    currency: str
    pricingStrategy: str
    laborRateSource: str
    materialPricingSource: str
    defaultMarginPct: float | None = None
    defaultMarkupPct: float | None = None
    minJobPrice: float | None = None
    profileVersion: int
    requiredInputs: list[CatalogPricingProfileRequiredInputRead] = Field(default_factory=list)
    baseRules: list[CatalogPricingProfileBaseRuleRead] = Field(default_factory=list)
    adjustmentRules: list[CatalogPricingProfileAdjustmentRuleRead] = Field(default_factory=list)
    laborAssumptions: list[CatalogPricingProfileLaborAssumptionRead] = Field(default_factory=list)
    materialAssumptions: list[CatalogPricingProfileMaterialAssumptionRead] = Field(default_factory=list)


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


class TenantWorkTypeExtraParameterOptionUpsert(BaseModel):
    code: str
    label: str
    sortOrder: int | None = None
    isActive: bool = True


class TenantWorkTypeExtraParameterRead(BaseModel):
    parameterDefinitionId: str
    parameterScope: str = "tenant_extra"
    status: str
    code: str
    slug: str
    label: str
    description: str | None = None
    dataType: str
    unit: str | None = None
    section: str
    sectionLabel: str
    required: bool
    enabled: bool
    sortOrder: int
    minNumberValue: float | None = None
    maxNumberValue: float | None = None
    visionExtractable: bool
    manualOverrideAllowed: bool
    defaultTextValue: str | None = None
    defaultNumberValue: float | None = None
    defaultBooleanValue: bool | None = None
    defaultOptionCode: str | None = None
    enumOptions: list[WorkTypeParameterOptionRead] = Field(default_factory=list)
    configVersion: int | None = None
    updatedAt: datetime | None = None


class WorkCategoryRead(BaseModel):
    code: str
    slug: str
    name: str
    name_cs: str | None = None
    description: str | None = None
    sortOrder: int
    catalogVersion: int


class WorkTypePhaseBindingRead(BaseModel):
    allowedCaseStates: list[str] = Field(default_factory=list)
    recommendedCaseStates: list[str] = Field(default_factory=list)
    visionDetectable: bool
    currentCaseStatus: str | None = None
    allowedInCurrentCaseState: bool | None = None
    recommendedInCurrentCaseState: bool | None = None


class CatalogCategoryListItemRead(WorkCategoryRead):
    activeWorkTypeCount: int = 0
    totalWorkTypeCount: int = 0


class CatalogCategoryListResponse(BaseModel):
    items: list[CatalogCategoryListItemRead]
    total: int


class CatalogWorkTypeListItemRead(BaseModel):
    code: str
    slug: str
    name: str
    description: str | None = None
    state: str
    category: WorkCategoryRead
    defaultUnit: str
    measurementKind: str
    workTypeVersion: int
    sortOrder: int
    parameterCount: int
    requiredParameterCount: int
    supportsVision: bool
    supportsPricing: bool
    phaseBinding: WorkTypePhaseBindingRead


class CatalogWorkTypeListResponse(BaseModel):
    items: list[CatalogWorkTypeListItemRead]
    total: int


class CatalogWorkTypeDetailRead(BaseModel):
    code: str
    slug: str
    name: str
    description: str | None = None
    state: str
    category: WorkCategoryRead
    defaultUnit: str
    measurementKind: str
    workTypeVersion: int
    sortOrder: int
    supportsVision: bool
    supportsPricing: bool
    phaseBinding: WorkTypePhaseBindingRead
    analysisProfile: AnalysisProfileRead | None = None
    catalogPricingProfile: CatalogPricingProfileRead | None = None
    parameters: list[WorkTypeParameterRead] = Field(default_factory=list)
    parameterSections: list[WorkTypeParameterSectionRead] = Field(default_factory=list)


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
    phaseBinding: WorkTypePhaseBindingRead
    analysisProfile: AnalysisProfileRead | None = None
    catalogPricingProfile: CatalogPricingProfileRead | None = None
    tenantPricingProfileId: str | None = None
    parameters: list[WorkTypeParameterRead] = Field(default_factory=list)
    parameterSections: list[WorkTypeParameterSectionRead] = Field(default_factory=list)
    tenantSetting: TenantWorkTypeSettingRead | None = None
    parameterOverrides: list[TenantWorkTypeParameterOverrideRead] = Field(default_factory=list)
    extraParameters: list[TenantWorkTypeExtraParameterRead] = Field(default_factory=list)


class EffectiveWorkTypeListResponse(BaseModel):
    items: list[EffectiveWorkTypeRead]
    total: int


class ParameterSchemaAnalysisBindingRead(BaseModel):
    bindingType: str
    bindingCode: str
    attributeCode: str | None = None
    targetEntity: str | None = None
    required: bool | None = None


class ParameterSchemaPricingBindingRead(BaseModel):
    bindingType: str
    bindingCode: str
    sourceType: str
    sourceKey: str | None = None
    required: bool | None = None
    lineType: str | None = None


class ParameterSchemaDetailRead(BaseModel):
    workTypeCode: str
    workTypeName: str
    category: WorkCategoryRead
    parameter: WorkTypeParameterRead
    supportsVisionPopulation: bool
    supportsPricingInput: bool
    analysisBindings: list[ParameterSchemaAnalysisBindingRead] = Field(default_factory=list)
    pricingBindings: list[ParameterSchemaPricingBindingRead] = Field(default_factory=list)


class EffectiveVisionConfigurationRead(BaseModel):
    supported: bool
    analysisProfileCode: str | None = None
    analysisProfileVersion: int | None = None
    taskType: str | None = None
    extractableParameterCodes: list[str] = Field(default_factory=list)
    outputParameterCodes: list[str] = Field(default_factory=list)
    fallbackRequiresManualReview: bool = False


class EffectivePricingConfigurationRead(BaseModel):
    supported: bool
    catalogPricingProfileCode: str | None = None
    catalogPricingProfileVersion: int | None = None
    tenantPricingProfileId: str | None = None
    requiredInputCodes: list[str] = Field(default_factory=list)
    parameterInputCodes: list[str] = Field(default_factory=list)
    workItemFieldInputCodes: list[str] = Field(default_factory=list)
    quantityParameterCodes: list[str] = Field(default_factory=list)
    conditionParameterCodes: list[str] = Field(default_factory=list)


class ProjectWorkItemEffectiveConfigurationRead(BaseModel):
    projectId: str
    caseStatus: str
    workTypeCode: str
    effectiveWorkType: EffectiveWorkTypeRead
    requiredParameterCodes: list[str] = Field(default_factory=list)
    defaultedParameterCodes: list[str] = Field(default_factory=list)
    vision: EffectiveVisionConfigurationRead
    pricing: EffectivePricingConfigurationRead


class ProjectWorkItemWorkflowRead(BaseModel):
    supportsVision: bool
    supportsPricing: bool
    canUpdateValues: bool
    canConfirmValues: bool
    canCreateVisionDetections: bool
    pendingConfirmationParameterCodes: list[str] = Field(default_factory=list)
    confirmedParameterCodes: list[str] = Field(default_factory=list)
    defaultedParameterCodes: list[str] = Field(default_factory=list)
    missingRequiredParameterCodes: list[str] = Field(default_factory=list)
    missingPricingInputCodes: list[str] = Field(default_factory=list)


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


class TenantWorkTypeExtraParameterUpsert(BaseModel):
    status: str = "active"
    code: str
    slug: str
    label: str
    description: str | None = None
    dataType: str
    unit: str | None = None
    section: str
    required: bool = False
    sortOrder: int | None = None
    minNumberValue: float | None = None
    maxNumberValue: float | None = None
    visionExtractable: bool = False
    manualOverrideAllowed: bool = True
    defaultTextValue: str | None = None
    defaultNumberValue: float | None = None
    defaultBooleanValue: bool | None = None
    defaultOptionCode: str | None = None
    enumOptions: list[TenantWorkTypeExtraParameterOptionUpsert] = Field(default_factory=list)


class TenantWorkTypeSettingWithParametersUpsert(TenantWorkTypeSettingUpsert):
    parameterOverrides: list[TenantWorkTypeParameterOverrideUpsert] = Field(default_factory=list)
    extraParameters: list[TenantWorkTypeExtraParameterUpsert] = Field(default_factory=list)


class ProjectWorkItemValueInput(BaseModel):
    parameterCode: str
    textValue: str | None = None
    numberValue: float | None = None
    booleanValue: bool | None = None
    optionValue: str | None = None
    sourceType: str = "manual"
    sourceConfidence: float | None = Field(default=None, ge=0, le=1)
    sourceDetectionId: str | None = None
    operatorNote: str | None = None


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
    parameterScope: str = "global"
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
    sourceConfidence: float | None = None
    sourceDetectionId: str | None = None
    confirmationStatus: str
    confirmedByUserId: str | None = None
    confirmedAt: datetime | None = None
    operatorNote: str | None = None
    updatedAt: datetime | None = None


class ProjectWorkItemValueConfirmationInput(BaseModel):
    parameterCode: str
    action: str
    textValue: str | None = None
    numberValue: float | None = None
    booleanValue: bool | None = None
    optionValue: str | None = None
    operatorNote: str | None = None


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
    confirmationStatus: str
    itemSequence: int
    measuredQuantity: float | None = None
    measuredUnit: str | None = None
    defaultUnit: str
    workTypeVersion: int
    settingVersion: int | None = None
    analysisProfileCode: str | None = None
    analysisProfileVersion: int | None = None
    catalogPricingProfileCode: str | None = None
    catalogPricingProfileVersion: int | None = None
    tenantPricingProfileId: str | None = None
    notes: str | None = None
    confirmedByUserId: str | None = None
    confirmedAt: datetime | None = None
    values: list[ProjectWorkItemValueRead] = Field(default_factory=list)
    detections: list[VisionDetectionRead] = Field(default_factory=list)
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class ProjectWorkItemListResponse(BaseModel):
    items: list[ProjectWorkItemRead]
    total: int


class ProjectWorkItemDetailRead(BaseModel):
    workItem: ProjectWorkItemRead
    effectiveConfiguration: ProjectWorkItemEffectiveConfigurationRead
    workflow: ProjectWorkItemWorkflowRead


# ---------------------------------------------------------------------------
# Grouped catalog — 4 display groups with Czech names for the UI picker
# ---------------------------------------------------------------------------

class CatalogGroupedWorkTypeRead(BaseModel):
    code: str
    name: str


class CatalogGroupedCategoryRead(BaseModel):
    code: str
    name: str
    types: list[CatalogGroupedWorkTypeRead] = Field(default_factory=list)


class CatalogGroupedResponse(BaseModel):
    items: list[CatalogGroupedCategoryRead]
    total: int

