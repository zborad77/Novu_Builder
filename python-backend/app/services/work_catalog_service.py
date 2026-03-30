from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

from app.models.work_catalog import (
    ProjectWorkItem,
    ProjectWorkItemValue,
    TenantWorkTypeParameterOverride,
    VisionDetection,
    WorkType,
    WorkTypeParameter,
)
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.schemas.work_catalog import (
    AnalysisProfileRead,
    CatalogPricingProfileRead,
    EffectiveWorkTypeRead,
    ProjectWorkItemCreate,
    ProjectWorkItemRead,
    ProjectWorkItemValueInput,
    ProjectWorkItemValueRead,
    TenantWorkTypeParameterOverrideRead,
    TenantWorkTypeParameterOverrideUpsert,
    TenantWorkTypeSettingRead,
    TenantWorkTypeSettingUpsert,
    TenantWorkTypeSettingWithParametersUpsert,
    VisionDetectionCreate,
    VisionDetectionRead,
    WorkCategoryRead,
    WorkTypeParameterOptionRead,
    WorkTypeParameterRead,
    WorkTypeParameterSectionRead,
)
from app.work_catalog.domain import (
    CATALOG_PRICING_STRATEGIES,
    MATERIAL_PRICING_SOURCES,
    PROJECT_WORK_ITEM_SOURCE_TYPES,
    PROJECT_WORK_ITEM_STATUSES,
    TENANT_WORK_TYPE_SETTING_STATUSES,
    VISION_DETECTION_STATUSES,
    WORK_TYPE_PARAMETER_DATA_TYPES,
    WORK_TYPE_STATES,
    CatalogValidationError,
    coerce_parameter_value,
    normalize_enum,
    normalize_machine_code,
    normalize_optional_name,
    section_label,
    section_sort_order,
)


class WorkCatalogNotFoundError(LookupError):
    """Raised when a requested catalog object does not exist in scope."""


def _as_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _analysis_profile_read(profile) -> AnalysisProfileRead | None:
    if profile is None:
        return None
    return AnalysisProfileRead(
        code=profile.code,
        name=profile.name,
        providerFamily=profile.provider_family,
        taskType=profile.task_type,
        outputContractVersion=profile.output_contract_version,
        confidenceThreshold=_as_float(profile.confidence_threshold),
        maxDetectionsPerPhoto=profile.max_detections_per_photo,
        profileVersion=profile.profile_version,
    )


def _catalog_pricing_profile_read(profile) -> CatalogPricingProfileRead | None:
    if profile is None:
        return None
    return CatalogPricingProfileRead(
        code=profile.code,
        name=profile.name,
        pricingStrategy=profile.pricing_strategy,
        laborRateSource=profile.labor_rate_source,
        materialPricingSource=profile.material_pricing_source,
        defaultMarginPct=_as_float(profile.default_margin_pct),
        defaultMarkupPct=_as_float(profile.default_markup_pct),
        profileVersion=profile.profile_version,
    )


