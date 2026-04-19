from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

from redis.asyncio import Redis

from app.core.metrics import observe_work_catalog_resolution, record_work_catalog_validation_failure
from app.models.work_catalog import (
    ProjectWorkItem,
    ProjectWorkItemValue,
    TenantWorkTypeExtraParameter,
    TenantWorkTypeParameterOverride,
    VisionDetection,
    WorkType,
)
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.schemas.work_catalog import (
    AnalysisProfileConfidenceThresholdRead,
    AnalysisProfileExtractionRuleRead,
    AnalysisProfileFallbackBehaviorRead,
    AnalysisProfileIgnoredObjectRead,
    AnalysisProfileOutputMappingRead,
    AnalysisProfileRead,
    AnalysisProfileTargetObjectRead,
    AnalysisProfileValidationRuleRead,
    CatalogPricingProfileAdjustmentRuleRead,
    CatalogPricingProfileBaseRuleRead,
    CatalogPricingProfileLaborAssumptionRead,
    CatalogPricingProfileMaterialAssumptionRead,
    CatalogPricingProfileRequiredInputRead,
    CatalogPricingProfileRead,
    CatalogCategoryListItemRead,
    CatalogWorkTypeDetailRead,
    CatalogWorkTypeListItemRead,
    EffectiveWorkTypeRead,
    EffectivePricingConfigurationRead,
    EffectiveVisionConfigurationRead,
    ParameterSchemaAnalysisBindingRead,
    ParameterSchemaDetailRead,
    ParameterSchemaPricingBindingRead,
    ProjectWorkItemCreate,
    ProjectWorkItemDetailRead,
    ProjectWorkItemEffectiveConfigurationRead,
    ProjectWorkItemRead,
    ProjectWorkItemWorkflowRead,
    ProjectWorkItemValueConfirmationInput,
    ProjectWorkItemValueInput,
    ProjectWorkItemValueRead,
    TenantWorkTypeExtraParameterRead,
    TenantWorkTypeExtraParameterUpsert,
    TenantWorkTypeParameterOverrideRead,
    TenantWorkTypeSettingRead,
    TenantWorkTypeSettingWithParametersUpsert,
    VisionDetectionCreate,
    VisionDetectionRead,
    WorkCategoryRead,
    WorkTypePhaseBindingRead,
    WorkTypeParameterOptionRead,
    WorkTypeParameterRead,
    WorkTypeParameterSectionRead,
)
from app.work_catalog.domain import (
    CATALOG_PRICING_STRATEGIES,
    MATERIAL_PRICING_SOURCES,
    PROJECT_WORK_ITEM_CONFIRMATION_STATUSES,
    PROJECT_WORK_ITEM_SOURCE_TYPES,
    PROJECT_WORK_ITEM_STATUSES,
    PROJECT_WORK_ITEM_VALUE_CONFIRMATION_STATUSES,
    TENANT_PARAMETER_OVERRIDE_STATUSES,
    TENANT_WORK_TYPE_SETTING_STATUSES,
    VISION_DETECTION_STATUSES,
    WORK_TYPE_PARAMETER_DATA_TYPES,
    WORK_TYPE_STATES,
    CatalogValidationError,
    coerce_parameter_value,
    normalize_enum,
    normalize_machine_code,
    normalize_optional_name,
    normalize_runtime_source_type,
    section_label,
    section_sort_order,
    validate_tenant_extra_parameter_definition,
)
from app.services.tenant_work_type_resolution_service import (
    ResolvedParameterDefinition,
    ResolvedTenantWorkTypeConfiguration,
    TenantWorkTypeResolutionService,
)
from app.work_catalog.phase_bindings import (
    get_phase_binding,
    is_allowed_in_status,
    is_recommended_in_status,
)
from app.work_catalog.cache import invalidate_pricing_resolution_cache, invalidate_tenant_effective_cache


class WorkCatalogNotFoundError(LookupError):
    """Raised when a requested catalog object does not exist in scope."""


def _as_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _initial_confirmation_status_for_source(source_type: str) -> str:
    if source_type == "manual":
        return "confirmed"
    if source_type == "default":
        return "defaulted"
    return "pending"


def _derive_work_item_confirmation_status(values: list[ProjectWorkItemValue]) -> str:
    statuses = {value.confirmation_status for value in values}
    if not statuses:
        return "pending"
    if statuses.issubset({"confirmed", "corrected", "defaulted"}):
        return "confirmed"
    if statuses.issubset({"pending", "defaulted"}):
        return "pending"
    return "mixed"


def _analysis_profile_read(profile) -> AnalysisProfileRead | None:
    if profile is None:
        return None
    return AnalysisProfileRead(
        code=profile.code,
        name=profile.name,
        status=profile.status,
        providerFamily=profile.provider_family,
        taskType=profile.task_type,
        outputContractVersion=profile.output_contract_version,
        confidenceThreshold=_as_float(profile.confidence_threshold),
        maxDetectionsPerPhoto=profile.max_detections_per_photo,
        scopeCode=profile.scope_code,
        scopeLabel=profile.scope_label,
        scopeDescription=profile.scope_description,
        fallbackBehavior=AnalysisProfileFallbackBehaviorRead(
            mode=profile.fallback_mode,
            instructions=profile.fallback_instructions,
            requiresManualReview=profile.fallback_requires_manual_review,
        ),
        profileVersion=profile.profile_version,
        targetObjects=[
            AnalysisProfileTargetObjectRead(
                code=row.code,
                label=row.label,
                description=row.description,
                objectRole=row.object_role,
                isRequired=row.is_required,
                sortOrder=row.sort_order,
            )
            for row in (profile.target_objects or [])
        ],
        ignoredObjects=[
            AnalysisProfileIgnoredObjectRead(
                code=row.code,
                label=row.label,
                reason=row.reason,
                sortOrder=row.sort_order,
            )
            for row in (profile.ignored_objects or [])
        ],
        extractionRules=[
            AnalysisProfileExtractionRuleRead(
                attributeCode=row.attribute_code,
                label=row.label,
                description=row.description,
                dataType=row.data_type,
                unit=row.unit,
                targetParameterCode=row.target_parameter_code,
                sourceObjectCode=row.source_object_code,
                required=row.is_required,
                manualReviewOnMissing=row.manual_review_on_missing,
                sortOrder=row.sort_order,
            )
            for row in (profile.extraction_rules or [])
        ],
        validationRules=[
            AnalysisProfileValidationRuleRead(
                code=row.code,
                ruleType=row.rule_type,
                severity=row.severity,
                targetAttributeCode=row.target_attribute_code,
                targetParameterCode=row.target_parameter_code,
                minNumberValue=_as_float(row.min_number_value),
                maxNumberValue=_as_float(row.max_number_value),
                message=row.message,
                sortOrder=row.sort_order,
            )
            for row in (profile.validation_rules or [])
        ],
        confidenceThresholds=[
            AnalysisProfileConfidenceThresholdRead(
                attributeCode=row.attribute_code,
                targetObjectCode=row.target_object_code,
                minConfidence=float(row.min_confidence),
                preferredConfidence=float(row.preferred_confidence),
                actionBelowThreshold=row.action_below_threshold,
                sortOrder=row.sort_order,
            )
            for row in (profile.confidence_thresholds or [])
        ],
        outputMappings=[
            AnalysisProfileOutputMappingRead(
                code=row.code,
                targetEntity=row.target_entity,
                targetField=row.target_field,
                sourceAttributeCode=row.source_attribute_code,
                targetParameterCode=row.target_parameter_code,
                required=row.is_required,
                sortOrder=row.sort_order,
            )
            for row in (profile.output_mappings or [])
        ],
    )


def _analysis_profile_matches_work_type(profile, work_type: WorkType) -> bool:
    if profile is None:
        return True
    return profile.code.startswith(f"{work_type.code}-")


def _catalog_pricing_profile_read(profile) -> CatalogPricingProfileRead | None:
    if profile is None:
        return None
    return CatalogPricingProfileRead(
        code=profile.code,
        name=profile.name,
        status=profile.status,
        pricingBasis=profile.pricing_basis,
        currency=profile.currency,
        pricingStrategy=profile.pricing_strategy,
        laborRateSource=profile.labor_rate_source,
        materialPricingSource=profile.material_pricing_source,
        defaultMarginPct=_as_float(profile.default_margin_pct),
        defaultMarkupPct=_as_float(profile.default_markup_pct),
        minJobPrice=_as_float(profile.min_job_price),
        profileVersion=profile.profile_version,
        requiredInputs=[
            CatalogPricingProfileRequiredInputRead(
                code=row.code,
                label=row.label,
                description=row.description,
                sourceType=row.source_type,
                sourceKey=row.source_key,
                required=row.is_required,
                sortOrder=row.sort_order,
            )
            for row in (profile.required_inputs or [])
        ],
        baseRules=[
            CatalogPricingProfileBaseRuleRead(
                code=row.code,
                label=row.label,
                description=row.description,
                lineType=row.line_type,
                calculationMethod=row.calculation_method,
                quantitySourceType=row.quantity_source_type,
                quantitySourceKey=row.quantity_source_key,
                quantityMultiplier=_as_float(row.quantity_multiplier) or 0,
                unit=row.unit,
                rateSource=row.rate_source,
                rateValue=_as_float(row.rate_value),
                laborAssumptionCode=row.labor_assumption_code,
                materialAssumptionCode=row.material_assumption_code,
                sortOrder=row.sort_order,
            )
            for row in (profile.base_rules or [])
        ],
        adjustmentRules=[
            CatalogPricingProfileAdjustmentRuleRead(
                code=row.code,
                label=row.label,
                description=row.description,
                targetScope=row.target_scope,
                targetLineType=row.target_line_type,
                targetBaseRuleCode=row.target_base_rule_code,
                operation=row.operation,
                adjustmentValue=_as_float(row.adjustment_value) or 0,
                conditionSourceType=row.condition_source_type,
                conditionSourceKey=row.condition_source_key,
                conditionOperator=row.condition_operator,
                conditionTextValue=row.condition_text_value,
                conditionNumberValue=_as_float(row.condition_number_value),
                conditionBooleanValue=row.condition_boolean_value,
                conditionOptionCode=row.condition_option_code,
                sortOrder=row.sort_order,
            )
            for row in (profile.adjustment_rules or [])
        ],
        laborAssumptions=[
            CatalogPricingProfileLaborAssumptionRead(
                code=row.code,
                label=row.label,
                description=row.description,
                quantitySourceType=row.quantity_source_type,
                quantitySourceKey=row.quantity_source_key,
                hoursPerUnit=_as_float(row.hours_per_unit) or 0,
                crewSize=row.crew_size,
                sortOrder=row.sort_order,
            )
            for row in (profile.labor_assumptions or [])
        ],
        materialAssumptions=[
            CatalogPricingProfileMaterialAssumptionRead(
                code=row.code,
                label=row.label,
                description=row.description,
                quantitySourceType=row.quantity_source_type,
                quantitySourceKey=row.quantity_source_key,
                quantityPerUnit=_as_float(row.quantity_per_unit) or 0,
                unit=row.unit,
                defaultUnitCost=_as_float(row.default_unit_cost),
                wasteFactorPct=_as_float(row.waste_factor_pct),
                sortOrder=row.sort_order,
            )
            for row in (profile.material_assumptions or [])
        ],
    )


