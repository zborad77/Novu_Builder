from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from time import perf_counter
from types import MappingProxyType
from typing import Mapping

from app.core.metrics import (
    observe_cache_operation,
    observe_work_catalog_resolution,
    observe_work_catalog_resolution_input,
    record_work_catalog_validation_failure,
)
from app.models.work_catalog import (
    AnalysisProfile,
    CatalogPricingProfile,
    TenantWorkTypeExtraParameter,
    TenantWorkTypeParameterOverride,
    TenantWorkTypeSetting,
    WorkType,
)
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.work_catalog.domain import (
    CatalogValidationError,
    TENANT_WORK_TYPE_SETTING_STATUSES,
    validate_resolved_parameter_contract,
    normalize_machine_code,
    normalize_enum,
    section_label,
    section_sort_order,
)


def _as_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


class TenantWorkTypeResolutionError(LookupError):
    """Raised when the effective tenant configuration cannot be resolved safely."""


@dataclass(frozen=True)
class ResolvedParameterOption:
    code: str
    label: str
    sort_order: int
    is_active: bool


@dataclass(frozen=True)
class ResolvedParameterDefinition:
    parameter_definition_id: str
    parameter_scope: str
    code: str
    slug: str
    label: str
    effective_label: str
    description: str | None
    data_type: str
    unit: str | None
    section: str
    required: bool
    enabled: bool
    sort_order: int
    override_status: str | None
    setting_version: int | None
    min_number_value: float | None
    max_number_value: float | None
    vision_extractable: bool
    manual_override_allowed: bool
    default_text_value: str | None
    default_number_value: float | None
    default_boolean_value: bool | None
    default_option_code: str | None
    enum_options: tuple[ResolvedParameterOption, ...]
    work_type_parameter_id: str | None
    tenant_extra_parameter_id: str | None

    @property
    def section_label(self) -> str:
        return section_label(self.section)

    @property
    def allowed_option_codes(self) -> set[str]:
        return {option.code for option in self.enum_options if option.is_active}

    def has_default(self) -> bool:
        return any(
            value is not None
            for value in (
                self.default_text_value,
                self.default_number_value,
                self.default_boolean_value,
                self.default_option_code,
            )
        )


@dataclass(frozen=True)
class ResolvedTenantWorkTypeConfiguration:
    organization_id: str
    work_type: WorkType
    tenant_setting: TenantWorkTypeSetting | None
    analysis_profile: AnalysisProfile | None
    catalog_pricing_profile: CatalogPricingProfile | None
    tenant_analysis_profile_code: str | None
    tenant_catalog_pricing_profile_code: str | None
    tenant_pricing_profile_id: str | None
    parameter_overrides: tuple[TenantWorkTypeParameterOverride, ...]
    extra_parameters: tuple[TenantWorkTypeExtraParameter, ...]
    parameters: tuple[ResolvedParameterDefinition, ...]
    is_enabled: bool

    @property
    def work_type_code(self) -> str:
        return self.work_type.code

    @property
    def setting_version(self) -> int | None:
        return self.tenant_setting.config_version if self.tenant_setting else None

    @property
    def effective_display_name(self) -> str:
        if self.tenant_setting and self.tenant_setting.custom_display_name:
            return self.tenant_setting.custom_display_name
        return self.work_type.name

    @cached_property
    def parameter_map(self) -> Mapping[str, ResolvedParameterDefinition]:
        return MappingProxyType({parameter.code: parameter for parameter in self.parameters})

    @property
    def extra_parameter_definitions(self) -> tuple[ResolvedParameterDefinition, ...]:
        return tuple(parameter for parameter in self.parameters if parameter.parameter_scope == "tenant_extra")

    @property
    def sorted_parameter_overrides(self) -> tuple[TenantWorkTypeParameterOverride, ...]:
        return tuple(
            sorted(
                self.parameter_overrides,
                key=lambda item: (
                    item.sort_order_override if item.sort_order_override is not None else 10_000,
                    item.parameter.code if item.parameter else item.work_type_parameter_id,
                ),
            )
        )

    def parameter_by_code(self) -> Mapping[str, ResolvedParameterDefinition]:
        return self.parameter_map