def _parameter_read(
    parameter: WorkTypeParameter,
    override: TenantWorkTypeParameterOverride | None = None,
) -> WorkTypeParameterRead:
    override_status = override.override_status if override else None
    is_enabled = override_status != "hidden"
    is_required = parameter.is_required
    if override_status == "required":
        is_required = True
    elif override_status == "optional":
        is_required = False
    return WorkTypeParameterRead(
        parameterDefinitionId=parameter.id,
        code=parameter.code,
        slug=parameter.slug,
        label=parameter.name,
        effectiveLabel=override.custom_display_name if override and override.custom_display_name else parameter.name,
        description=parameter.description,
        dataType=parameter.data_type,
        unit=parameter.unit,
        section=parameter.section or "optional_notes",
        sectionLabel=section_label(parameter.section),
        required=is_required,
        enabled=is_enabled,
        sortOrder=override.sort_order_override if override and override.sort_order_override is not None else parameter.sort_order,
        overrideStatus=override_status,
        settingVersion=override.config_version if override else None,
        minNumberValue=_as_float(parameter.min_number_value),
        maxNumberValue=_as_float(parameter.max_number_value),
        visionExtractable=parameter.vision_extractable,
        manualOverrideAllowed=parameter.manual_override_allowed,
        defaultTextValue=override.default_text_value if override and override.default_text_value is not None else parameter.default_text_value,
        defaultNumberValue=_as_float(
            override.default_number_value if override and override.default_number_value is not None else parameter.default_number_value
        ),
        defaultBooleanValue=override.default_boolean_value if override and override.default_boolean_value is not None else parameter.default_boolean_value,
        defaultOptionCode=override.default_option_code if override and override.default_option_code is not None else parameter.default_option_code,
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


def _tenant_setting_read(setting) -> TenantWorkTypeSettingRead | None:
    if setting is None:
        return None
    return TenantWorkTypeSettingRead(
        status=setting.status,
        customDisplayName=setting.custom_display_name,
        analysisProfileCode=setting.analysis_profile.code if setting.analysis_profile else None,
        catalogPricingProfileCode=setting.catalog_pricing_profile.code if setting.catalog_pricing_profile else None,
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


class WorkCatalogService:
    def __init__(self, repository: WorkCatalogRepository):
        self.repository = repository

    @staticmethod
    def _effective_parameter_specs(
        work_type: WorkType,
        parameter_overrides: dict[str, TenantWorkTypeParameterOverride],
    ) -> dict[str, dict]:
        specs: dict[str, dict] = {}
        for parameter in (work_type.parameters or []):
            override = parameter_overrides.get(parameter.id)
            override_status = override.override_status if override else "inherited"
            is_enabled = override_status != "hidden"
            is_required = parameter.is_required
            if override_status == "required":
                is_required = True
            elif override_status == "optional":
                is_required = False
            specs[parameter.code] = {
                "parameter": parameter,
                "override": override,
                "is_enabled": is_enabled,
                "is_required": is_required,
            }
        return specs

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

    def _to_effective_read(
        self,
        work_type: WorkType,
        setting,
        parameter_overrides: dict[str, TenantWorkTypeParameterOverride],
    ) -> EffectiveWorkTypeRead:
        category = work_type.category
        effective_analysis_profile = setting.analysis_profile if setting and setting.analysis_profile else work_type.default_analysis_profile
        effective_pricing_profile = (
            setting.catalog_pricing_profile
            if setting and setting.catalog_pricing_profile
            else work_type.default_catalog_pricing_profile
        )
        is_enabled = work_type.is_active and work_type.state == "active"
        if setting and setting.status == "disabled":
            is_enabled = False
        parameter_reads = []
        for parameter in (work_type.parameters or []):
            override = parameter_overrides.get(parameter.id)
            parameter_reads.append(_parameter_read(parameter, override))
        parameter_reads.sort(
            key=lambda item: (
                section_sort_order(item.section),
                item.sortOrder,
                item.code,
            )
        )

        return EffectiveWorkTypeRead(
            code=work_type.code,
            slug=work_type.slug,
            name=work_type.name,
            description=work_type.description,
            state=work_type.state,
            isEnabled=is_enabled,
            effectiveDisplayName=(
                setting.custom_display_name
                if setting and setting.custom_display_name
                else work_type.name
            ),
            category=WorkCategoryRead(
                code=category.code,
                slug=category.slug,
                name=category.name,
                description=category.description,
                sortOrder=category.sort_order,
                catalogVersion=category.catalog_version,
            ),
            defaultUnit=work_type.default_unit,
            measurementKind=work_type.measurement_kind,
            workTypeVersion=work_type.catalog_version,
            settingVersion=setting.config_version if setting else None,
            analysisProfile=_analysis_profile_read(effective_analysis_profile),
            catalogPricingProfile=_catalog_pricing_profile_read(effective_pricing_profile),
            tenantPricingProfileId=setting.tenant_pricing_profile_id if setting else None,
            parameters=parameter_reads,
            parameterSections=self._build_parameter_sections(parameter_reads),
            tenantSetting=_tenant_setting_read(setting),
            parameterOverrides=[
                _tenant_parameter_override_read(override)
                for override in sorted(
                    parameter_overrides.values(),
                    key=lambda item: (
                        item.sort_order_override if item.sort_order_override is not None else 10_000,
                        item.parameter.code if item.parameter else item.work_type_parameter_id,
                    ),
                )
            ],
        )

    async def list_effective_work_types(self, organization_id: str) -> list[EffectiveWorkTypeRead]:
        work_types = list(await self.repository.list_work_types())
        settings = await self.repository.list_tenant_settings_for_org(
            organization_id,
            work_type_ids=[work_type.id for work_type in work_types],
        )
        parameter_overrides = await self.repository.list_parameter_overrides_for_org(
            organization_id,
            work_type_ids=[work_type.id for work_type in work_types],
        )
        return [
            self._to_effective_read(
                work_type,
                settings.get(work_type.id),
                {
                    parameter.id: parameter_overrides[parameter.id]
                    for parameter in (work_type.parameters or [])
                    if parameter.id in parameter_overrides
                },
            )
            for work_type in work_types
        ]

    async def get_effective_work_type(self, organization_id: str, work_type_code: str) -> EffectiveWorkTypeRead:
        normalized_code = normalize_machine_code(work_type_code, field_name="workTypeCode")
        work_type = await self.repository.get_work_type_by_code(normalized_code)
        if work_type is None:
            raise WorkCatalogNotFoundError(f"Work type '{normalized_code}' was not found.")
        settings = await self.repository.list_tenant_settings_for_org(
            organization_id,
            work_type_ids=[work_type.id],
        )
        parameter_overrides = await self.repository.list_parameter_overrides_for_org(
            organization_id,
            work_type_ids=[work_type.id],
        )
        return self._to_effective_read(
            work_type,
            settings.get(work_type.id),
            {
                parameter.id: parameter_overrides[parameter.id]
                for parameter in (work_type.parameters or [])
                if parameter.id in parameter_overrides
            },
        )

    async def upsert_tenant_setting(
        self,
        *,
        organization_id: str,
        work_type_code: str,
        payload: TenantWorkTypeSettingWithParametersUpsert,
        updated_by_user_id: str | None,
    ) -> EffectiveWorkTypeRead:
        normalized_code = normalize_machine_code(work_type_code, field_name="workTypeCode")
        status = normalize_enum(
            payload.status,
            field_name="status",
            allowed=TENANT_WORK_TYPE_SETTING_STATUSES,
        )
        work_type = await self.repository.get_work_type_by_code(normalized_code)
        if work_type is None:
            raise WorkCatalogNotFoundError(f"Work type '{normalized_code}' was not found.")

        analysis_profile = None
        if payload.analysisProfileCode:
            analysis_profile = await self.repository.get_analysis_profile_by_code(
                normalize_machine_code(payload.analysisProfileCode, field_name="analysisProfileCode")
            )
            if analysis_profile is None:
                raise WorkCatalogNotFoundError("Analysis profile was not found.")

        catalog_pricing_profile = None
        if payload.catalogPricingProfileCode:
            catalog_pricing_profile = await self.repository.get_catalog_pricing_profile_by_code(
                normalize_machine_code(payload.catalogPricingProfileCode, field_name="catalogPricingProfileCode")
            )
            if catalog_pricing_profile is None:
                raise WorkCatalogNotFoundError("Catalog pricing profile was not found.")

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
                allowed={"inherited", "required", "optional", "hidden"},
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
        parameter_overrides = await self.repository.list_parameter_overrides_for_org(
            organization_id,
            work_type_ids=[work_type.id],
        )
        parameter_overrides = {
            parameter.id: parameter_overrides[parameter.id]
            for parameter in (work_type.parameters or [])
            if parameter.id in parameter_overrides
        }
        return self._to_effective_read(work_type, updated, parameter_overrides)

    def _validate_work_item_payload(self, payload: ProjectWorkItemCreate) -> None:
        normalize_enum(payload.status, field_name="status", allowed=PROJECT_WORK_ITEM_STATUSES)
        normalize_enum(payload.sourceType, field_name="sourceType", allowed=PROJECT_WORK_ITEM_SOURCE_TYPES)

    def _build_value_rows(
        self,
        *,
        work_type: WorkType,
        parameter_overrides: dict[str, TenantWorkTypeParameterOverride],
        value_inputs: list[ProjectWorkItemValueInput],
    ) -> list[ProjectWorkItemValue]:
        parameter_specs = self._effective_parameter_specs(work_type, parameter_overrides)
        rows: list[ProjectWorkItemValue] = []
        seen_codes: set[str] = set()

        for value_input in value_inputs:
            parameter_code = normalize_machine_code(value_input.parameterCode, field_name="parameterCode")
            if parameter_code in seen_codes:
                raise CatalogValidationError(f"Duplicate parameterCode '{parameter_code}' in payload.")
            parameter_spec = parameter_specs.get(parameter_code)
            if parameter_spec is None:
                raise CatalogValidationError(
                    f"Parameter '{parameter_code}' is not defined for work type '{work_type.code}'."
                )
            parameter = parameter_spec["parameter"]
            if not parameter_spec["is_enabled"]:
                raise CatalogValidationError(
                    f"Parameter '{parameter_code}' is disabled for this tenant."
                )
            normalized_source_type = normalize_enum(
                value_input.sourceType,
                field_name="sourceType",
                allowed=PROJECT_WORK_ITEM_SOURCE_TYPES,
            )
            if normalized_source_type == "manual" and not parameter.manual_override_allowed:
                raise CatalogValidationError(
                    f"Parameter '{parameter_code}' does not allow manual overrides."
                )
            if normalized_source_type == "vision" and not parameter.vision_extractable:
                raise CatalogValidationError(
                    f"Parameter '{parameter_code}' is not marked as vision extractable."
                )
            allowed_option_codes = {
                option.code for option in (parameter.options or []) if option.is_active
            }
            typed_values = coerce_parameter_value(
                data_type=parameter.data_type,
                text_value=value_input.textValue,
                number_value=value_input.numberValue,
                boolean_value=value_input.booleanValue,
                option_value=value_input.optionValue,
                min_number_value=parameter.min_number_value,
                max_number_value=parameter.max_number_value,
                allowed_option_codes=allowed_option_codes or None,
                parameter_code=parameter_code,
            )

            rows.append(
                ProjectWorkItemValue(
                    id=f"pwiv_{uuid4().hex[:10]}",
                    work_type_parameter_id=parameter.id,
                    source_type=normalized_source_type,
                    resolved_parameter_code=parameter.code,
                    resolved_parameter_name=parameter.name,
                    resolved_data_type=parameter.data_type,
                    resolved_unit=parameter.unit,
                    **typed_values,
                )
            )
            seen_codes.add(parameter_code)

        missing_required_codes = [
            parameter_code
            for parameter_code, parameter_spec in parameter_specs.items()
            if parameter_spec["is_enabled"] and parameter_spec["is_required"] and parameter_code not in seen_codes
        ]
        if missing_required_codes:
            raise CatalogValidationError(
                f"Missing required parameters: {', '.join(sorted(missing_required_codes))}."
            )

        return rows

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

        effective = await self.get_effective_work_type(organization_id, payload.workTypeCode)
        if not effective.isEnabled:
            raise CatalogValidationError(
                f"Work type '{effective.code}' is disabled for this tenant."
            )
        work_type = await self.repository.get_work_type_by_code(effective.code)
        if work_type is None:
            raise WorkCatalogNotFoundError("Work type was not found.")

        settings = await self.repository.list_tenant_settings_for_org(
            organization_id,
            work_type_ids=[work_type.id],
        )
        setting = settings.get(work_type.id)
        parameter_overrides = await self.repository.list_parameter_overrides_for_org(
            organization_id,
            work_type_ids=[work_type.id],
        )
        parameter_overrides = {
            parameter.id: parameter_overrides[parameter.id]
            for parameter in (work_type.parameters or [])
            if parameter.id in parameter_overrides
        }
        item_sequence = await self.repository.get_next_item_sequence(project_id, work_type.id)
        values = self._build_value_rows(
            work_type=work_type,
            parameter_overrides=parameter_overrides,
            value_inputs=payload.values,
        )
        work_item = ProjectWorkItem(
            id=f"pwi_{uuid4().hex[:10]}",
            project_id=project.id,
            organization_id=organization_id,
            work_type_id=work_type.id,
            tenant_work_type_setting_id=setting.id if setting else None,
            analysis_profile_id=setting.analysis_profile_id if setting and setting.analysis_profile_id else work_type.default_analysis_profile_id,
            catalog_pricing_profile_id=(
                setting.catalog_pricing_profile_id
                if setting and setting.catalog_pricing_profile_id
                else work_type.default_catalog_pricing_profile_id
            ),
            tenant_pricing_profile_id=setting.tenant_pricing_profile_id if setting else None,
            title=normalize_optional_name(payload.title, field_name="title") or effective.effectiveDisplayName,
            status=normalize_enum(payload.status, field_name="status", allowed=PROJECT_WORK_ITEM_STATUSES),
            source_type=normalize_enum(payload.sourceType, field_name="sourceType", allowed=PROJECT_WORK_ITEM_SOURCE_TYPES),
            item_sequence=item_sequence,
            resolved_display_name=effective.effectiveDisplayName,
            resolved_work_type_code=effective.code,
            resolved_category_code=effective.category.code,
            resolved_unit=effective.defaultUnit,
            resolved_catalog_version=effective.workTypeVersion,
            resolved_setting_version=effective.settingVersion,
            measured_quantity=payload.measuredQuantity,
            measured_unit=payload.measuredUnit or effective.defaultUnit,
            notes=normalize_optional_name(payload.notes, field_name="notes"),
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
        work_item = await self.repository.get_project_work_item(
            project_id,
            project_work_item_id,
            organization_id=organization_id,
        )
        if work_item is None:
            raise WorkCatalogNotFoundError("Project work item was not found.")
        work_type = await self.repository.get_work_type_by_code(work_item.resolved_work_type_code)
        if work_type is None:
            raise WorkCatalogNotFoundError("Work type was not found.")
        parameter_overrides = await self.repository.list_parameter_overrides_for_org(
            organization_id,
            work_type_ids=[work_type.id],
        )
        parameter_overrides = {
            parameter.id: parameter_overrides[parameter.id]
            for parameter in (work_type.parameters or [])
            if parameter.id in parameter_overrides
        }
        value_rows = self._build_value_rows(
            work_type=work_type,
            parameter_overrides=parameter_overrides,
            value_inputs=values,
        )
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
            itemSequence=work_item.item_sequence,
            measuredQuantity=_as_float(work_item.measured_quantity),
            measuredUnit=work_item.measured_unit,
            defaultUnit=work_item.resolved_unit,
            workTypeVersion=work_item.resolved_catalog_version,
            settingVersion=work_item.resolved_setting_version,
            tenantPricingProfileId=work_item.tenant_pricing_profile_id,
            notes=work_item.notes,
            values=[
                ProjectWorkItemValueRead(
                    parameterDefinitionId=value.work_type_parameter_id,
                    parameterCode=value.resolved_parameter_code,
                    parameterSlug=value.parameter.slug if value.parameter else value.resolved_parameter_code,
                    parameterLabel=value.resolved_parameter_name,
                    parameterSection=value.parameter.section if value.parameter else None,
                    dataType=value.resolved_data_type,
                    unit=value.resolved_unit,
                    visionExtractable=value.parameter.vision_extractable if value.parameter else None,
                    manualOverrideAllowed=value.parameter.manual_override_allowed if value.parameter else None,
                    textValue=value.value_text,
                    numberValue=_as_float(value.value_number),
                    booleanValue=value.value_boolean,
                    optionValue=value.value_option_code,
                    sourceType=value.source_type,
                    updatedAt=value.updated_at,
                )
                for value in (work_item.values or [])
            ],
            detections=[self._vision_detection_read(detection) for detection in (work_item.detections or [])],
            createdAt=work_item.created_at,
            updatedAt=work_item.updated_at,
        )

    async def list_project_work_items(self, *, project_id: str, organization_id: str) -> list[ProjectWorkItemRead]:
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
        work_type = await self.repository.get_work_type_by_code(effective.code)
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
            source_provider=normalize_optional_name(payload.sourceProvider, field_name="sourceProvider"),
            source_model=normalize_optional_name(payload.sourceModel, field_name="sourceModel"),
            source_model_version=normalize_optional_name(payload.sourceModelVersion, field_name="sourceModelVersion"),
            created_by_user_id=created_by_user_id,
        )
        created = await self.repository.create_vision_detection(detection)
        return self._vision_detection_read(created)
