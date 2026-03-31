from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter
from typing import Any

from app.core.metrics import (
    observe_cache_operation,
    observe_work_catalog_resolution,
    record_work_catalog_validation_failure,
)
from app.models.work_catalog import AnalysisProfile, WorkType
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.services.tenant_work_type_resolution_service import TenantWorkTypeResolutionService
from app.work_catalog.domain import (
    CatalogValidationError,
    coerce_analysis_attribute_value,
    validate_number_bounds,
    validate_option_code,
    normalize_machine_code,
)


class AnalysisProfileResolutionError(LookupError):
    """Raised when no valid effective analysis profile can be resolved."""


def _as_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


@dataclass(frozen=True)
class ResolvedAnalysisConfiguration:
    organization_id: str
    work_type: WorkType
    analysis_profile: AnalysisProfile
    parameter_codes: dict[str, set[str]]

    @property
    def work_type_code(self) -> str:
        return self.work_type.code

    @property
    def profile_code(self) -> str:
        return self.analysis_profile.code

    @property
    def profile_version(self) -> int:
        return int(self.analysis_profile.profile_version)


class AnalysisProfileService:
    def __init__(self, repository: WorkCatalogRepository):
        self.repository = repository
        self.resolution_service = TenantWorkTypeResolutionService(repository)
        self._resolved_by_work_type: dict[tuple[str, str], ResolvedAnalysisConfiguration] = {}
        self._resolved_snapshots: dict[tuple[str, str, str], ResolvedAnalysisConfiguration] = {}

    async def resolve_for_work_type(
        self,
        *,
        organization_id: str,
        work_type_code: str,
    ) -> ResolvedAnalysisConfiguration:
        normalized_code = normalize_machine_code(work_type_code, field_name="workTypeCode")
        cache_key = (organization_id, normalized_code)
        cached = self._resolved_by_work_type.get(cache_key)
        if cached is not None:
            observe_cache_operation(
                namespace="work_catalog_local",
                operation="analysis_profile.resolve_for_work_type",
                outcome="hit",
            )
            return cached
        observe_cache_operation(
            namespace="work_catalog_local",
            operation="analysis_profile.resolve_for_work_type",
            outcome="miss",
        )
        started_at = perf_counter()
        outcome = "success"
        try:
            resolved = await self.resolution_service.resolve_for_work_type(
                organization_id=organization_id,
                work_type_code=normalized_code,
            )
        except CatalogValidationError as exc:
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="analysis_profile.resolve_for_work_type",
                reason="invalid_effective_configuration",
            )
            raise AnalysisProfileResolutionError(str(exc)) from exc
        except Exception:
            outcome = "error"
            raise
        finally:
            observe_work_catalog_resolution(
                path="analysis_profile.resolve_for_work_type",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
        work_type = resolved.work_type
        profile = resolved.analysis_profile
        if profile is None:
            raise AnalysisProfileResolutionError(
                f"Work type '{normalized_code}' has no active analysis profile."
            )
        configured = ResolvedAnalysisConfiguration(
            organization_id=organization_id,
            work_type=work_type,
            analysis_profile=profile,
            parameter_codes={
                parameter.code: parameter.allowed_option_codes
                for parameter in resolved.parameters
            },
        )
        self._resolved_by_work_type[cache_key] = configured
        return configured

    async def resolve_for_snapshot(
        self,
        *,
        organization_id: str,
        work_type_code: str,
        analysis_profile_id: str,
    ) -> ResolvedAnalysisConfiguration:
        normalized_code = normalize_machine_code(work_type_code, field_name="workTypeCode")
        cache_key = (organization_id, normalized_code, analysis_profile_id)
        cached = self._resolved_snapshots.get(cache_key)
        if cached is not None:
            observe_cache_operation(
                namespace="work_catalog_local",
                operation="analysis_profile.resolve_for_snapshot",
                outcome="hit",
            )
            return cached
        observe_cache_operation(
            namespace="work_catalog_local",
            operation="analysis_profile.resolve_for_snapshot",
            outcome="miss",
        )
        started_at = perf_counter()
        outcome = "success"
        work_type = await self.repository.get_work_type_by_code(normalized_code)
        if work_type is None:
            outcome = "not_found"
            observe_work_catalog_resolution(
                path="analysis_profile.resolve_for_snapshot",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
            raise AnalysisProfileResolutionError(f"Work type '{normalized_code}' was not found.")
        profile = await self.repository.get_analysis_profile_by_id(analysis_profile_id)
        if profile is None:
            outcome = "not_found"
            observe_work_catalog_resolution(
                path="analysis_profile.resolve_for_snapshot",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
            raise AnalysisProfileResolutionError(
                f"Analysis profile '{analysis_profile_id}' was not found."
            )
        if not profile.code.startswith(f"{work_type.code}-"):
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="analysis_profile.resolve_for_snapshot",
                reason="profile_work_type_mismatch",
            )
            observe_work_catalog_resolution(
                path="analysis_profile.resolve_for_snapshot",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
            raise AnalysisProfileResolutionError(
                f"Analysis profile '{profile.code}' is inconsistent with work type '{work_type.code}'."
            )
        if not profile.is_active or profile.status != "active":
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="analysis_profile.resolve_for_snapshot",
                reason="inactive_profile",
            )
            observe_work_catalog_resolution(
                path="analysis_profile.resolve_for_snapshot",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
            raise AnalysisProfileResolutionError(
                f"Analysis profile '{profile.code}' is not active."
            )
        configured = ResolvedAnalysisConfiguration(
            organization_id=organization_id,
            work_type=work_type,
            analysis_profile=profile,
            parameter_codes={
                parameter.code: (
                    {
                        option.code
                        for option in (parameter.options or [])
                        if option.is_active
                    }
                    if parameter.data_type == "option"
                    else set()
                )
                for parameter in (work_type.parameters or [])
            },
        )
        self._resolved_snapshots[cache_key] = configured
        observe_work_catalog_resolution(
            path="analysis_profile.resolve_for_snapshot",
            outcome=outcome,
            duration_seconds=perf_counter() - started_at,
        )
        return configured

    def build_provider_config(self, resolved: ResolvedAnalysisConfiguration) -> dict[str, Any]:
        profile = resolved.analysis_profile
        return {
            "workTypeCode": resolved.work_type.code,
            "workTypeName": resolved.work_type.name,
            "defaultUnit": resolved.work_type.default_unit,
            "measurementKind": resolved.work_type.measurement_kind,
            "analysisProfile": {
                "id": profile.id,
                "code": profile.code,
                "version": profile.profile_version,
                "status": profile.status,
                "scopeCode": profile.scope_code,
                "scopeLabel": profile.scope_label,
                "scopeDescription": profile.scope_description,
                "taskType": profile.task_type,
                "targetObjects": [
                    {
                        "code": row.code,
                        "label": row.label,
                        "description": row.description,
                        "objectRole": row.object_role,
                        "isRequired": row.is_required,
                    }
                    for row in (profile.target_objects or [])
                ],
                "ignoredObjects": [
                    {
                        "code": row.code,
                        "label": row.label,
                        "reason": row.reason,
                    }
                    for row in (profile.ignored_objects or [])
                ],
                "extractionRules": [
                    {
                        "attributeCode": row.attribute_code,
                        "label": row.label,
                        "description": row.description,
                        "dataType": row.data_type,
                        "unit": row.unit,
                        "targetParameterCode": row.target_parameter_code,
                        "sourceObjectCode": row.source_object_code,
                        "required": row.is_required,
                        "allowedOptionCodes": sorted(
                            resolved.parameter_codes.get(row.target_parameter_code, set())
                        ),
                    }
                    for row in (profile.extraction_rules or [])
                ],
                "validationRules": [
                    {
                        "code": row.code,
                        "ruleType": row.rule_type,
                        "severity": row.severity,
                        "targetAttributeCode": row.target_attribute_code,
                        "targetParameterCode": row.target_parameter_code,
                        "minNumberValue": _as_float(row.min_number_value),
                        "maxNumberValue": _as_float(row.max_number_value),
                        "message": row.message,
                    }
                    for row in (profile.validation_rules or [])
                ],
                "confidenceThresholds": [
                    {
                        "attributeCode": row.attribute_code,
                        "targetObjectCode": row.target_object_code,
                        "minConfidence": float(row.min_confidence),
                        "preferredConfidence": float(row.preferred_confidence),
                        "actionBelowThreshold": row.action_below_threshold,
                    }
                    for row in (profile.confidence_thresholds or [])
                ],
                "fallbackBehavior": {
                    "mode": profile.fallback_mode,
                    "instructions": profile.fallback_instructions,
                    "requiresManualReview": profile.fallback_requires_manual_review,
                },
            },
        }

    def validate_and_map_output(
        self,
        *,
        resolved: ResolvedAnalysisConfiguration,
        raw_output: dict[str, Any],
        photo_count: int,
    ) -> dict[str, Any]:
        profile = resolved.analysis_profile
        parameter_by_code = {parameter.code: parameter for parameter in (resolved.work_type.parameters or [])}
        catalog_attributes_raw = raw_output.get("catalogAttributes") or {}
        if catalog_attributes_raw is None:
            catalog_attributes_raw = {}
        if not isinstance(catalog_attributes_raw, dict):
            raise CatalogValidationError("catalogAttributes must be an object when provided.")

        normalized_attributes: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []

        for rule in (profile.extraction_rules or []):
            raw_attribute = catalog_attributes_raw.get(rule.attribute_code)
            if raw_attribute is None:
                continue
            if not isinstance(raw_attribute, dict):
                raw_attribute = {"value": raw_attribute}
            value = coerce_analysis_attribute_value(
                data_type=rule.data_type,
                value=raw_attribute.get("value"),
                field_name=rule.attribute_code,
            )
            confidence_value = raw_attribute.get("confidence")
            confidence = float(confidence_value) if confidence_value is not None else None
            parameter = parameter_by_code.get(rule.target_parameter_code)
            if parameter and rule.data_type == "number":
                validate_number_bounds(
                    value,
                    field_name=rule.attribute_code,
                    min_value=parameter.min_number_value,
                    max_value=parameter.max_number_value,
                )
            if parameter and rule.data_type == "option":
                validate_option_code(
                    str(value),
                    field_name=rule.attribute_code,
                    allowed_codes={
                        option.code for option in (parameter.options or []) if option.is_active
                    },
                )
            normalized_attributes[rule.attribute_code] = {
                "value": _as_float(value) if isinstance(value, Decimal) else value,
                "confidence": confidence,
                "sourceObjectCode": raw_attribute.get("sourceObjectCode", rule.source_object_code),
            }

        for rule in (profile.validation_rules or []):
            if rule.rule_type == "min_photos":
                minimum = int(rule.min_number_value or 0)
                if photo_count < minimum:
                    warnings.append(rule.message)
                continue
            attribute_payload = normalized_attributes.get(rule.target_attribute_code or "")
            if rule.rule_type == "required_attribute" and attribute_payload is None:
                raise CatalogValidationError(rule.message)
            if rule.rule_type == "numeric_range" and attribute_payload is not None:
                numeric_value = attribute_payload.get("value")
                if numeric_value is not None:
                    validate_number_bounds(
                        Decimal(str(numeric_value)),
                        field_name=rule.target_attribute_code or "attribute",
                        min_value=rule.min_number_value,
                        max_value=rule.max_number_value,
                    )

        for threshold in (profile.confidence_thresholds or []):
            attribute_payload = normalized_attributes.get(threshold.attribute_code)
            if attribute_payload is None:
                continue
            confidence = attribute_payload.get("confidence")
            if confidence is None or confidence >= float(threshold.min_confidence):
                continue
            if threshold.action_below_threshold == "fail_analysis":
                raise CatalogValidationError(
                    f"Attribute '{threshold.attribute_code}' confidence {confidence} is below profile minimum."
                )
            warnings.append(
                f"Attribute '{threshold.attribute_code}' confidence {confidence} is below {float(threshold.min_confidence):.2f}."
            )
            if threshold.action_below_threshold == "drop_attribute":
                normalized_attributes.pop(threshold.attribute_code, None)

        analysis_result_fields = {
            "object_type": raw_output.get("objectType"),
            "surface_condition": raw_output.get("surfaceCondition"),
            "recommended_scope": raw_output.get("recommendedScope"),
            "estimated_quantity": raw_output.get("estimatedQuantity", raw_output.get("estimatedAreaSqm")),
            "estimated_unit": raw_output.get("estimatedUnit", resolved.work_type.default_unit),
            "estimated_area_sqm": raw_output.get("estimatedAreaSqm"),
            "area_confidence": raw_output.get("areaConfidence"),
            "mask_polygon": raw_output.get("maskPolygon"),
            "materials": raw_output.get("materials"),
            "workflow_steps": raw_output.get("workflowSteps"),
            "estimated_duration_days": raw_output.get("estimatedTotalDays"),
            "labor_hours_total": raw_output.get("laborHoursTotal"),
        }

        project_work_item_fields: dict[str, Any] = {}
        project_work_item_values: list[dict[str, Any]] = []
        for mapping in sorted(profile.output_mappings or [], key=lambda row: (row.sort_order, row.code)):
            if mapping.source_attribute_code in normalized_attributes:
                source_value = normalized_attributes[mapping.source_attribute_code]["value"]
            else:
                source_value = {
                    "object-type": analysis_result_fields["object_type"],
                    "surface-condition": analysis_result_fields["surface_condition"],
                    "recommended-scope": analysis_result_fields["recommended_scope"],
                    "estimated-quantity": analysis_result_fields["estimated_quantity"],
                    "estimated-unit": analysis_result_fields["estimated_unit"],
                    "estimated-area-sqm": analysis_result_fields["estimated_area_sqm"],
                    "area-confidence": analysis_result_fields["area_confidence"],
                    "mask-polygon": analysis_result_fields["mask_polygon"],
                    "materials": analysis_result_fields["materials"],
                    "workflow-steps": analysis_result_fields["workflow_steps"],
                    "estimated-total-days": analysis_result_fields["estimated_duration_days"],
                    "labor-hours-total": analysis_result_fields["labor_hours_total"],
                }.get(mapping.source_attribute_code)

            if source_value is None:
                if mapping.is_required:
                    raise CatalogValidationError(
                        f"Required output mapping '{mapping.code}' did not resolve a value."
                    )
                continue

            if mapping.target_entity == "analysis_result":
                analysis_result_fields[mapping.target_field] = source_value
            elif mapping.target_entity == "project_work_item":
                project_work_item_fields[mapping.target_field] = source_value
            elif mapping.target_entity == "project_work_item_value" and mapping.target_parameter_code:
                parameter = parameter_by_code[mapping.target_parameter_code]
                value_input = {
                    "parameterCode": mapping.target_parameter_code,
                    "textValue": None,
                    "numberValue": None,
                    "booleanValue": None,
                    "optionValue": None,
                    "sourceType": "vision",
                }
                if parameter.data_type == "number":
                    value_input["numberValue"] = float(source_value)
                elif parameter.data_type == "text":
                    value_input["textValue"] = str(source_value)
                elif parameter.data_type == "boolean":
                    value_input["booleanValue"] = bool(source_value)
                else:
                    value_input["optionValue"] = str(source_value)
                project_work_item_values.append(value_input)

        return {
            "analysis_result_fields": analysis_result_fields,
            "project_work_item_fields": project_work_item_fields,
            "project_work_item_values": project_work_item_values,
            "catalog_attributes": normalized_attributes,
            "validation_warnings": warnings,
            "resolved_work_type_code": resolved.work_type.code,
            "analysis_profile_code": profile.code,
            "analysis_profile_version": profile.profile_version,
            "analysis_profile_id": profile.id,
        }