def _analysis_profile_matches_work_type(profile, work_type: WorkType) -> bool:
    if profile is None:
        return True
    return profile.code.startswith(f"{work_type.code}-")


def _catalog_pricing_profile_matches_work_type(profile, work_type: WorkType) -> bool:
    if profile is None:
        return True
    return profile.code.startswith(f"{work_type.code}-")


def _setting_matches_work_type(setting: TenantWorkTypeSetting | None, work_type: WorkType) -> bool:
    if setting is None:
        return True
    return setting.work_type_id == work_type.id


class TenantWorkTypeResolutionService:
    def __init__(self, repository: WorkCatalogRepository):
        self.repository = repository
        self._resolved_by_work_type: dict[tuple[str, str], ResolvedTenantWorkTypeConfiguration] = {}
        self._resolved_all_by_org: dict[str, list[ResolvedTenantWorkTypeConfiguration]] = {}

    def invalidate(
        self,
        *,
        organization_id: str,
        work_type_code: str | None = None,
    ) -> None:
        self._resolved_all_by_org.pop(organization_id, None)
        if work_type_code is None:
            stale_keys = [key for key in self._resolved_by_work_type if key[0] == organization_id]
            for key in stale_keys:
                self._resolved_by_work_type.pop(key, None)
            return
        self._resolved_by_work_type.pop((organization_id, work_type_code), None)

    async def resolve_for_work_type(
        self,
        *,
        organization_id: str,
        work_type_code: str,
    ) -> ResolvedTenantWorkTypeConfiguration:
        normalized_code = normalize_machine_code(work_type_code, field_name="workTypeCode")
        cache_key = (organization_id, normalized_code)
        cached = self._resolved_by_work_type.get(cache_key)
        if cached is not None:
            observe_cache_operation(
                namespace="work_catalog_local",
                operation="resolve_for_work_type",
                outcome="hit",
            )
            return cached
        observe_cache_operation(
            namespace="work_catalog_local",
            operation="resolve_for_work_type",
            outcome="miss",
        )
        started_at = perf_counter()
        outcome = "success"
        work_type = await self.repository.get_work_type_by_code_for_resolution(normalized_code)
        if work_type is None:
            outcome = "not_found"
            observe_work_catalog_resolution(
                path="tenant_work_type_resolution.resolve_for_work_type",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
            raise TenantWorkTypeResolutionError(f"Work type '{normalized_code}' was not found.")
        try:
            resolved = await self._resolve_for_work_types(
                organization_id=organization_id,
                work_types=[work_type],
            )
        except CatalogValidationError:
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="tenant_work_type_resolution.resolve_for_work_type",
                reason="invalid_effective_configuration",
            )
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            observe_work_catalog_resolution(
                path="tenant_work_type_resolution.resolve_for_work_type",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
        self._resolved_by_work_type[cache_key] = resolved[0]
        return resolved[0]

    async def resolve_all_for_org(
        self,
        *,
        organization_id: str,
    ) -> list[ResolvedTenantWorkTypeConfiguration]:
        cached = self._resolved_all_by_org.get(organization_id)
        if cached is not None:
            observe_cache_operation(
                namespace="work_catalog_local",
                operation="resolve_all_for_org",
                outcome="hit",
            )
            return cached
        observe_cache_operation(
            namespace="work_catalog_local",
            operation="resolve_all_for_org",
            outcome="miss",
        )
        started_at = perf_counter()
        outcome = "success"
        work_types = list(await self.repository.list_work_types_for_resolution())
        try:
            resolved = await self._resolve_for_work_types(
                organization_id=organization_id,
                work_types=work_types,
            )
        except CatalogValidationError:
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="tenant_work_type_resolution.resolve_all_for_org",
                reason="invalid_effective_configuration",
            )
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            observe_work_catalog_resolution(
                path="tenant_work_type_resolution.resolve_all_for_org",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
        self._resolved_all_by_org[organization_id] = resolved
        for item in resolved:
            self._resolved_by_work_type[(organization_id, item.work_type.code)] = item
        return resolved

    async def _resolve_for_work_types(
        self,
        *,
        organization_id: str,
        work_types: list[WorkType],
    ) -> list[ResolvedTenantWorkTypeConfiguration]:
        if not work_types:
            return []
        work_type_ids = [work_type.id for work_type in work_types]
        settings = await self.repository.list_tenant_settings_for_resolution_for_org(
            organization_id,
            work_type_ids=work_type_ids,
        )
        parameter_overrides = await self.repository.list_parameter_overrides_for_org(
            organization_id,
            work_type_ids=work_type_ids,
        )
        extra_parameters = await self.repository.list_tenant_extra_parameters_for_org(
            organization_id,
            work_type_ids=work_type_ids,
        )
        analysis_profile_ids = {
            profile_id
            for profile_id in (
                [work_type.default_analysis_profile_id for work_type in work_types]
                + [setting.analysis_profile_id for setting in settings.values()]
            )
            if profile_id
        }
        catalog_pricing_profile_ids = {
            profile_id
            for profile_id in (
                [work_type.default_catalog_pricing_profile_id for work_type in work_types]
                + [setting.catalog_pricing_profile_id for setting in settings.values()]
            )
            if profile_id
        }
        analysis_profiles_by_id = await self.repository.list_analysis_profiles_by_ids(
            tuple(sorted(analysis_profile_ids))
        )
        catalog_pricing_profiles_by_id = await self.repository.list_catalog_pricing_profiles_by_ids(
            tuple(sorted(catalog_pricing_profile_ids))
        )
        self._observe_resolution_inputs(
            path="tenant_work_type_resolution.batch_inputs",
            work_types=work_types,
            settings=settings,
            parameter_overrides=parameter_overrides,
            extra_parameters=extra_parameters,
            analysis_profiles_by_id=analysis_profiles_by_id,
            catalog_pricing_profiles_by_id=catalog_pricing_profiles_by_id,
        )
        resolved: list[ResolvedTenantWorkTypeConfiguration] = []
        for work_type in work_types:
            setting = settings.get(work_type.id)
            filtered_overrides = {
                parameter.id: parameter_overrides[parameter.id]
                for parameter in (work_type.parameters or [])
                if parameter.id in parameter_overrides
            }
            resolved.append(
                self._compose_effective_configuration(
                    organization_id=organization_id,
                    work_type=work_type,
                    setting=setting,
                    parameter_overrides=filtered_overrides,
                    extra_parameters=extra_parameters.get(work_type.id, []),
                    analysis_profiles_by_id=analysis_profiles_by_id,
                    catalog_pricing_profiles_by_id=catalog_pricing_profiles_by_id,
                )
            )
        return resolved

    @staticmethod
    def _observe_resolution_inputs(
        *,
        path: str,
        work_types: list[WorkType],
        settings: Mapping[str, TenantWorkTypeSetting],
        parameter_overrides: Mapping[str, TenantWorkTypeParameterOverride],
        extra_parameters: Mapping[str, list[TenantWorkTypeExtraParameter]],
        analysis_profiles_by_id: Mapping[str, AnalysisProfile],
        catalog_pricing_profiles_by_id: Mapping[str, CatalogPricingProfile],
    ) -> None:
        observe_work_catalog_resolution_input(path=path, kind="work_types", count=len(work_types))
        observe_work_catalog_resolution_input(path=path, kind="settings", count=len(settings))
        observe_work_catalog_resolution_input(
            path=path,
            kind="parameter_overrides",
            count=len(parameter_overrides),
        )
        observe_work_catalog_resolution_input(
            path=path,
            kind="extra_parameters",
            count=sum(len(rows) for rows in extra_parameters.values()),
        )
        observe_work_catalog_resolution_input(
            path=path,
            kind="analysis_profiles",
            count=len(analysis_profiles_by_id),
        )
        observe_work_catalog_resolution_input(
            path=path,
            kind="catalog_pricing_profiles",
            count=len(catalog_pricing_profiles_by_id),
        )

    def _compose_effective_configuration(
        self,
        *,
        organization_id: str,
        work_type: WorkType,
        setting: TenantWorkTypeSetting | None,
        parameter_overrides: dict[str, TenantWorkTypeParameterOverride],
        extra_parameters: list[TenantWorkTypeExtraParameter],
        analysis_profiles_by_id: Mapping[str, AnalysisProfile],
        catalog_pricing_profiles_by_id: Mapping[str, CatalogPricingProfile],
    ) -> ResolvedTenantWorkTypeConfiguration:
        self._validate_setting_scope(
            organization_id=organization_id,
            work_type=work_type,
            setting=setting,
        )
        validated_overrides = self._validate_parameter_override_scope(
            organization_id=organization_id,
            work_type=work_type,
            setting=setting,
            parameter_overrides=parameter_overrides,
        )
        validated_extra_parameters = self._validate_extra_parameter_scope(
            organization_id=organization_id,
            work_type=work_type,
            setting=setting,
            extra_parameters=extra_parameters,
        )

        analysis_profile = self._resolve_analysis_profile(
            work_type=work_type,
            setting=setting,
            analysis_profiles_by_id=analysis_profiles_by_id,
        )
        catalog_pricing_profile = self._resolve_catalog_pricing_profile(
            work_type=work_type,
            setting=setting,
            catalog_pricing_profiles_by_id=catalog_pricing_profiles_by_id,
        )
        parameters = self._resolve_parameters(
            work_type=work_type,
            parameter_overrides=validated_overrides,
            extra_parameters=validated_extra_parameters,
        )
        is_enabled = self._resolve_enabled_state(work_type=work_type, setting=setting)
        return ResolvedTenantWorkTypeConfiguration(
            organization_id=organization_id,
            work_type=work_type,
            tenant_setting=setting,
            analysis_profile=analysis_profile,
            catalog_pricing_profile=catalog_pricing_profile,
            tenant_analysis_profile_code=(
                analysis_profiles_by_id[setting.analysis_profile_id].code
                if setting and setting.analysis_profile_id and setting.analysis_profile_id in analysis_profiles_by_id
                else None
            ),
            tenant_catalog_pricing_profile_code=(
                catalog_pricing_profiles_by_id[setting.catalog_pricing_profile_id].code
                if setting
                and setting.catalog_pricing_profile_id
                and setting.catalog_pricing_profile_id in catalog_pricing_profiles_by_id
                else None
            ),
            tenant_pricing_profile_id=setting.tenant_pricing_profile_id if setting else None,
            parameter_overrides=tuple(validated_overrides.values()),
            extra_parameters=tuple(validated_extra_parameters),
            parameters=tuple(parameters),
            is_enabled=is_enabled,
        )

    @staticmethod
    def _resolve_analysis_profile(
        *,
        work_type: WorkType,
        setting: TenantWorkTypeSetting | None,
        analysis_profiles_by_id: Mapping[str, AnalysisProfile],
    ) -> AnalysisProfile | None:
        analysis_profile_id = (
            setting.analysis_profile_id
            if setting and setting.analysis_profile_id
            else work_type.default_analysis_profile_id
        )
        if analysis_profile_id is None:
            return None
        analysis_profile = analysis_profiles_by_id.get(analysis_profile_id)
        if analysis_profile is None:
            raise CatalogValidationError(
                f"Analysis profile '{analysis_profile_id}' could not be loaded for work type '{work_type.code}'."
            )
        if not _analysis_profile_matches_work_type(analysis_profile, work_type):
            raise CatalogValidationError(
                f"Analysis profile '{analysis_profile.code}' is inconsistent with work type '{work_type.code}'."
            )
        if not analysis_profile.is_active or analysis_profile.status != "active":
            raise CatalogValidationError(
                f"Analysis profile '{analysis_profile.code}' is not active for work type '{work_type.code}'."
            )
        return analysis_profile

    @staticmethod
    def _resolve_catalog_pricing_profile(
        *,
        work_type: WorkType,
        setting: TenantWorkTypeSetting | None,
        catalog_pricing_profiles_by_id: Mapping[str, CatalogPricingProfile],
    ) -> CatalogPricingProfile | None:
        catalog_pricing_profile_id = (
            setting.catalog_pricing_profile_id
            if setting and setting.catalog_pricing_profile_id
            else work_type.default_catalog_pricing_profile_id
        )
        if catalog_pricing_profile_id is None:
            return None
        catalog_pricing_profile = catalog_pricing_profiles_by_id.get(catalog_pricing_profile_id)
        if catalog_pricing_profile is None:
            raise CatalogValidationError(
                f"Catalog pricing profile '{catalog_pricing_profile_id}' could not be loaded for work type '{work_type.code}'."
            )
        if not _catalog_pricing_profile_matches_work_type(catalog_pricing_profile, work_type):
            raise CatalogValidationError(
                f"Catalog pricing profile '{catalog_pricing_profile.code}' is inconsistent with work type '{work_type.code}'."
            )
        if not catalog_pricing_profile.is_active or catalog_pricing_profile.status != "active":
            raise CatalogValidationError(
                f"Catalog pricing profile '{catalog_pricing_profile.code}' is not active for work type '{work_type.code}'."
            )
        return catalog_pricing_profile

    @staticmethod
    def _resolve_enabled_state(
        *,
        work_type: WorkType,
        setting: TenantWorkTypeSetting | None,
    ) -> bool:
        is_enabled = work_type.is_active and work_type.state == "active"
        if setting is None:
            return is_enabled
        normalized_status = normalize_enum(
            setting.status,
            field_name="status",
            allowed=TENANT_WORK_TYPE_SETTING_STATUSES,
        )
        if normalized_status == "disabled":
            return False
        return is_enabled

    @staticmethod
    def _validate_setting_scope(
        *,
        organization_id: str,
        work_type: WorkType,
        setting: TenantWorkTypeSetting | None,
    ) -> None:
        if setting is None:
            return
        if setting.organization_id != organization_id:
            raise CatalogValidationError(
                f"Tenant setting '{setting.id}' is not scoped to organization '{organization_id}'."
            )
        if not _setting_matches_work_type(setting, work_type):
            raise CatalogValidationError(
                f"Tenant setting '{setting.id}' is not scoped to work type '{work_type.code}'."
            )

    @staticmethod
    def _validate_parameter_override_scope(
        *,
        organization_id: str,
        work_type: WorkType,
        setting: TenantWorkTypeSetting | None,
        parameter_overrides: dict[str, TenantWorkTypeParameterOverride],
    ) -> dict[str, TenantWorkTypeParameterOverride]:
        if not parameter_overrides:
            return {}
        expected_setting_id = setting.id if setting else None
        validated: dict[str, TenantWorkTypeParameterOverride] = {}
        for parameter_id, override in parameter_overrides.items():
            if override.organization_id != organization_id:
                raise CatalogValidationError(
                    f"Parameter override '{override.id}' is not scoped to organization '{organization_id}'."
                )
            if override.work_type_id != work_type.id:
                raise CatalogValidationError(
                    f"Parameter override '{override.id}' is not scoped to work type '{work_type.code}'."
                )
            if expected_setting_id is None or override.tenant_work_type_setting_id != expected_setting_id:
                raise CatalogValidationError(
                    f"Parameter override '{override.id}' is not attached to the active tenant setting for work type '{work_type.code}'."
                )
            if override.work_type_parameter_id != parameter_id:
                raise CatalogValidationError(
                    f"Parameter override '{override.id}' resolved under an unexpected parameter key."
                )
            validated[parameter_id] = override
        return validated

    @staticmethod
    def _validate_extra_parameter_scope(
        *,
        organization_id: str,
        work_type: WorkType,
        setting: TenantWorkTypeSetting | None,
        extra_parameters: list[TenantWorkTypeExtraParameter],
    ) -> list[TenantWorkTypeExtraParameter]:
        if not extra_parameters:
            return []
        expected_setting_id = setting.id if setting else None
        validated: list[TenantWorkTypeExtraParameter] = []
        seen_codes: set[str] = set()
        seen_slugs: set[str] = set()
        for extra_parameter in extra_parameters:
            if extra_parameter.organization_id != organization_id:
                raise CatalogValidationError(
                    f"Tenant extra parameter '{extra_parameter.code}' is not scoped to organization '{organization_id}'."
                )
            if extra_parameter.work_type_id != work_type.id:
                raise CatalogValidationError(
                    f"Tenant extra parameter '{extra_parameter.code}' is not scoped to work type '{work_type.code}'."
                )
            if expected_setting_id is None or extra_parameter.tenant_work_type_setting_id != expected_setting_id:
                raise CatalogValidationError(
                    f"Tenant extra parameter '{extra_parameter.code}' is not attached to the active tenant setting for work type '{work_type.code}'."
                )
            if extra_parameter.code in seen_codes:
                raise CatalogValidationError(
                    f"Duplicate tenant extra parameter code '{extra_parameter.code}' on work type '{work_type.code}'."
                )
            if extra_parameter.slug in seen_slugs:
                raise CatalogValidationError(
                    f"Duplicate tenant extra parameter slug '{extra_parameter.slug}' on work type '{work_type.code}'."
                )
            seen_codes.add(extra_parameter.code)
            seen_slugs.add(extra_parameter.slug)
            validated.append(extra_parameter)
        return validated

    def _resolve_parameters(
        self,
        *,
        work_type: WorkType,
        parameter_overrides: dict[str, TenantWorkTypeParameterOverride],
        extra_parameters: list[TenantWorkTypeExtraParameter],
    ) -> list[ResolvedParameterDefinition]:
        resolved: list[ResolvedParameterDefinition] = []
        seen_codes: set[str] = set()

        for parameter in (work_type.parameters or []):
            override = parameter_overrides.get(parameter.id)
            resolved_parameter = self._resolve_global_parameter(
                parameter=parameter,
                override=override,
            )
            resolved.append(resolved_parameter)
            seen_codes.add(resolved_parameter.code)

        for extra_parameter in extra_parameters:
            if extra_parameter.code in seen_codes:
                raise CatalogValidationError(
                    f"Tenant extra parameter '{extra_parameter.code}' collides with an existing parameter on work type '{work_type.code}'."
                )
            resolved_parameter = self._resolve_extra_parameter(extra_parameter=extra_parameter)
            resolved.append(resolved_parameter)
            seen_codes.add(resolved_parameter.code)

        resolved.sort(key=lambda item: (section_sort_order(item.section), item.sort_order, item.code))
        return resolved

    @staticmethod
    def _resolve_global_parameter(
        *,
        parameter,
        override: TenantWorkTypeParameterOverride | None,
    ) -> ResolvedParameterDefinition:
        override_status = override.override_status if override else None
        is_enabled = override_status != "hidden"
        is_required = parameter.is_required
        if override_status == "required":
            is_required = True
        elif override_status == "optional":
            is_required = False
        resolved = ResolvedParameterDefinition(
            parameter_definition_id=parameter.id,
            parameter_scope="global",
            code=parameter.code,
            slug=parameter.slug,
            label=parameter.name,
            effective_label=override.custom_display_name if override and override.custom_display_name else parameter.name,
            description=parameter.description,
            data_type=parameter.data_type,
            unit=parameter.unit,
            section=parameter.section or "optional_notes",
            required=is_required,
            enabled=is_enabled,
            sort_order=override.sort_order_override if override and override.sort_order_override is not None else parameter.sort_order,
            override_status=override_status,
            setting_version=override.config_version if override else None,
            min_number_value=_as_float(parameter.min_number_value),
            max_number_value=_as_float(parameter.max_number_value),
            vision_extractable=parameter.vision_extractable,
            manual_override_allowed=parameter.manual_override_allowed,
            default_text_value=override.default_text_value if override and override.default_text_value is not None else parameter.default_text_value,
            default_number_value=_as_float(
                override.default_number_value if override and override.default_number_value is not None else parameter.default_number_value
            ),
            default_boolean_value=override.default_boolean_value if override and override.default_boolean_value is not None else parameter.default_boolean_value,
            default_option_code=override.default_option_code if override and override.default_option_code is not None else parameter.default_option_code,
            enum_options=tuple(
                ResolvedParameterOption(
                    code=option.code,
                    label=option.label,
                    sort_order=option.sort_order,
                    is_active=option.is_active,
                )
                for option in (parameter.options or [])
            ),
            work_type_parameter_id=parameter.id,
            tenant_extra_parameter_id=None,
        )
        validate_resolved_parameter_contract(
            parameter_scope=resolved.parameter_scope,
            parameter_code=resolved.code,
            slug=resolved.slug,
            label=resolved.label,
            effective_label=resolved.effective_label,
            data_type=resolved.data_type,
            unit=resolved.unit,
            section=resolved.section,
            required=resolved.required,
            enabled=resolved.enabled,
            override_status=resolved.override_status,
            vision_extractable=resolved.vision_extractable,
            manual_override_allowed=resolved.manual_override_allowed,
            min_number_value=resolved.min_number_value,
            max_number_value=resolved.max_number_value,
            default_text_value=resolved.default_text_value,
            default_number_value=resolved.default_number_value,
            default_boolean_value=resolved.default_boolean_value,
            default_option_code=resolved.default_option_code,
            option_codes={option.code for option in resolved.enum_options if option.is_active},
        )
        return resolved

    @staticmethod
    def _resolve_extra_parameter(
        *,
        extra_parameter: TenantWorkTypeExtraParameter,
    ) -> ResolvedParameterDefinition:
        resolved = ResolvedParameterDefinition(
            parameter_definition_id=extra_parameter.id,
            parameter_scope="tenant_extra",
            code=extra_parameter.code,
            slug=extra_parameter.slug,
            label=extra_parameter.name,
            effective_label=extra_parameter.name,
            description=extra_parameter.description,
            data_type=extra_parameter.data_type,
            unit=extra_parameter.unit,
            section=extra_parameter.section,
            required=extra_parameter.is_required,
            enabled=extra_parameter.status == "active",
            sort_order=extra_parameter.sort_order,
            override_status=extra_parameter.status,
            setting_version=extra_parameter.config_version,
            min_number_value=_as_float(extra_parameter.min_number_value),
            max_number_value=_as_float(extra_parameter.max_number_value),
            vision_extractable=extra_parameter.vision_extractable,
            manual_override_allowed=extra_parameter.manual_override_allowed,
            default_text_value=extra_parameter.default_text_value,
            default_number_value=_as_float(extra_parameter.default_number_value),
            default_boolean_value=extra_parameter.default_boolean_value,
            default_option_code=extra_parameter.default_option_code,
            enum_options=tuple(
                ResolvedParameterOption(
                    code=option.code,
                    label=option.label,
                    sort_order=option.sort_order,
                    is_active=option.is_active,
                )
                for option in (extra_parameter.options or [])
            ),
            work_type_parameter_id=None,
            tenant_extra_parameter_id=extra_parameter.id,
        )
        validate_resolved_parameter_contract(
            parameter_scope=resolved.parameter_scope,
            parameter_code=resolved.code,
            slug=resolved.slug,
            label=resolved.label,
            effective_label=resolved.effective_label,
            data_type=resolved.data_type,
            unit=resolved.unit,
            section=resolved.section,
            required=resolved.required,
            enabled=resolved.enabled,
            override_status=resolved.override_status,
            vision_extractable=resolved.vision_extractable,
            manual_override_allowed=resolved.manual_override_allowed,
            min_number_value=resolved.min_number_value,
            max_number_value=resolved.max_number_value,
            default_text_value=resolved.default_text_value,
            default_number_value=resolved.default_number_value,
            default_boolean_value=resolved.default_boolean_value,
            default_option_code=resolved.default_option_code,
            option_codes={option.code for option in resolved.enum_options if option.is_active},
        )
        return resolved