def _catalog_pricing_profile_matches_work_type(profile, work_type: WorkType) -> bool:
    if profile is None:
        return True
    return profile.code.startswith(f"{work_type.code}-")


def _resolved_parameter_read(
    parameter: ResolvedParameterDefinition,
) -> WorkTypeParameterRead:
    return WorkTypeParameterRead(
        parameterDefinitionId=parameter.parameter_definition_id,
        parameterScope=parameter.parameter_scope,
        code=parameter.code,
        slug=parameter.slug,
        label=parameter.label,
        effectiveLabel=parameter.effective_label,
        description=parameter.description,
        dataType=parameter.data_type,
        unit=parameter.unit,
        section=parameter.section,
        sectionLabel=section_label(parameter.section),
        required=parameter.required,
        enabled=parameter.enabled,
        sortOrder=parameter.sort_order,
        overrideStatus=parameter.override_status,
        settingVersion=parameter.setting_version,
        minNumberValue=parameter.min_number_value,
        maxNumberValue=parameter.max_number_value,
        visionExtractable=parameter.vision_extractable,
        manualOverrideAllowed=parameter.manual_override_allowed,
        defaultTextValue=parameter.default_text_value,
        defaultNumberValue=parameter.default_number_value,
        defaultBooleanValue=parameter.default_boolean_value,
        defaultOptionCode=parameter.default_option_code,
        enumOptions=[
            WorkTypeParameterOptionRead(
                code=option.code,
                label=option.label,
                sortOrder=option.sort_order,
                isActive=option.is_active,
            )
            for option in parameter.enum_options
        ],
    )


def _tenant_setting_read(resolved: ResolvedTenantWorkTypeConfiguration) -> TenantWorkTypeSettingRead | None:
    setting = resolved.tenant_setting
    if setting is None:
        return None
    return TenantWorkTypeSettingRead(
        status=setting.status,
        customDisplayName=setting.custom_display_name,
        analysisProfileCode=resolved.tenant_analysis_profile_code,
        catalogPricingProfileCode=resolved.tenant_catalog_pricing_profile_code,
        tenantPricingProfileId=setting.tenant_pricing_profile_id,
        isBillableOverride=setting.is_billable_override,
        sortOrderOverride=setting.sort_order_override,
        configVersion=setting.config_version,
        updatedAt=setting.updated_at,
    )


def _tenant_parameter_override_read(
    override: TenantWorkTypeParameterOverride,
) -> TenantWorkTypeParameterOverrideRead:
    return TenantWorkTypeParameterOverrideRead(
        parameterCode=override.parameter.code if override.parameter else "",
        overrideStatus=override.override_status,
        customDisplayName=override.custom_display_name,
        sortOrderOverride=override.sort_order_override,
        defaultTextValue=override.default_text_value,
        defaultNumberValue=_as_float(override.default_number_value),
        defaultBooleanValue=override.default_boolean_value,
        defaultOptionCode=override.default_option_code,
        configVersion=override.config_version,
        updatedAt=override.updated_at,
    )


def _tenant_extra_parameter_read(
    parameter: TenantWorkTypeExtraParameter,
) -> TenantWorkTypeExtraParameterRead:
    return TenantWorkTypeExtraParameterRead(
        parameterDefinitionId=parameter.id,
        parameterScope="tenant_extra",
        status=parameter.status,
        code=parameter.code,
        slug=parameter.slug,
        label=parameter.name,
        description=parameter.description,
        dataType=parameter.data_type,
        unit=parameter.unit,
        section=parameter.section,
        sectionLabel=section_label(parameter.section),
        required=parameter.is_required,
        enabled=parameter.status == "active",
        sortOrder=parameter.sort_order,
        minNumberValue=_as_float(parameter.min_number_value),
        maxNumberValue=_as_float(parameter.max_number_value),
        visionExtractable=parameter.vision_extractable,
        manualOverrideAllowed=parameter.manual_override_allowed,
        defaultTextValue=parameter.default_text_value,
        defaultNumberValue=_as_float(parameter.default_number_value),
        defaultBooleanValue=parameter.default_boolean_value,
        defaultOptionCode=parameter.default_option_code,
        enumOptions=[
            WorkTypeParameterOptionRead(
                code=option.code,
                label=option.label,
                sortOrder=option.sort_order,
                isActive=option.is_active,
            )
            for option in (parameter.options or [])
        ],
        configVersion=parameter.config_version,
        updatedAt=parameter.updated_at,
    )


def _resolved_extra_parameter_read(
    parameter: ResolvedParameterDefinition,
) -> TenantWorkTypeExtraParameterRead:
    return TenantWorkTypeExtraParameterRead(
        parameterDefinitionId=parameter.parameter_definition_id,
        parameterScope=parameter.parameter_scope,
        status=parameter.override_status or "active",
        code=parameter.code,
        slug=parameter.slug,
        label=parameter.label,
        description=parameter.description,
        dataType=parameter.data_type,
        unit=parameter.unit,
        section=parameter.section,
        sectionLabel=parameter.section_label,
        required=parameter.required,
        enabled=parameter.enabled,
        sortOrder=parameter.sort_order,
        minNumberValue=parameter.min_number_value,
        maxNumberValue=parameter.max_number_value,
        visionExtractable=parameter.vision_extractable,
        manualOverrideAllowed=parameter.manual_override_allowed,
        defaultTextValue=parameter.default_text_value,
        defaultNumberValue=parameter.default_number_value,
        defaultBooleanValue=parameter.default_boolean_value,
        defaultOptionCode=parameter.default_option_code,
        enumOptions=[
            WorkTypeParameterOptionRead(
                code=option.code,
                label=option.label,
                sortOrder=option.sort_order,
                isActive=option.is_active,
            )
            for option in parameter.enum_options
        ],
        configVersion=parameter.setting_version,
        updatedAt=None,
    )


def _category_read(category) -> WorkCategoryRead:
    return WorkCategoryRead(
        code=category.code,
        slug=category.slug,
        name=category.name,
        description=category.description,
        sortOrder=category.sort_order,
        catalogVersion=category.catalog_version,
    )


def _phase_binding_read(
    work_type_code: str,
    *,
    case_status: str | None = None,
) -> WorkTypePhaseBindingRead:
    binding = get_phase_binding(work_type_code)
    if binding is None:
        return WorkTypePhaseBindingRead(visionDetectable=False, currentCaseStatus=case_status)
    return WorkTypePhaseBindingRead(
        allowedCaseStates=sorted(binding.allowed_in),
        recommendedCaseStates=sorted(binding.recommended_in),
        visionDetectable=binding.vision_detectable,
        currentCaseStatus=case_status,
        allowedInCurrentCaseState=(
            is_allowed_in_status(work_type_code, case_status)
            if case_status is not None
            else None
        ),
        recommendedInCurrentCaseState=(
            is_recommended_in_status(work_type_code, case_status)
            if case_status is not None
            else None
        ),
    )


def _global_parameter_read(parameter) -> WorkTypeParameterRead:
    return WorkTypeParameterRead(
        parameterDefinitionId=parameter.id,
        parameterScope="global",
        code=parameter.code,
        slug=parameter.slug,
        label=parameter.name,
        effectiveLabel=parameter.name,
        description=parameter.description,
        dataType=parameter.data_type,
        unit=parameter.unit,
        section=parameter.section or "optional_notes",
        sectionLabel=section_label(parameter.section or "optional_notes"),
        required=parameter.is_required,
        enabled=True,
        sortOrder=parameter.sort_order,
        minNumberValue=_as_float(parameter.min_number_value),
        maxNumberValue=_as_float(parameter.max_number_value),
        visionExtractable=parameter.vision_extractable,
        manualOverrideAllowed=parameter.manual_override_allowed,
        defaultTextValue=parameter.default_text_value,
        defaultNumberValue=_as_float(parameter.default_number_value),
        defaultBooleanValue=parameter.default_boolean_value,
        defaultOptionCode=parameter.default_option_code,
        enumOptions=[
            WorkTypeParameterOptionRead(
                code=option.code,
                label=option.label,
                sortOrder=option.sort_order,
                isActive=option.is_active,
            )
            for option in (parameter.options or [])
        ],
    )


