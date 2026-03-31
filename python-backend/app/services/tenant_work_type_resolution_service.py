from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter

from app.core.metrics import (
    observe_cache_operation,
    observe_work_catalog_resolution,
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
from app.work_catalog.domain import CatalogValidationError, normalize_machine_code, section_label, section_sort_order


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

    def parameter_by_code(self) -> dict[str, ResolvedParameterDefinition]:
        return {parameter.code: parameter for parameter in self.parameters}


def _analysis_profile_matches_work_type(profile, work_type: WorkType) -> bool:
    if profile is None:
        return True
    return profile.code.startswith(f"{work_type.code}-")


def _catalog_pricing_profile_matches_work_type(profile, work_type: WorkType) -> bool:
    if profile is None:
        return True
    return profile.code.startswith(f"{work_type.code}-")


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
        work_type = await self.repository.get_work_type_by_code(normalized_code)
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
        work_types = list(await self.repository.list_work_types())
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
        settings = await self.repository.list_tenant_settings_for_org(
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
                )
            )
        return resolved

    def _compose_effective_configuration(
        self,
        *,
        organization_id: str,
        work_type: WorkType,
        setting: TenantWorkTypeSetting | None,
        parameter_overrides: dict[str, TenantWorkTypeParameterOverride],
        extra_parameters: list[TenantWorkTypeExtraParameter],
    ) -> ResolvedTenantWorkTypeConfiguration:
        analysis_profile = setting.analysis_profile if setting and setting.analysis_profile else work_type.default_analysis_profile
        catalog_pricing_profile = (
            setting.catalog_pricing_profile
            if setting and setting.catalog_pricing_profile
            else work_type.default_catalog_pricing_profile
        )
        if analysis_profile is not None and not _analysis_profile_matches_work_type(analysis_profile, work_type):
            raise CatalogValidationError(
                f"Analysis profile '{analysis_profile.code}' is inconsistent with work type '{work_type.code}'."
            )
        if analysis_profile is not None and (not analysis_profile.is_active or analysis_profile.status != "active"):
            raise CatalogValidationError(
                f"Analysis profile '{analysis_profile.code}' is not active for work type '{work_type.code}'."
            )
        if catalog_pricing_profile is not None and not _catalog_pricing_profile_matches_work_type(
            catalog_pricing_profile,
            work_type,
        ):
            raise CatalogValidationError(
                f"Catalog pricing profile '{catalog_pricing_profile.code}' is inconsistent with work type '{work_type.code}'."
            )
        if catalog_pricing_profile is not None and (
            not catalog_pricing_profile.is_active or catalog_pricing_profile.status != "active"
        ):
            raise CatalogValidationError(
                f"Catalog pricing profile '{catalog_pricing_profile.code}' is not active for work type '{work_type.code}'."
            )

        parameters = self._resolve_parameters(
            work_type=work_type,
            parameter_overrides=parameter_overrides,
            extra_parameters=extra_parameters,
        )
        is_enabled = work_type.is_active and work_type.state == "active"
        if setting and setting.status == "disabled":
            is_enabled = False
        return ResolvedTenantWorkTypeConfiguration(
            organization_id=organization_id,
            work_type=work_type,
            tenant_setting=setting,
            analysis_profile=analysis_profile,
            catalog_pricing_profile=catalog_pricing_profile,
            tenant_pricing_profile_id=setting.tenant_pricing_profile_id if setting else None,
            parameter_overrides=tuple(parameter_overrides.values()),
            extra_parameters=tuple(extra_parameters),
            parameters=tuple(parameters),
            is_enabled=is_enabled,
        )

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
            override_status = override.override_status if override else None
            is_enabled = override_status != "hidden"
            is_required = parameter.is_required
            if override_status == "required":
                is_required = True
            elif override_status == "optional":
                is_required = False
            resolved.append(
                ResolvedParameterDefinition(
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
            )
            seen_codes.add(parameter.code)

        for extra_parameter in extra_parameters:
            if extra_parameter.code in seen_codes:
                raise CatalogValidationError(
                    f"Tenant extra parameter '{extra_parameter.code}' collides with an existing parameter on work type '{work_type.code}'."
                )
            resolved.append(
                ResolvedParameterDefinition(
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
            )
            seen_codes.add(extra_parameter.code)

        resolved.sort(key=lambda item: (section_sort_order(item.section), item.sort_order, item.code))
        return resolved