class WorkCatalogService:
    def __init__(self, repository: WorkCatalogRepository, redis: Redis | None = None):
        self.repository = repository
        self.redis = redis
        self.resolution_service = TenantWorkTypeResolutionService(repository, redis=redis)

    async def _invalidate_tenant_effective_cache(
        self,
        *,
        organization_id: str,
        work_type_codes: set[str],
    ) -> None:
        await invalidate_tenant_effective_cache(
            self.redis,
            organization_id=organization_id,
            work_type_codes=work_type_codes,
        )
        await invalidate_pricing_resolution_cache(
            self.redis,
            organization_id=organization_id,
        )

    async def _get_work_type(self, work_type_code: str) -> WorkType | None:
        return await self.repository.get_work_type_by_code(work_type_code)

    @staticmethod
    def _assert_work_type_allowed_in_case_status(
        *,
        work_type_code: str,
        case_status: str,
        operation: str,
    ) -> None:
        if is_allowed_in_status(work_type_code, case_status):
            return
        binding = get_phase_binding(work_type_code)
        allowed_states = sorted(binding.allowed_in) if binding is not None else []
        raise CatalogValidationError(
            f"Work type '{work_type_code}' cannot be {operation} while case is in status "
            f"'{case_status}'. Allowed case states: {allowed_states}."
        )

    @staticmethod
    def _observe_operation(
        *,
        operation: str,
        started_at: float,
        outcome: str,
    ) -> None:
        observe_work_catalog_resolution(
            path=operation,
            outcome=outcome,
            duration_seconds=perf_counter() - started_at,
        )

    @staticmethod
    def _build_parameter_sections(
        parameters: list[WorkTypeParameterRead],
    ) -> list[WorkTypeParameterSectionRead]:
        grouped: dict[str, list[WorkTypeParameterRead]] = {}
        for parameter in parameters:
            grouped.setdefault(parameter.section, []).append(parameter)

        sections: list[WorkTypeParameterSectionRead] = []
        for section_code, items in grouped.items():
            items.sort(key=lambda item: (item.sortOrder, item.code))
            sections.append(
                WorkTypeParameterSectionRead(
                    code=section_code,
                    label=section_label(section_code),
                    sortOrder=section_sort_order(section_code),
                    parameters=items,
                )
            )
        sections.sort(key=lambda item: (item.sortOrder, item.code))
        return sections

    @staticmethod
    def _parameter_has_default(parameter: WorkTypeParameterRead) -> bool:
        return any(
            value is not None
            for value in (
                parameter.defaultTextValue,
                parameter.defaultNumberValue,
                parameter.defaultBooleanValue,
                parameter.defaultOptionCode,
            )
        )

    def _catalog_work_type_list_item_read(self, work_type) -> CatalogWorkTypeListItemRead:
        parameters = list(work_type.parameters or [])
        return CatalogWorkTypeListItemRead(
            code=work_type.code,
            slug=work_type.slug,
            name=work_type.name,
            description=work_type.description,
            state=work_type.state,
            category=_category_read(work_type.category),
            defaultUnit=work_type.default_unit,
            measurementKind=work_type.measurement_kind,
            workTypeVersion=work_type.catalog_version,
            sortOrder=work_type.sort_order,
            parameterCount=len(parameters),
            requiredParameterCount=sum(1 for parameter in parameters if parameter.is_required),
            supportsVision=work_type.default_analysis_profile is not None,
            supportsPricing=work_type.default_catalog_pricing_profile is not None,
            phaseBinding=_phase_binding_read(work_type.code),
        )

    def _catalog_work_type_detail_read(self, work_type) -> CatalogWorkTypeDetailRead:
        parameters = [_global_parameter_read(parameter) for parameter in (work_type.parameters or [])]
        return CatalogWorkTypeDetailRead(
            code=work_type.code,
            slug=work_type.slug,
            name=work_type.name,
            description=work_type.description,
            state=work_type.state,
            category=_category_read(work_type.category),
            defaultUnit=work_type.default_unit,
            measurementKind=work_type.measurement_kind,
            workTypeVersion=work_type.catalog_version,
            sortOrder=work_type.sort_order,
            supportsVision=work_type.default_analysis_profile is not None,
            supportsPricing=work_type.default_catalog_pricing_profile is not None,
            phaseBinding=_phase_binding_read(work_type.code),
            analysisProfile=_analysis_profile_read(work_type.default_analysis_profile),
            catalogPricingProfile=_catalog_pricing_profile_read(work_type.default_catalog_pricing_profile),
            parameters=parameters,
            parameterSections=self._build_parameter_sections(parameters),
        )

    def _effective_vision_configuration_read(
        self,
        effective: EffectiveWorkTypeRead,
    ) -> EffectiveVisionConfigurationRead:
        analysis_profile = effective.analysisProfile
        return EffectiveVisionConfigurationRead(
            supported=analysis_profile is not None,
            analysisProfileCode=analysis_profile.code if analysis_profile else None,
            analysisProfileVersion=analysis_profile.profileVersion if analysis_profile else None,
            taskType=analysis_profile.taskType if analysis_profile else None,
            extractableParameterCodes=sorted(
                parameter.code
                for parameter in effective.parameters
                if parameter.enabled and parameter.visionExtractable
            ),
            outputParameterCodes=sorted(
                {
                    mapping.targetParameterCode
                    for mapping in (analysis_profile.outputMappings if analysis_profile else [])
                    if mapping.targetParameterCode
                }
            ),
            fallbackRequiresManualReview=(
                analysis_profile.fallbackBehavior.requiresManualReview
                if analysis_profile
                else False
            ),
        )

    def _effective_pricing_configuration_read(
        self,
        effective: EffectiveWorkTypeRead,
    ) -> EffectivePricingConfigurationRead:
        pricing_profile = effective.catalogPricingProfile
        if pricing_profile is None:
            return EffectivePricingConfigurationRead(
                supported=False,
                tenantPricingProfileId=effective.tenantPricingProfileId,
            )
        return EffectivePricingConfigurationRead(
            supported=True,
            catalogPricingProfileCode=pricing_profile.code,
            catalogPricingProfileVersion=pricing_profile.profileVersion,
            tenantPricingProfileId=effective.tenantPricingProfileId,
            requiredInputCodes=sorted(
                input_rule.code
                for input_rule in pricing_profile.requiredInputs
                if input_rule.required
            ),
            parameterInputCodes=sorted(
                {
                    input_rule.sourceKey
                    for input_rule in pricing_profile.requiredInputs
                    if input_rule.sourceType == "parameter"
                }
            ),
            workItemFieldInputCodes=sorted(
                {
                    input_rule.sourceKey
                    for input_rule in pricing_profile.requiredInputs
                    if input_rule.sourceType == "work_item_field"
                }
            ),
            quantityParameterCodes=sorted(
                {
                    rule.quantitySourceKey
                    for rule in pricing_profile.baseRules
                    if rule.quantitySourceType == "parameter" and rule.quantitySourceKey
                }
            ),
            conditionParameterCodes=sorted(
                {
                    rule.conditionSourceKey
                    for rule in pricing_profile.adjustmentRules
                    if rule.conditionSourceType == "parameter" and rule.conditionSourceKey
                }
            ),
        )

    def _project_work_item_effective_configuration_read(
        self,
        *,
        project_id: str,
        case_status: str,
        effective: EffectiveWorkTypeRead,
    ) -> ProjectWorkItemEffectiveConfigurationRead:
        return ProjectWorkItemEffectiveConfigurationRead(
            projectId=project_id,
            caseStatus=case_status,
            workTypeCode=effective.code,
            effectiveWorkType=effective,
            requiredParameterCodes=sorted(
                parameter.code
                for parameter in effective.parameters
                if parameter.enabled and parameter.required
            ),
            defaultedParameterCodes=sorted(
                parameter.code
                for parameter in effective.parameters
                if parameter.enabled and self._parameter_has_default(parameter)
            ),
            vision=self._effective_vision_configuration_read(effective),
            pricing=self._effective_pricing_configuration_read(effective),
        )

    @staticmethod
    def _work_item_field_value(work_item: ProjectWorkItemRead, field_code: str):
        if field_code == "measured_quantity":
            return work_item.measuredQuantity
        if field_code == "measured_unit":
            return work_item.measuredUnit
        if field_code == "item_sequence":
            return work_item.itemSequence
        return None

    def _project_work_item_workflow_read(
        self,
        *,
        work_item: ProjectWorkItemRead,
        effective_configuration: ProjectWorkItemEffectiveConfigurationRead,
    ) -> ProjectWorkItemWorkflowRead:
        values_by_code = {value.parameterCode: value for value in work_item.values}
        pending_confirmation_codes = sorted(
            value.parameterCode
            for value in work_item.values
            if value.confirmationStatus == "pending"
        )
        confirmed_codes = sorted(
            value.parameterCode
            for value in work_item.values
            if value.confirmationStatus in {"confirmed", "corrected"}
        )
        defaulted_codes = sorted(
            value.parameterCode
            for value in work_item.values
            if value.confirmationStatus == "defaulted"
        )
        missing_required_codes = sorted(
            parameter_code
            for parameter_code in effective_configuration.requiredParameterCodes
            if parameter_code not in values_by_code
        )
        missing_pricing_inputs: list[str] = []
        pricing_profile = effective_configuration.effectiveWorkType.catalogPricingProfile
        if pricing_profile is not None:
            for input_rule in pricing_profile.requiredInputs:
                if not input_rule.required:
                    continue
                if input_rule.sourceType == "parameter":
                    if input_rule.sourceKey not in values_by_code:
                        missing_pricing_inputs.append(input_rule.code)
                    continue
                if self._work_item_field_value(work_item, input_rule.sourceKey) in (None, "", []):
                    missing_pricing_inputs.append(input_rule.code)

        return ProjectWorkItemWorkflowRead(
            supportsVision=effective_configuration.vision.supported,
            supportsPricing=effective_configuration.pricing.supported,
            canUpdateValues=True,
            canConfirmValues=bool(pending_confirmation_codes),
            canCreateVisionDetections=effective_configuration.vision.supported,
            pendingConfirmationParameterCodes=pending_confirmation_codes,
            confirmedParameterCodes=confirmed_codes,
            defaultedParameterCodes=defaulted_codes,
            missingRequiredParameterCodes=missing_required_codes,
            missingPricingInputCodes=sorted(set(missing_pricing_inputs)),
        )

    def _to_effective_read(
        self,
        resolved: ResolvedTenantWorkTypeConfiguration,
        *,
        case_status: str | None = None,
    ) -> EffectiveWorkTypeRead:
        work_type = resolved.work_type
        setting = resolved.tenant_setting
        category = work_type.category
        parameter_reads = [_resolved_parameter_read(parameter) for parameter in resolved.parameters]

        return EffectiveWorkTypeRead(
            code=work_type.code,
            slug=work_type.slug,
            name=work_type.name,
            description=work_type.description,
            state=work_type.state,
            isEnabled=resolved.is_enabled,
            effectiveDisplayName=resolved.effective_display_name,
            category=_category_read(category),
            defaultUnit=work_type.default_unit,
            measurementKind=work_type.measurement_kind,
            workTypeVersion=work_type.catalog_version,
            settingVersion=resolved.setting_version,
            phaseBinding=_phase_binding_read(work_type.code, case_status=case_status),
            analysisProfile=_analysis_profile_read(resolved.analysis_profile),
            catalogPricingProfile=_catalog_pricing_profile_read(resolved.catalog_pricing_profile),
            tenantPricingProfileId=resolved.tenant_pricing_profile_id,
            parameters=parameter_reads,
            parameterSections=self._build_parameter_sections(parameter_reads),
            tenantSetting=_tenant_setting_read(resolved),
            parameterOverrides=[
                _tenant_parameter_override_read(override)
                for override in resolved.sorted_parameter_overrides
            ],
            extraParameters=[
                _resolved_extra_parameter_read(parameter)
                for parameter in resolved.extra_parameter_definitions
            ],
        )

    async def list_effective_work_types(self, organization_id: str) -> list[EffectiveWorkTypeRead]:
        started_at = perf_counter()
        outcome = "success"
        try:
            resolved = await self.resolution_service.resolve_all_for_org(organization_id=organization_id)
            return [self._to_effective_read(item) for item in resolved]
        except CatalogValidationError:
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="work_catalog.list_effective_work_types",
                reason="invalid_effective_configuration",
            )
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            self._observe_operation(
                operation="work_catalog.list_effective_work_types",
                started_at=started_at,
                outcome=outcome,
            )

    async def ensure_project_exists(self, *, project_id: str, organization_id: str) -> None:
        project = await self.repository.get_project_in_org(project_id, organization_id)
        if project is None:
            raise WorkCatalogNotFoundError("Project was not found.")

    async def list_categories(self) -> list[CatalogCategoryListItemRead]:
        started_at = perf_counter()
        outcome = "success"
        try:
            rows = await self.repository.list_categories()
            items: list[CatalogCategoryListItemRead] = []
            for category, total_work_type_count, active_work_type_count in rows:
                items.append(
                    CatalogCategoryListItemRead(
                        **_category_read(category).model_dump(),
                        totalWorkTypeCount=int(total_work_type_count or 0),
                        activeWorkTypeCount=int(active_work_type_count or 0),
                    )
                )
            return items
        except Exception:
            outcome = "error"
            raise
        finally:
            self._observe_operation(
                operation="work_catalog.list_categories",
                started_at=started_at,
                outcome=outcome,
            )

    async def list_work_types_global(self) -> list[CatalogWorkTypeListItemRead]:
        started_at = perf_counter()
        outcome = "success"
        try:
            work_types = await self.repository.list_work_types_global()
            return [self._catalog_work_type_list_item_read(work_type) for work_type in work_types]
        except Exception:
            outcome = "error"
            raise
        finally:
            self._observe_operation(
                operation="work_catalog.list_work_types_global",
                started_at=started_at,
                outcome=outcome,
            )

    async def get_work_type_detail(self, work_type_code: str) -> CatalogWorkTypeDetailRead:
        started_at = perf_counter()
        outcome = "success"
        normalized_code = normalize_machine_code(work_type_code, field_name="workTypeCode")
        work_type = await self._get_work_type(normalized_code)
        if work_type is None:
            outcome = "not_found"
            self._observe_operation(
                operation="work_catalog.get_work_type_detail",
                started_at=started_at,
                outcome=outcome,
            )
            raise WorkCatalogNotFoundError(f"Work type '{normalized_code}' was not found.")
        try:
            return self._catalog_work_type_detail_read(work_type)
        finally:
            self._observe_operation(
                operation="work_catalog.get_work_type_detail",
                started_at=started_at,
                outcome=outcome,
            )

    async def get_parameter_schema_detail(
        self,
        *,
        work_type_code: str,
        parameter_code: str,
    ) -> ParameterSchemaDetailRead:
        started_at = perf_counter()
        outcome = "success"
        normalized_work_type_code = normalize_machine_code(work_type_code, field_name="workTypeCode")
        normalized_parameter_code = normalize_machine_code(parameter_code, field_name="parameterCode")
        work_type = await self._get_work_type(normalized_work_type_code)
        if work_type is None:
            outcome = "not_found"
            self._observe_operation(
                operation="work_catalog.get_parameter_schema_detail",
                started_at=started_at,
                outcome=outcome,
            )
            raise WorkCatalogNotFoundError(f"Work type '{normalized_work_type_code}' was not found.")
        parameter = next(
            (row for row in (work_type.parameters or []) if row.code == normalized_parameter_code),
            None,
        )
        if parameter is None:
            outcome = "not_found"
            self._observe_operation(
                operation="work_catalog.get_parameter_schema_detail",
                started_at=started_at,
                outcome=outcome,
            )
            raise WorkCatalogNotFoundError(
                f"Parameter '{normalized_parameter_code}' was not found for work type '{normalized_work_type_code}'."
            )
        analysis_profile = work_type.default_analysis_profile
        pricing_profile = work_type.default_catalog_pricing_profile
        analysis_bindings = [
            ParameterSchemaAnalysisBindingRead(
                bindingType="extraction_rule",
                bindingCode=row.attribute_code,
                attributeCode=row.attribute_code,
                targetEntity="project_work_item_value",
                required=row.is_required,
            )
            for row in (analysis_profile.extraction_rules if analysis_profile else [])
            if row.target_parameter_code == parameter.code
        ] + [
            ParameterSchemaAnalysisBindingRead(
                bindingType="output_mapping",
                bindingCode=row.code,
                attributeCode=row.source_attribute_code,
                targetEntity=row.target_entity,
                required=row.is_required,
            )
            for row in (analysis_profile.output_mappings if analysis_profile else [])
            if row.target_parameter_code == parameter.code
        ] + [
            ParameterSchemaAnalysisBindingRead(
                bindingType="validation_rule",
                bindingCode=row.code,
                attributeCode=row.target_attribute_code,
                targetEntity="project_work_item_value",
                required=True,
            )
            for row in (analysis_profile.validation_rules if analysis_profile else [])
            if row.target_parameter_code == parameter.code
        ]
        pricing_bindings = [
            ParameterSchemaPricingBindingRead(
                bindingType="required_input",
                bindingCode=row.code,
                sourceType=row.source_type,
                sourceKey=row.source_key,
                required=row.is_required,
            )
            for row in (pricing_profile.required_inputs if pricing_profile else [])
            if row.source_type == "parameter" and row.source_key == parameter.code
        ] + [
            ParameterSchemaPricingBindingRead(
                bindingType="base_rule_quantity",
                bindingCode=row.code,
                sourceType=row.quantity_source_type,
                sourceKey=row.quantity_source_key,
                lineType=row.line_type,
            )
            for row in (pricing_profile.base_rules if pricing_profile else [])
            if row.quantity_source_type == "parameter" and row.quantity_source_key == parameter.code
        ] + [
            ParameterSchemaPricingBindingRead(
                bindingType="adjustment_condition",
                bindingCode=row.code,
                sourceType=row.condition_source_type,
                sourceKey=row.condition_source_key,
                lineType=row.target_line_type,
            )
            for row in (pricing_profile.adjustment_rules if pricing_profile else [])
            if row.condition_source_type == "parameter" and row.condition_source_key == parameter.code
        ]
        try:
            return ParameterSchemaDetailRead(
                workTypeCode=work_type.code,
                workTypeName=work_type.name,
                category=_category_read(work_type.category),
                parameter=_global_parameter_read(parameter),
                supportsVisionPopulation=parameter.vision_extractable or bool(analysis_bindings),
                supportsPricingInput=bool(pricing_bindings),
                analysisBindings=analysis_bindings,
                pricingBindings=pricing_bindings,
            )
        finally:
            self._observe_operation(
                operation="work_catalog.get_parameter_schema_detail",
                started_at=started_at,
                outcome=outcome,
            )

    async def get_effective_work_type(self, organization_id: str, work_type_code: str) -> EffectiveWorkTypeRead:
        started_at = perf_counter()
        outcome = "success"
        try:
            resolved = await self.resolution_service.resolve_for_work_type(
                organization_id=organization_id,
                work_type_code=work_type_code,
            )
        except LookupError as exc:
            outcome = "not_found"
            raise WorkCatalogNotFoundError(str(exc)) from exc
        except CatalogValidationError:
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="work_catalog.get_effective_work_type",
                reason="invalid_effective_configuration",
            )
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            self._observe_operation(
                operation="work_catalog.get_effective_work_type",
                started_at=started_at,
                outcome=outcome,
            )
        return self._to_effective_read(resolved)

    @staticmethod
    def _validate_unique_parameter_override_payloads(
        *,
        work_type_code: str,
        override_payloads: list,
    ) -> None:
        seen_codes: set[str] = set()
        for override_payload in override_payloads:
            parameter_code = normalize_machine_code(
                override_payload.parameterCode,
                field_name="parameterCode",
            )
            if parameter_code in seen_codes:
                raise CatalogValidationError(
                    f"Duplicate parameter override payload for '{parameter_code}' on work type '{work_type_code}'."
                )
            seen_codes.add(parameter_code)

    @staticmethod
    def _validate_unique_extra_parameter_payloads(
        *,
        work_type_code: str,
        extra_payloads: list,
    ) -> None:
        seen_codes: set[str] = set()
        seen_slugs: set[str] = set()
        for extra_payload in extra_payloads:
            parameter_code = normalize_machine_code(extra_payload.code, field_name="code")
            parameter_slug = normalize_machine_code(extra_payload.slug, field_name="slug")
            if parameter_code in seen_codes:
                raise CatalogValidationError(
                    f"Duplicate tenant extra parameter code '{parameter_code}' on work type '{work_type_code}'."
                )
            if parameter_slug in seen_slugs:
                raise CatalogValidationError(
                    f"Duplicate tenant extra parameter slug '{parameter_slug}' on work type '{work_type_code}'."
                )
            seen_codes.add(parameter_code)
            seen_slugs.add(parameter_slug)

    async def upsert_tenant_setting(
        self,
        *,
        organization_id: str,
        work_type_code: str,
        payload: TenantWorkTypeSettingWithParametersUpsert,
        updated_by_user_id: str | None,
    ) -> EffectiveWorkTypeRead:
        started_at = perf_counter()
        outcome = "success"
        normalized_code = normalize_machine_code(work_type_code, field_name="workTypeCode")
        status = normalize_enum(
            payload.status,
            field_name="status",
            allowed=TENANT_WORK_TYPE_SETTING_STATUSES,
        )
        work_type = await self._get_work_type(normalized_code)
        if work_type is None:
            outcome = "not_found"
            raise WorkCatalogNotFoundError(f"Work type '{normalized_code}' was not found.")

        analysis_profile = None
        if payload.analysisProfileCode:
            analysis_profile = await self.repository.get_analysis_profile_by_code(
                normalize_machine_code(payload.analysisProfileCode, field_name="analysisProfileCode")
            )
            if analysis_profile is None:
                raise WorkCatalogNotFoundError("Analysis profile was not found.")
            if not _analysis_profile_matches_work_type(analysis_profile, work_type):
                raise CatalogValidationError(
                    f"Analysis profile '{analysis_profile.code}' cannot be assigned to work type '{work_type.code}'."
                )

        catalog_pricing_profile = None
        if payload.catalogPricingProfileCode:
            catalog_pricing_profile = await self.repository.get_catalog_pricing_profile_by_code(
                normalize_machine_code(payload.catalogPricingProfileCode, field_name="catalogPricingProfileCode")
            )
            if catalog_pricing_profile is None:
                raise WorkCatalogNotFoundError("Catalog pricing profile was not found.")
            if not _catalog_pricing_profile_matches_work_type(catalog_pricing_profile, work_type):
                raise CatalogValidationError(
                    f"Catalog pricing profile '{catalog_pricing_profile.code}' cannot be assigned to work type '{work_type.code}'."
                )
            if not catalog_pricing_profile.is_active or catalog_pricing_profile.status != "active":
                raise CatalogValidationError(
                    f"Catalog pricing profile '{catalog_pricing_profile.code}' is not active."
                )

        if payload.tenantPricingProfileId:
            tenant_pricing_profile = await self.repository.get_tenant_pricing_profile(
                payload.tenantPricingProfileId,
                organization_id=organization_id,
            )
            if tenant_pricing_profile is None:
                raise WorkCatalogNotFoundError("Tenant pricing profile was not found.")

        existing = (
            await self.repository.list_tenant_settings_for_org(
                organization_id,
                work_type_ids=[work_type.id],
            )
        ).get(work_type.id)
        updated = await self.repository.upsert_tenant_work_type_setting(
            existing=existing,
            setting_id=existing.id if existing else f"twts_{uuid4().hex[:10]}",
            organization_id=organization_id,
            work_type_id=work_type.id,
            status=status,
            custom_display_name=normalize_optional_name(payload.customDisplayName, field_name="customDisplayName"),
            analysis_profile_id=analysis_profile.id if analysis_profile else None,
            catalog_pricing_profile_id=catalog_pricing_profile.id if catalog_pricing_profile else None,
            tenant_pricing_profile_id=payload.tenantPricingProfileId,
            is_billable_override=payload.isBillableOverride,
            sort_order_override=payload.sortOrderOverride,
            updated_by_user_id=updated_by_user_id,
        )
        updated.analysis_profile = analysis_profile
        updated.catalog_pricing_profile = catalog_pricing_profile

        parameter_map = {parameter.code: parameter for parameter in (work_type.parameters or [])}
        self._validate_unique_parameter_override_payloads(
            work_type_code=work_type.code,
            override_payloads=list(getattr(payload, "parameterOverrides", [])),
        )
        override_payload_rows: list[dict] = []
        for override_payload in getattr(payload, "parameterOverrides", []):
            parameter_code = normalize_machine_code(
                override_payload.parameterCode,
                field_name="parameterCode",
            )
            parameter = parameter_map.get(parameter_code)
            if parameter is None:
                raise CatalogValidationError(
                    f"Parameter '{parameter_code}' is not defined for work type '{work_type.code}'."
                )
            override_status = normalize_enum(
                override_payload.overrideStatus,
                field_name="overrideStatus",
                allowed=TENANT_PARAMETER_OVERRIDE_STATUSES,
            )
            typed_defaults = coerce_parameter_value(
                data_type=parameter.data_type,
                text_value=override_payload.defaultTextValue,
                number_value=override_payload.defaultNumberValue,
                boolean_value=override_payload.defaultBooleanValue,
                option_value=override_payload.defaultOptionCode,
                min_number_value=parameter.min_number_value,
                max_number_value=parameter.max_number_value,
                allowed_option_codes={
                    option.code for option in (parameter.options or []) if option.is_active
                },
                parameter_code=parameter.code,
            ) if any(
                value is not None
                for value in (
                    override_payload.defaultTextValue,
                    override_payload.defaultNumberValue,
                    override_payload.defaultBooleanValue,
                    override_payload.defaultOptionCode,
                )
            ) else {
                "value_text": None,
                "value_number": None,
                "value_boolean": None,
                "value_option_code": None,
            }
            if typed_defaults["value_option_code"] is not None:
                allowed_option_codes = {
                    option.code for option in (parameter.options or []) if option.is_active
                }
                if typed_defaults["value_option_code"] not in allowed_option_codes:
                    raise CatalogValidationError(
                        f"Option '{typed_defaults['value_option_code']}' is not valid for parameter '{parameter_code}'."
                    )
            override_payload_rows.append(
                {
                    "id": f"twpo_{uuid4().hex[:10]}",
                    "work_type_parameter_id": parameter.id,
                    "override_status": override_status,
                    "custom_display_name": normalize_optional_name(
                        override_payload.customDisplayName,
                        field_name="customDisplayName",
                    ),
                    "sort_order_override": override_payload.sortOrderOverride,
                    "default_text_value": typed_defaults["value_text"],
                    "default_number_value": typed_defaults["value_number"],
                    "default_boolean_value": typed_defaults["value_boolean"],
                    "default_option_code": typed_defaults["value_option_code"],
                    "updated_by_user_id": updated_by_user_id,
                }
            )

        if override_payload_rows:
            await self.repository.upsert_tenant_parameter_overrides(
                tenant_work_type_setting=updated,
                overrides_payload=override_payload_rows,
            )

        self._validate_unique_extra_parameter_payloads(
            work_type_code=work_type.code,
            extra_payloads=list(getattr(payload, "extraParameters", [])),
        )
        extra_payload_rows: list[dict] = []
        for extra_payload in getattr(payload, "extraParameters", []):
            parameter_code = normalize_machine_code(extra_payload.code, field_name="code")
            parameter_slug = normalize_machine_code(extra_payload.slug, field_name="slug")
            if parameter_code in parameter_map:
                raise CatalogValidationError(
                    f"Tenant extra parameter '{parameter_code}' collides with a global parameter on work type '{work_type.code}'."
                )
            option_codes = {
                normalize_machine_code(option.code, field_name="optionCode")
                for option in extra_payload.enumOptions
            }
            validate_tenant_extra_parameter_definition(
                parameter_code=parameter_code,
                slug=parameter_slug,
                label=extra_payload.label,
                data_type=extra_payload.dataType,
                unit=extra_payload.unit,
                section=extra_payload.section,
                is_required=extra_payload.required,
                status=extra_payload.status,
                vision_extractable=extra_payload.visionExtractable,
                manual_override_allowed=extra_payload.manualOverrideAllowed,
                min_number_value=extra_payload.minNumberValue,
                max_number_value=extra_payload.maxNumberValue,
                default_text_value=extra_payload.defaultTextValue,
                default_number_value=extra_payload.defaultNumberValue,
                default_boolean_value=extra_payload.defaultBooleanValue,
                default_option_code=extra_payload.defaultOptionCode,
                option_codes=option_codes,
            )
            extra_payload_rows.append(
                {
                    "id": f"twep_{uuid4().hex[:10]}",
                    "code": parameter_code,
                    "slug": parameter_slug,
                    "name": extra_payload.label.strip(),
                    "description": normalize_optional_name(extra_payload.description, field_name="description"),
                    "data_type": normalize_enum(
                        extra_payload.dataType,
                        field_name="dataType",
                        allowed=WORK_TYPE_PARAMETER_DATA_TYPES,
                    ),
                    "unit": normalize_optional_name(extra_payload.unit, field_name="unit"),
                    "section": normalize_machine_code(extra_payload.section, field_name="section"),
                    "status": normalize_enum(
                        extra_payload.status,
                        field_name="status",
                        allowed={"active", "disabled"},
                    ),
                    "is_required": extra_payload.required,
                    "sort_order": extra_payload.sortOrder or 100,
                    "min_number_value": extra_payload.minNumberValue,
                    "max_number_value": extra_payload.maxNumberValue,
                    "vision_extractable": extra_payload.visionExtractable,
                    "manual_override_allowed": extra_payload.manualOverrideAllowed,
                    "default_text_value": extra_payload.defaultTextValue,
                    "default_number_value": extra_payload.defaultNumberValue,
                    "default_boolean_value": extra_payload.defaultBooleanValue,
                    "default_option_code": extra_payload.defaultOptionCode,
                    "updated_by_user_id": updated_by_user_id,
                    "options": [
                        {
                            "id": f"twepo_{uuid4().hex[:10]}",
                            "code": normalize_machine_code(option.code, field_name="optionCode"),
                            "label": option.label.strip(),
                            "sort_order": option.sortOrder or 100,
                            "is_active": option.isActive,
                        }
                        for option in extra_payload.enumOptions
                    ],
                }
            )

        if extra_payload_rows:
            await self.repository.upsert_tenant_extra_parameters(
                tenant_work_type_setting=updated,
                extra_parameters_payload=extra_payload_rows,
            )

        self.resolution_service.invalidate(
            organization_id=organization_id,
            work_type_code=work_type.code,
        )
        await self._invalidate_tenant_effective_cache(
            organization_id=organization_id,
            work_type_codes={normalized_code, work_type.code},
        )
        resolved = await self.resolution_service.resolve_for_work_type(
            organization_id=organization_id,
            work_type_code=work_type.code,
        )
        try:
            return self._to_effective_read(resolved)
        except CatalogValidationError:
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="work_catalog.upsert_tenant_setting",
                reason="invalid_effective_configuration",
            )
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            self._observe_operation(
                operation="work_catalog.upsert_tenant_setting",
                started_at=started_at,
                outcome=outcome,
            )

    def _validate_work_item_payload(self, payload: ProjectWorkItemCreate) -> None:
        normalize_enum(payload.status, field_name="status", allowed=PROJECT_WORK_ITEM_STATUSES)
        normalize_runtime_source_type(payload.sourceType, field_name="sourceType")

    @staticmethod
    def _project_work_item_value_from_definition(
        *,
        parameter: ResolvedParameterDefinition,
        source_type: str,
        typed_values: dict[str, object],
        source_confidence: float | None = None,
        source_detection_id: str | None = None,
        operator_note: str | None = None,
        confirmation_status: str | None = None,
        confirmed_by_user_id: str | None = None,
        confirmed_at: datetime | None = None,
    ) -> ProjectWorkItemValue:
        normalized_source_type = normalize_runtime_source_type(source_type, field_name="sourceType")
        return ProjectWorkItemValue(
            id=f"pwiv_{uuid4().hex[:10]}",
            work_type_parameter_id=parameter.work_type_parameter_id,
            tenant_work_type_extra_parameter_id=parameter.tenant_extra_parameter_id,
            source_detection_id=source_detection_id,
            source_type=normalized_source_type,
            source_confidence=source_confidence,
            confirmation_status=confirmation_status or _initial_confirmation_status_for_source(normalized_source_type),
            confirmed_by_user_id=confirmed_by_user_id,
            confirmed_at=confirmed_at,
            operator_note=operator_note,
            resolved_parameter_scope=parameter.parameter_scope,
            resolved_parameter_code=parameter.code,
            resolved_parameter_name=parameter.effective_label,
            resolved_data_type=parameter.data_type,
            resolved_unit=parameter.unit,
            **typed_values,
        )

    def _build_value_rows(
        self,
        *,
        resolved: ResolvedTenantWorkTypeConfiguration,
        value_inputs: list[ProjectWorkItemValueInput],
    ) -> list[ProjectWorkItemValue]:
        parameter_specs = resolved.parameter_by_code()
        rows: list[ProjectWorkItemValue] = []
        seen_codes: set[str] = set()

        for value_input in value_inputs:
            parameter_code = normalize_machine_code(value_input.parameterCode, field_name="parameterCode")
            if parameter_code in seen_codes:
                raise CatalogValidationError(f"Duplicate parameterCode '{parameter_code}' in payload.")
            parameter_spec = parameter_specs.get(parameter_code)
            if parameter_spec is None:
                raise CatalogValidationError(
                    f"Parameter '{parameter_code}' is not defined for work type '{resolved.work_type.code}'."
                )
            if not parameter_spec.enabled:
                raise CatalogValidationError(
                    f"Parameter '{parameter_code}' is disabled for this tenant."
                )
            normalized_source_type = normalize_runtime_source_type(
                value_input.sourceType,
                field_name="sourceType",
            )
            if normalized_source_type == "manual" and not parameter_spec.manual_override_allowed:
                raise CatalogValidationError(
                    f"Parameter '{parameter_code}' does not allow manual overrides."
                )
            if normalized_source_type == "vision" and not parameter_spec.vision_extractable:
                raise CatalogValidationError(
                    f"Parameter '{parameter_code}' is not marked as vision extractable."
                )
            typed_values = coerce_parameter_value(
                data_type=parameter_spec.data_type,
                text_value=value_input.textValue,
                number_value=value_input.numberValue,
                boolean_value=value_input.booleanValue,
                option_value=value_input.optionValue,
                min_number_value=parameter_spec.min_number_value,
                max_number_value=parameter_spec.max_number_value,
                allowed_option_codes=parameter_spec.allowed_option_codes or None,
                parameter_code=parameter_code,
            )
            rows.append(
                self._project_work_item_value_from_definition(
                    parameter=parameter_spec,
                    source_type=normalized_source_type,
                    typed_values=typed_values,
                    source_confidence=value_input.sourceConfidence,
                    source_detection_id=value_input.sourceDetectionId,
                    operator_note=normalize_optional_name(value_input.operatorNote, field_name="operatorNote"),
                )
            )
            seen_codes.add(parameter_code)

        for parameter in resolved.parameters:
            if not parameter.enabled or parameter.code in seen_codes or not parameter.has_default():
                continue
            typed_values = coerce_parameter_value(
                data_type=parameter.data_type,
                text_value=parameter.default_text_value,
                number_value=parameter.default_number_value,
                boolean_value=parameter.default_boolean_value,
                option_value=parameter.default_option_code,
                min_number_value=parameter.min_number_value,
                max_number_value=parameter.max_number_value,
                allowed_option_codes=parameter.allowed_option_codes or None,
                parameter_code=parameter.code,
            )
            rows.append(
                self._project_work_item_value_from_definition(
                    parameter=parameter,
                    source_type="default",
                    typed_values=typed_values,
                )
            )
            seen_codes.add(parameter.code)

        missing_required_codes = [
            parameter.code
            for parameter in resolved.parameters
            if parameter.enabled and parameter.required and parameter.code not in seen_codes
        ]
        if missing_required_codes:
            raise CatalogValidationError(
                f"Missing required parameters: {', '.join(sorted(missing_required_codes))}."
            )

        return rows

    @staticmethod
    def _value_input_from_existing_row(value: ProjectWorkItemValue) -> ProjectWorkItemValueInput:
        return ProjectWorkItemValueInput(
            parameterCode=value.resolved_parameter_code,
            textValue=value.value_text,
            numberValue=_as_float(value.value_number),
            booleanValue=value.value_boolean,
            optionValue=value.value_option_code,
            sourceType=value.source_type,
            sourceConfidence=_as_float(value.source_confidence),
            sourceDetectionId=value.source_detection_id,
            operatorNote=value.operator_note,
        )

    async def _validate_source_references(
        self,
        *,
        project_id: str,
        organization_id: str,
        project_work_item: ProjectWorkItem | None,
        value_inputs: list[ProjectWorkItemValueInput],
    ) -> None:
        for value_input in value_inputs:
            if value_input.sourceDetectionId is None:
                continue
            detection = await self.repository.get_vision_detection(
                project_id,
                value_input.sourceDetectionId,
                organization_id=organization_id,
            )
            if detection is None:
                raise WorkCatalogNotFoundError(
                    f"Vision detection '{value_input.sourceDetectionId}' was not found in this project."
                )
            if project_work_item is not None and detection.project_work_item_id not in (None, project_work_item.id):
                raise CatalogValidationError(
                    f"Vision detection '{value_input.sourceDetectionId}' belongs to a different work item."
                )

    def _merge_value_inputs(
        self,
        *,
        existing_values: list[ProjectWorkItemValue],
        incoming_values: list[ProjectWorkItemValueInput],
    ) -> list[ProjectWorkItemValueInput]:
        existing_by_code = {
            value.resolved_parameter_code: self._value_input_from_existing_row(value)
            for value in existing_values
        }
        for incoming in incoming_values:
            normalized_code = normalize_machine_code(incoming.parameterCode, field_name="parameterCode")
            existing = next(
                (value for value in existing_values if value.resolved_parameter_code == normalized_code),
                None,
            )
            incoming_source = normalize_runtime_source_type(incoming.sourceType, field_name="sourceType")
            if existing is None:
                existing_by_code[normalized_code] = incoming
                continue

            existing_source = normalize_runtime_source_type(existing.source_type, field_name="sourceType")
            existing_confidence = _as_float(existing.source_confidence) or 0.0
            incoming_confidence = incoming.sourceConfidence or 0.0
            if incoming_source == "manual":
                existing_by_code[normalized_code] = incoming
                continue
            if existing.confirmation_status in {"confirmed", "corrected"} and existing_source == "manual":
                continue
            if incoming_source == "default":
                existing_by_code.setdefault(normalized_code, incoming)
                continue
            if incoming_source == "imported":
                if existing_source in {"default", "vision", "imported"} and existing.confirmation_status != "corrected":
                    existing_by_code[normalized_code] = incoming
                continue
            if incoming_source == "vision":
                if existing_source == "manual" or existing.confirmation_status in {"confirmed", "corrected"}:
                    continue
                if existing_source == "default" or incoming_confidence >= existing_confidence:
                    existing_by_code[normalized_code] = incoming
                continue

            existing_by_code[normalized_code] = incoming

        return list(existing_by_code.values())

    async def get_project_work_item_effective_configuration(
        self,
        *,
        project_id: str,
        organization_id: str,
        work_type_code: str,
    ) -> ProjectWorkItemEffectiveConfigurationRead:
        started_at = perf_counter()
        outcome = "success"
        try:
            project = await self.repository.get_project_in_org(project_id, organization_id)
            if project is None:
                raise WorkCatalogNotFoundError("Project was not found.")
            resolved = await self.resolution_service.resolve_for_work_type(
                organization_id=organization_id,
                work_type_code=work_type_code,
            )
            effective = self._to_effective_read(resolved, case_status=project.status)
            return self._project_work_item_effective_configuration_read(
                project_id=project_id,
                case_status=project.status,
                effective=effective,
            )
        except LookupError as exc:
            outcome = "not_found"
            raise WorkCatalogNotFoundError(str(exc)) from exc
        except WorkCatalogNotFoundError:
            outcome = "not_found"
            raise
        except CatalogValidationError:
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="work_catalog.get_project_work_item_effective_configuration",
                reason="invalid_effective_configuration",
            )
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            self._observe_operation(
                operation="work_catalog.get_project_work_item_effective_configuration",
                started_at=started_at,
                outcome=outcome,
            )

    async def get_project_work_item_detail(
        self,
        *,
        project_id: str,
        project_work_item_id: str,
        organization_id: str,
    ) -> ProjectWorkItemDetailRead:
        started_at = perf_counter()
        outcome = "success"
        work_item = await self.repository.get_project_work_item(
            project_id,
            project_work_item_id,
            organization_id=organization_id,
        )
        if work_item is None:
            outcome = "not_found"
            self._observe_operation(
                operation="work_catalog.get_project_work_item_detail",
                started_at=started_at,
                outcome=outcome,
            )
            raise WorkCatalogNotFoundError("Project work item was not found.")
        work_item_read = self._project_work_item_read(work_item)
        effective_configuration = await self.get_project_work_item_effective_configuration(
            project_id=project_id,
            organization_id=organization_id,
            work_type_code=work_item.resolved_work_type_code,
        )
        try:
            return ProjectWorkItemDetailRead(
                workItem=work_item_read,
                effectiveConfiguration=effective_configuration,
                workflow=self._project_work_item_workflow_read(
                    work_item=work_item_read,
                    effective_configuration=effective_configuration,
                ),
            )
        finally:
            self._observe_operation(
                operation="work_catalog.get_project_work_item_detail",
                started_at=started_at,
                outcome=outcome,
            )

    async def update_project_work_item_values(
        self,
        *,
        project_id: str,
        project_work_item_id: str,
        organization_id: str,
        values: list[ProjectWorkItemValueInput],
    ) -> ProjectWorkItemRead:
        project = await self.repository.get_project_in_org(project_id, organization_id)
        if project is None:
            raise WorkCatalogNotFoundError("Project was not found.")
        work_item = await self.repository.get_project_work_item(
            project_id,
            project_work_item_id,
            organization_id=organization_id,
        )
        if work_item is None:
            raise WorkCatalogNotFoundError("Project work item was not found.")
        self._assert_work_type_allowed_in_case_status(
            work_type_code=work_item.resolved_work_type_code,
            case_status=project.status,
            operation="updated",
        )
        await self._validate_source_references(
            project_id=project_id,
            organization_id=organization_id,
            project_work_item=work_item,
            value_inputs=values,
        )
        merged_inputs = self._merge_value_inputs(
            existing_values=list(work_item.values or []),
            incoming_values=values,
        )
        work_type = await self._get_work_type(work_item.resolved_work_type_code)
        if work_type is None:
            raise WorkCatalogNotFoundError("Work type was not found.")
        resolved = await self.resolution_service.resolve_for_work_type(
            organization_id=organization_id,
            work_type_code=work_type.code,
        )
        value_rows = self._build_value_rows(
            resolved=resolved,
            value_inputs=merged_inputs,
        )
        work_item.confirmation_status = _derive_work_item_confirmation_status(value_rows)
        if work_item.confirmation_status == "confirmed":
            work_item.confirmed_at = datetime.now(UTC)
        updated = await self.repository.replace_project_work_item_values(
            project_work_item=work_item,
            values=value_rows,
        )
        return self._project_work_item_read(updated)

    async def merge_project_work_item_values(
        self,
        *,
        project_id: str,
        project_work_item_id: str,
        organization_id: str,
        values: list[ProjectWorkItemValueInput],
    ) -> ProjectWorkItemRead:
        return await self.update_project_work_item_values(
            project_id=project_id,
            project_work_item_id=project_work_item_id,
            organization_id=organization_id,
            values=values,
        )

    async def confirm_project_work_item_values(
        self,
        *,
        project_id: str,
        project_work_item_id: str,
        organization_id: str,
        confirmations: list[ProjectWorkItemValueConfirmationInput],
        confirmed_by_user_id: str | None,
    ) -> ProjectWorkItemRead:
        project = await self.repository.get_project_in_org(project_id, organization_id)
        if project is None:
            raise WorkCatalogNotFoundError("Project was not found.")
        work_item = await self.repository.get_project_work_item(
            project_id,
            project_work_item_id,
            organization_id=organization_id,
        )
        if work_item is None:
            raise WorkCatalogNotFoundError("Project work item was not found.")
        self._assert_work_type_allowed_in_case_status(
            work_type_code=work_item.resolved_work_type_code,
            case_status=project.status,
            operation="confirmed",
        )
        work_type = await self._get_work_type(work_item.resolved_work_type_code)
        if work_type is None:
            raise WorkCatalogNotFoundError("Work type was not found.")
        resolved = await self.resolution_service.resolve_for_work_type(
            organization_id=organization_id,
            work_type_code=work_type.code,
        )
        value_by_code = {value.resolved_parameter_code: value for value in (work_item.values or [])}
        parameter_specs = resolved.parameter_by_code()
        confirmation_time = datetime.now(UTC)

        for confirmation in confirmations:
            parameter_code = normalize_machine_code(confirmation.parameterCode, field_name="parameterCode")
            action = normalize_machine_code(confirmation.action, field_name="action")
            value = value_by_code.get(parameter_code)
            parameter_spec = parameter_specs.get(parameter_code)
            if value is None or parameter_spec is None:
                raise CatalogValidationError(
                    f"Parameter '{parameter_code}' is not present on project work item '{work_item.id}'."
                )
            if action == "confirm":
                value.confirmation_status = "confirmed"
                value.confirmed_by_user_id = confirmed_by_user_id
                value.confirmed_at = confirmation_time
                if confirmation.operatorNote is not None:
                    value.operator_note = normalize_optional_name(confirmation.operatorNote, field_name="operatorNote")
                continue
            if action != "correct":
                raise CatalogValidationError("action must be one of: confirm, correct.")
            typed_values = coerce_parameter_value(
                data_type=parameter_spec.data_type,
                text_value=confirmation.textValue,
                number_value=confirmation.numberValue,
                boolean_value=confirmation.booleanValue,
                option_value=confirmation.optionValue,
                min_number_value=parameter_spec.min_number_value,
                max_number_value=parameter_spec.max_number_value,
                allowed_option_codes=parameter_spec.allowed_option_codes or None,
                parameter_code=parameter_code,
            )
            value.source_type = "manual"
            value.source_confidence = None
            value.source_detection_id = None
            value.confirmation_status = "corrected"
            value.confirmed_by_user_id = confirmed_by_user_id
            value.confirmed_at = confirmation_time
            value.operator_note = normalize_optional_name(confirmation.operatorNote, field_name="operatorNote")
            value.value_text = typed_values["value_text"]
            value.value_number = typed_values["value_number"]
            value.value_boolean = typed_values["value_boolean"]
            value.value_option_code = typed_values["value_option_code"]

        work_item.confirmation_status = _derive_work_item_confirmation_status(list(work_item.values or []))
        work_item.confirmed_by_user_id = confirmed_by_user_id if work_item.confirmation_status == "confirmed" else None
        work_item.confirmed_at = confirmation_time if work_item.confirmation_status == "confirmed" else None
        updated = await self.repository.save_project_work_item(project_work_item=work_item)
        return self._project_work_item_read(updated)

    async def create_project_work_item(
        self,
        *,
        project_id: str,
        organization_id: str,
        payload: ProjectWorkItemCreate,
        created_by_user_id: str | None,
    ) -> ProjectWorkItemRead:
        self._validate_work_item_payload(payload)
        project = await self.repository.get_project_in_org(project_id, organization_id)
        if project is None:
            raise WorkCatalogNotFoundError("Project was not found.")
        await self._validate_source_references(
            project_id=project_id,
            organization_id=organization_id,
            project_work_item=None,
            value_inputs=payload.values,
        )

        resolved = await self.resolution_service.resolve_for_work_type(
            organization_id=organization_id,
            work_type_code=payload.workTypeCode,
        )
        effective = self._to_effective_read(resolved)
        if not resolved.is_enabled:
            raise CatalogValidationError(
                f"Work type '{resolved.work_type.code}' is disabled for this tenant."
            )
        self._assert_work_type_allowed_in_case_status(
            work_type_code=resolved.work_type.code,
            case_status=project.status,
            operation="created",
        )
        work_type = resolved.work_type
        setting = resolved.tenant_setting
        item_sequence = await self.repository.get_next_item_sequence(project_id, work_type.id)
        values = self._build_value_rows(
            resolved=resolved,
            value_inputs=payload.values,
        )
        confirmation_status = _derive_work_item_confirmation_status(values)
        work_item = ProjectWorkItem(
            id=f"pwi_{uuid4().hex[:10]}",
            project_id=project.id,
            organization_id=organization_id,
            work_type_id=work_type.id,
            tenant_work_type_setting_id=setting.id if setting else None,
            analysis_profile_id=resolved.analysis_profile.id if resolved.analysis_profile else None,
            catalog_pricing_profile_id=(
                resolved.catalog_pricing_profile.id
                if resolved.catalog_pricing_profile
                else None
            ),
            tenant_pricing_profile_id=resolved.tenant_pricing_profile_id,
            title=normalize_optional_name(payload.title, field_name="title") or effective.effectiveDisplayName,
            status=normalize_enum(payload.status, field_name="status", allowed=PROJECT_WORK_ITEM_STATUSES),
            source_type=normalize_runtime_source_type(payload.sourceType, field_name="sourceType"),
            confirmation_status=confirmation_status,
            item_sequence=item_sequence,
            resolved_display_name=effective.effectiveDisplayName,
            resolved_work_type_code=effective.code,
            resolved_category_code=effective.category.code,
            resolved_analysis_profile_code=effective.analysisProfile.code if effective.analysisProfile else None,
            resolved_analysis_profile_version=effective.analysisProfile.profileVersion if effective.analysisProfile else None,
            resolved_catalog_pricing_profile_code=(
                effective.catalogPricingProfile.code if effective.catalogPricingProfile else None
            ),
            resolved_catalog_pricing_profile_version=(
                effective.catalogPricingProfile.profileVersion if effective.catalogPricingProfile else None
            ),
            resolved_unit=effective.defaultUnit,
            resolved_catalog_version=effective.workTypeVersion,
            resolved_setting_version=resolved.setting_version,
            measured_quantity=payload.measuredQuantity,
            measured_unit=payload.measuredUnit or effective.defaultUnit,
            notes=normalize_optional_name(payload.notes, field_name="notes"),
            confirmed_by_user_id=created_by_user_id if confirmation_status == "confirmed" else None,
            confirmed_at=datetime.now(UTC) if confirmation_status == "confirmed" else None,
            created_by_user_id=created_by_user_id,
            values=values,
        )
        created = await self.repository.create_project_work_item(work_item=work_item)
        return self._project_work_item_read(created)

    async def replace_project_work_item_values(
        self,
        *,
        project_id: str,
        project_work_item_id: str,
        organization_id: str,
        values: list[ProjectWorkItemValueInput],
    ) -> ProjectWorkItemRead:
        project = await self.repository.get_project_in_org(project_id, organization_id)
        if project is None:
            raise WorkCatalogNotFoundError("Project was not found.")
        work_item = await self.repository.get_project_work_item(
            project_id,
            project_work_item_id,
            organization_id=organization_id,
        )
        if work_item is None:
            raise WorkCatalogNotFoundError("Project work item was not found.")
        self._assert_work_type_allowed_in_case_status(
            work_type_code=work_item.resolved_work_type_code,
            case_status=project.status,
            operation="replaced",
        )
        await self._validate_source_references(
            project_id=project_id,
            organization_id=organization_id,
            project_work_item=work_item,
            value_inputs=values,
        )
        work_type = await self._get_work_type(work_item.resolved_work_type_code)
        if work_type is None:
            raise WorkCatalogNotFoundError("Work type was not found.")
        resolved = await self.resolution_service.resolve_for_work_type(
            organization_id=organization_id,
            work_type_code=work_type.code,
        )
        value_rows = self._build_value_rows(
            resolved=resolved,
            value_inputs=values,
        )
        work_item.confirmation_status = _derive_work_item_confirmation_status(value_rows)
        if work_item.confirmation_status == "confirmed":
            work_item.confirmed_at = datetime.now(UTC)
        updated = await self.repository.replace_project_work_item_values(
            project_work_item=work_item,
            values=value_rows,
        )
        return self._project_work_item_read(updated)

    def _project_work_item_read(self, work_item) -> ProjectWorkItemRead:
        return ProjectWorkItemRead(
            id=work_item.id,
            projectId=work_item.project_id,
            workTypeCode=work_item.resolved_work_type_code,
            categoryCode=work_item.resolved_category_code,
            title=work_item.title,
            status=work_item.status,
            sourceType=work_item.source_type,
            confirmationStatus=work_item.confirmation_status,
            itemSequence=work_item.item_sequence,
            measuredQuantity=_as_float(work_item.measured_quantity),
            measuredUnit=work_item.measured_unit,
            defaultUnit=work_item.resolved_unit,
            workTypeVersion=work_item.resolved_catalog_version,
            settingVersion=work_item.resolved_setting_version,
            analysisProfileCode=work_item.resolved_analysis_profile_code,
            analysisProfileVersion=work_item.resolved_analysis_profile_version,
            catalogPricingProfileCode=work_item.resolved_catalog_pricing_profile_code,
            catalogPricingProfileVersion=work_item.resolved_catalog_pricing_profile_version,
            tenantPricingProfileId=work_item.tenant_pricing_profile_id,
            notes=work_item.notes,
            confirmedByUserId=work_item.confirmed_by_user_id,
            confirmedAt=work_item.confirmed_at,
            values=[
                ProjectWorkItemValueRead(
                    parameterDefinitionId=value.work_type_parameter_id or value.tenant_work_type_extra_parameter_id or "",
                    parameterScope=value.resolved_parameter_scope,
                    parameterCode=value.resolved_parameter_code,
                    parameterSlug=(
                        value.parameter.slug
                        if value.parameter
                        else value.tenant_extra_parameter.slug
                        if value.tenant_extra_parameter
                        else value.resolved_parameter_code
                    ),
                    parameterLabel=value.resolved_parameter_name,
                    parameterSection=(
                        value.parameter.section
                        if value.parameter
                        else value.tenant_extra_parameter.section
                        if value.tenant_extra_parameter
                        else None
                    ),
                    dataType=value.resolved_data_type,
                    unit=value.resolved_unit,
                    visionExtractable=(
                        value.parameter.vision_extractable
                        if value.parameter
                        else value.tenant_extra_parameter.vision_extractable
                        if value.tenant_extra_parameter
                        else None
                    ),
                    manualOverrideAllowed=(
                        value.parameter.manual_override_allowed
                        if value.parameter
                        else value.tenant_extra_parameter.manual_override_allowed
                        if value.tenant_extra_parameter
                        else None
                    ),
                    textValue=value.value_text,
                    numberValue=_as_float(value.value_number),
                    booleanValue=value.value_boolean,
                    optionValue=value.value_option_code,
                    sourceType=value.source_type,
                    sourceConfidence=_as_float(value.source_confidence),
                    sourceDetectionId=value.source_detection_id,
                    confirmationStatus=value.confirmation_status,
                    confirmedByUserId=value.confirmed_by_user_id,
                    confirmedAt=value.confirmed_at,
                    operatorNote=value.operator_note,
                    updatedAt=value.updated_at,
                )
                for value in (work_item.values or [])
            ],
            detections=[self._vision_detection_read(detection) for detection in (work_item.detections or [])],
            createdAt=work_item.created_at,
            updatedAt=work_item.updated_at,
        )

    async def list_project_work_items(self, *, project_id: str, organization_id: str) -> list[ProjectWorkItemRead]:
        project = await self.repository.get_project_in_org(project_id, organization_id)
        if project is None:
            raise WorkCatalogNotFoundError("Project was not found.")
        items = await self.repository.list_project_work_items(project_id, organization_id=organization_id)
        return [self._project_work_item_read(item) for item in items]

    def _vision_detection_read(self, detection) -> VisionDetectionRead:
        geometry = None
        if detection.geometry_json:
            try:
                geometry = json.loads(detection.geometry_json)
            except json.JSONDecodeError:
                geometry = None
        return VisionDetectionRead(
            id=detection.id,
            detectionKey=detection.detection_key,
            workTypeCode=detection.resolved_work_type_code,
            status=detection.status,
            referencePhotoId=detection.reference_photo_id,
            confidenceScore=_as_float(detection.confidence_score),
            rawLabel=detection.raw_label,
            rawValue=detection.raw_value,
            detectedQuantity=_as_float(detection.detected_quantity),
            detectedUnit=detection.detected_unit,
            geometryType=detection.geometry_type,
            bboxLeft=_as_float(detection.bbox_left),
            bboxTop=_as_float(detection.bbox_top),
            bboxRight=_as_float(detection.bbox_right),
            bboxBottom=_as_float(detection.bbox_bottom),
            geometry=geometry,
            sourceProvider=detection.source_provider,
            sourceModel=detection.source_model,
            sourceModelVersion=detection.source_model_version,
            createdAt=detection.created_at,
        )

    async def create_vision_detection(
        self,
        *,
        project_id: str,
        project_work_item_id: str,
        organization_id: str,
        payload: VisionDetectionCreate,
        created_by_user_id: str | None,
    ) -> VisionDetectionRead:
        project = await self.repository.get_project_in_org(project_id, organization_id)
        if project is None:
            raise WorkCatalogNotFoundError("Project was not found.")
        project_work_item = await self.repository.get_project_work_item(
            project_id,
            project_work_item_id,
            organization_id=organization_id,
        )
        if project_work_item is None:
            raise WorkCatalogNotFoundError("Project work item was not found.")
        self._assert_work_type_allowed_in_case_status(
            work_type_code=project_work_item.resolved_work_type_code,
            case_status=project.status,
            operation="annotated",
        )
        if payload.referencePhotoId:
            photo = await self.repository.get_project_photo_in_project(
                project_id,
                payload.referencePhotoId,
                organization_id=organization_id,
            )
            if photo is None:
                raise WorkCatalogNotFoundError("Reference photo was not found in this project.")
        normalized_detection_status = normalize_enum(
            payload.status,
            field_name="status",
            allowed=VISION_DETECTION_STATUSES,
        )
        effective = await self.get_effective_work_type(organization_id, payload.workTypeCode)
        if effective.code != project_work_item.resolved_work_type_code:
            raise CatalogValidationError(
                "Vision detection workTypeCode must match the target project work item."
            )
        work_type = await self._get_work_type(effective.code)
        if work_type is None:
            raise WorkCatalogNotFoundError("Work type was not found.")

        detection = VisionDetection(
            id=f"vd_{uuid4().hex[:10]}",
            project_id=project.id,
            organization_id=organization_id,
            project_work_item_id=project_work_item.id,
            analysis_job_id=payload.analysisJobId,
            work_type_id=work_type.id,
            analysis_profile_id=project_work_item.analysis_profile_id,
            reference_photo_id=payload.referencePhotoId,
            detection_key=normalize_machine_code(payload.detectionKey, field_name="detectionKey"),
            status=normalized_detection_status,
            confidence_score=payload.confidenceScore,
            raw_label=normalize_optional_name(payload.rawLabel, field_name="rawLabel"),
            raw_value=normalize_optional_name(payload.rawValue, field_name="rawValue"),
            detected_quantity=payload.detectedQuantity,
            detected_unit=payload.detectedUnit,
            geometry_type=normalize_optional_name(payload.geometryType, field_name="geometryType"),
            bbox_left=payload.bboxLeft,
            bbox_top=payload.bboxTop,
            bbox_right=payload.bboxRight,
            bbox_bottom=payload.bboxBottom,
            geometry_json=self.repository.serialize_geometry(payload.geometry),
            resolved_work_type_code=effective.code,
            resolved_analysis_profile_code=project_work_item.resolved_analysis_profile_code,
            resolved_analysis_profile_version=project_work_item.resolved_analysis_profile_version,
            source_provider=normalize_optional_name(payload.sourceProvider, field_name="sourceProvider"),
            source_model=normalize_optional_name(payload.sourceModel, field_name="sourceModel"),
            source_model_version=normalize_optional_name(payload.sourceModelVersion, field_name="sourceModelVersion"),
            created_by_user_id=created_by_user_id,
        )
        created = await self.repository.create_vision_detection(detection)
        return self._vision_detection_read(created)
