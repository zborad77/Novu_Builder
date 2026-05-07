from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


CODE_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")

WORK_TYPE_STATES = frozenset({"active", "hidden", "deprecated"})
WORK_TYPE_PARAMETER_DATA_TYPES = frozenset({"number", "text", "boolean", "option"})
TENANT_WORK_TYPE_SETTING_STATUSES = frozenset({"inherited", "enabled", "disabled"})
TENANT_PARAMETER_OVERRIDE_STATUSES = frozenset({"inherited", "required", "optional", "hidden"})
TENANT_EXTRA_PARAMETER_STATUSES = frozenset({"active", "disabled"})
PARAMETER_DEFINITION_SCOPES = frozenset({"global", "tenant_extra"})
PROJECT_WORK_ITEM_STATUSES = frozenset({"draft", "resolved", "accepted", "rejected"})
PROJECT_WORK_ITEM_SOURCE_TYPES = frozenset({"manual", "vision", "import", "imported", "system", "default"})
PROJECT_WORK_ITEM_VALUE_CONFIRMATION_STATUSES = frozenset({"pending", "confirmed", "corrected", "defaulted"})
PROJECT_WORK_ITEM_CONFIRMATION_STATUSES = frozenset({"pending", "mixed", "confirmed"})
VISION_DETECTION_STATUSES = frozenset({"pending", "accepted", "rejected", "linked"})
ANALYSIS_PROFILE_TASK_TYPES = frozenset({"classification", "detection", "measurement", "hybrid"})
ANALYSIS_PROFILE_STATUSES = frozenset({"draft", "active", "deprecated", "archived"})
ANALYSIS_PROFILE_OBJECT_ROLES = frozenset({"primary", "secondary", "context"})
ANALYSIS_PROFILE_VALIDATION_RULE_TYPES = frozenset({
    "min_photos",
    "required_attribute",
    "numeric_range",
    "confidence_gate",
})
ANALYSIS_PROFILE_VALIDATION_SEVERITIES = frozenset({"warning", "blocking"})
ANALYSIS_PROFILE_FALLBACK_MODES = frozenset({
    "manual_review",
    "request_more_photos",
    "return_partial",
})
ANALYSIS_PROFILE_CONFIDENCE_ACTIONS = frozenset({"manual_review", "drop_attribute", "fail_analysis"})
ANALYSIS_PROFILE_MAPPING_TARGET_ENTITIES = frozenset({
    "analysis_result",
    "project_work_item",
    "project_work_item_value",
    "vision_detection",
})
CATALOG_PRICING_PROFILE_STATUSES = frozenset({"draft", "active", "deprecated", "archived"})
CATALOG_PRICING_BASES = frozenset({"area", "length", "count", "volume", "scope", "inspection", "service", "incident"})
CATALOG_PRICING_STRATEGIES = frozenset({"tenant_pricebook", "catalog_formula", "fixed_formula", "manual_review"})
LABOR_RATE_SOURCES = frozenset({"tenant_default", "catalog_default", "manual"})
MATERIAL_PRICING_SOURCES = frozenset({"tenant_pricebook", "catalog_default", "manual"})
CATALOG_PRICING_REQUIRED_INPUT_SOURCES = frozenset({"parameter", "work_item_field"})
CATALOG_PRICING_RULE_LINE_TYPES = frozenset({"labor", "material", "other"})
CATALOG_PRICING_RULE_CALCULATION_METHODS = frozenset({"per_unit", "fixed"})
CATALOG_PRICING_RULE_QUANTITY_SOURCES = frozenset({"parameter", "work_item_field", "constant"})
CATALOG_PRICING_RULE_RATE_SOURCES = frozenset({
    "tenant_hourly_rate",
    "tenant_daily_rate",
    "catalog_unit_rate",
    "catalog_flat_rate",
})
CATALOG_PRICING_ADJUSTMENT_TARGET_SCOPES = frozenset({"profile_total", "line_type", "base_rule"})
CATALOG_PRICING_ADJUSTMENT_OPERATIONS = frozenset({"multiply", "add_flat"})
CATALOG_PRICING_ADJUSTMENT_CONDITION_OPERATORS = frozenset({"eq", "gte", "lte", "true"})
CATALOG_PRICING_WORK_ITEM_FIELDS = frozenset({"measured_quantity", "measured_unit", "item_sequence"})

# Sections that group parameters for UI rendering, vision orchestration, and pricing.
PARAMETER_SECTIONS = frozenset({
    "dimensions",           # physical size / geometry (length, thickness, pitch)
    "materials",            # material type / grade / system choices
    "condition_or_damage",  # damage severity / substrate state / inspection classification
    "access_and_complexity",# access method / floor level / site complexity
    "quantity_scope",       # primary quantity / scope description
    "optional_notes",       # free-text annotations
})
PARAMETER_SECTION_ORDER = {
    "dimensions": 10,
    "materials": 20,
    "condition_or_damage": 30,
    "access_and_complexity": 40,
    "quantity_scope": 50,
    "optional_notes": 60,
}
PARAMETER_SECTION_LABELS = {
    "dimensions": "Dimensions",
    "materials": "Materials",
    "condition_or_damage": "Condition Or Damage",
    "access_and_complexity": "Access And Complexity",
    "quantity_scope": "Quantity And Scope",
    "optional_notes": "Optional Notes",
}
TENANT_EXTRA_PARAMETER_CODE_PREFIX = "tenant."


class CatalogValidationError(ValueError):
    """Raised when catalog input violates normalized domain rules."""


def normalize_machine_code(value: str, *, field_name: str = "code") -> str:
    if not isinstance(value, str):
        raise CatalogValidationError(f"{field_name} must be a string.")
    normalized = value.strip().lower()
    if not normalized:
        raise CatalogValidationError(f"{field_name} is required.")
    if not CODE_PATTERN.fullmatch(normalized):
        raise CatalogValidationError(
            f"{field_name} must use lowercase machine-readable code format."
        )
    return normalized


def normalize_slug(value: str, *, field_name: str = "slug") -> str:
    return normalize_machine_code(value, field_name=field_name)


def normalize_optional_name(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def normalize_enum(value: str, *, field_name: str, allowed: set[str] | frozenset[str]) -> str:
    normalized = normalize_machine_code(value, field_name=field_name)
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise CatalogValidationError(f"{field_name} must be one of: {allowed_values}.")
    return normalized


def normalize_runtime_source_type(value: str, *, field_name: str = "sourceType") -> str:
    normalized = normalize_enum(
        value,
        field_name=field_name,
        allowed=PROJECT_WORK_ITEM_SOURCE_TYPES,
    )
    if normalized == "import":
        return "imported"
    if normalized == "system":
        return "default"
    return normalized


def parse_decimal(value: Any, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CatalogValidationError(f"{field_name} must be numeric.") from exc


def validate_number_bounds(
    value: Decimal,
    *,
    field_name: str,
    min_value: Any | None,
    max_value: Any | None,
) -> None:
    """Raise CatalogValidationError if *value* is outside the declared [min, max] range."""
    if min_value is not None:
        try:
            lower = Decimal(str(min_value))
        except (InvalidOperation, ValueError, TypeError):
            return  # malformed bound — skip silently; seed validation will catch it
        if value < lower:
            raise CatalogValidationError(
                f"{field_name} must be ≥ {lower} (got {value})."
            )
    if max_value is not None:
        try:
            upper = Decimal(str(max_value))
        except (InvalidOperation, ValueError, TypeError):
            return
        if value > upper:
            raise CatalogValidationError(
                f"{field_name} must be ≤ {upper} (got {value})."
            )


def validate_option_code(
    option_code: str,
    *,
    field_name: str,
    allowed_codes: set[str],
) -> None:
    """Raise CatalogValidationError if *option_code* is not in the allowed set."""
    if option_code not in allowed_codes:
        readable = ", ".join(sorted(allowed_codes)) if allowed_codes else "<none defined>"
        raise CatalogValidationError(
            f"Option '{option_code}' is not valid for {field_name}. "
            f"Allowed: {readable}."
        )


def section_sort_order(section: str | None) -> int:
    return PARAMETER_SECTION_ORDER.get(section or "", 9_999)


def section_label(section: str | None) -> str:
    if not section:
        return "Uncategorized"
    return PARAMETER_SECTION_LABELS.get(section, section.replace("_", " ").title())


def validate_parameter_definition(
    *,
    parameter_code: str,
    slug: str,
    label: str,
    data_type: str,
    unit: str | None,
    section: str | None,
    min_number_value: Any | None = None,
    max_number_value: Any | None = None,
    vision_extractable: bool = False,
    manual_override_allowed: bool = True,
    default_text_value: str | None = None,
    default_number_value: Any | None = None,
    default_boolean_value: bool | None = None,
    default_option_code: str | None = None,
    option_codes: set[str] | None = None,
) -> None:
    normalized_code = normalize_machine_code(parameter_code, field_name="parameterCode")
    normalize_slug(slug, field_name="slug")

    if not isinstance(label, str) or not label.strip():
        raise CatalogValidationError(f"label is required for parameter '{normalized_code}'.")

    normalized_type = normalize_enum(
        data_type,
        field_name="dataType",
        allowed=WORK_TYPE_PARAMETER_DATA_TYPES,
    )

    if section is None:
        raise CatalogValidationError(f"section is required for parameter '{normalized_code}'.")
    normalize_enum(section, field_name="section", allowed=PARAMETER_SECTIONS)

    if not isinstance(vision_extractable, bool):
        raise CatalogValidationError(
            f"visionExtractable must be boolean for parameter '{normalized_code}'."
        )
    if not isinstance(manual_override_allowed, bool):
        raise CatalogValidationError(
            f"manualOverrideAllowed must be boolean for parameter '{normalized_code}'."
        )

    lower = parse_decimal(min_number_value, field_name="minNumberValue")
    upper = parse_decimal(max_number_value, field_name="maxNumberValue")
    if lower is not None and upper is not None and lower > upper:
        raise CatalogValidationError(
            f"minNumberValue cannot be greater than maxNumberValue for parameter '{normalized_code}'."
        )

    if normalized_type == "number":
        if not unit:
            raise CatalogValidationError(
                f"unit is required for number parameter '{normalized_code}'."
            )
    else:
        if unit is not None:
            raise CatalogValidationError(
                f"unit must be null for non-number parameter '{normalized_code}'."
            )
        if lower is not None or upper is not None:
            raise CatalogValidationError(
                f"min/max bounds can only be used on number parameter '{normalized_code}'."
            )

    allowed_option_codes = {
        normalize_machine_code(option_code, field_name="optionCode")
        for option_code in (option_codes or set())
    }
    if normalized_type == "option" and not allowed_option_codes:
        raise CatalogValidationError(
            f"Option parameter '{normalized_code}' must define enum options."
        )
    if normalized_type != "option" and allowed_option_codes:
        raise CatalogValidationError(
            f"Only option parameters can define enum options: '{normalized_code}'."
        )

    if any(
        value is not None
        for value in (
            default_text_value,
            default_number_value,
            default_boolean_value,
            default_option_code,
        )
    ):
        coerce_parameter_value(
            data_type=normalized_type,
            text_value=default_text_value,
            number_value=default_number_value,
            boolean_value=default_boolean_value,
            option_value=default_option_code,
            min_number_value=lower,
            max_number_value=upper,
            allowed_option_codes=allowed_option_codes or None,
            parameter_code=normalized_code,
        )


def validate_tenant_extra_parameter_definition(
    *,
    parameter_code: str,
    slug: str,
    label: str,
    data_type: str,
    unit: str | None,
    section: str | None,
    is_required: bool,
    status: str,
    vision_extractable: bool = False,
    manual_override_allowed: bool = True,
    min_number_value: Any | None = None,
    max_number_value: Any | None = None,
    default_text_value: str | None = None,
    default_number_value: Any | None = None,
    default_boolean_value: bool | None = None,
    default_option_code: str | None = None,
    option_codes: set[str] | None = None,
) -> None:
    normalized_code = normalize_machine_code(parameter_code, field_name="parameterCode")
    normalized_slug = normalize_slug(slug, field_name="slug")
    normalized_status = normalize_enum(status, field_name="status", allowed=TENANT_EXTRA_PARAMETER_STATUSES)
    if not normalized_code.startswith(TENANT_EXTRA_PARAMETER_CODE_PREFIX):
        raise CatalogValidationError(
            f"Tenant extra parameter '{normalized_code}' must start with '{TENANT_EXTRA_PARAMETER_CODE_PREFIX}'."
        )
    if not normalized_slug.startswith(TENANT_EXTRA_PARAMETER_CODE_PREFIX):
        raise CatalogValidationError(
            f"Tenant extra parameter slug '{normalized_slug}' must start with '{TENANT_EXTRA_PARAMETER_CODE_PREFIX}'."
        )
    if not isinstance(is_required, bool):
        raise CatalogValidationError(f"isRequired must be boolean for parameter '{normalized_code}'.")
    if normalized_status == "disabled" and vision_extractable:
        raise CatalogValidationError(
            f"Disabled tenant extra parameter '{normalized_code}' cannot be vision extractable."
        )
    if vision_extractable:
        raise CatalogValidationError(
            f"Tenant extra parameter '{normalized_code}' cannot be vision extractable until tenant analysis mappings are versioned."
        )
    validate_parameter_definition(
        parameter_code=normalized_code,
        slug=normalized_slug,
        label=label,
        data_type=data_type,
        unit=unit,
        section=section,
        min_number_value=min_number_value,
        max_number_value=max_number_value,
        vision_extractable=vision_extractable,
        manual_override_allowed=manual_override_allowed,
        default_text_value=default_text_value,
        default_number_value=default_number_value,
        default_boolean_value=default_boolean_value,
        default_option_code=default_option_code,
        option_codes=option_codes,
    )


def validate_resolved_parameter_contract(
    *,
    parameter_scope: str,
    parameter_code: str,
    slug: str,
    label: str,
    effective_label: str,
    data_type: str,
    unit: str | None,
    section: str | None,
    required: bool,
    enabled: bool,
    override_status: str | None,
    vision_extractable: bool,
    manual_override_allowed: bool,
    min_number_value: Any | None = None,
    max_number_value: Any | None = None,
    default_text_value: str | None = None,
    default_number_value: Any | None = None,
    default_boolean_value: bool | None = None,
    default_option_code: str | None = None,
    option_codes: set[str] | None = None,
) -> None:
    normalized_scope = normalize_enum(
        parameter_scope,
        field_name="parameterScope",
        allowed=PARAMETER_DEFINITION_SCOPES,
    )
    normalized_effective_label = normalize_optional_name(effective_label, field_name="effectiveLabel")
    if normalized_effective_label is None:
        raise CatalogValidationError(f"effectiveLabel is required for parameter '{parameter_code}'.")
    if not isinstance(required, bool):
        raise CatalogValidationError(f"required must be boolean for parameter '{parameter_code}'.")
    if not isinstance(enabled, bool):
        raise CatalogValidationError(f"enabled must be boolean for parameter '{parameter_code}'.")

    if normalized_scope == "global":
        normalized_override_status = (
            normalize_enum(
                override_status,
                field_name="overrideStatus",
                allowed=TENANT_PARAMETER_OVERRIDE_STATUSES,
            )
            if override_status is not None
            else None
        )
        validate_parameter_definition(
            parameter_code=parameter_code,
            slug=slug,
            label=label,
            data_type=data_type,
            unit=unit,
            section=section,
            min_number_value=min_number_value,
            max_number_value=max_number_value,
            vision_extractable=vision_extractable,
            manual_override_allowed=manual_override_allowed,
            default_text_value=default_text_value,
            default_number_value=default_number_value,
            default_boolean_value=default_boolean_value,
            default_option_code=default_option_code,
            option_codes=option_codes,
        )
        if normalized_override_status == "hidden" and enabled:
            raise CatalogValidationError(
                f"Hidden parameter '{parameter_code}' cannot resolve as enabled."
            )
        if normalized_override_status != "hidden" and not enabled:
            raise CatalogValidationError(
                f"Visible parameter '{parameter_code}' cannot resolve as disabled."
            )
        if normalized_override_status == "required" and not required:
            raise CatalogValidationError(
                f"Required override for parameter '{parameter_code}' must resolve as required."
            )
        if normalized_override_status == "optional" and required:
            raise CatalogValidationError(
                f"Optional override for parameter '{parameter_code}' must resolve as optional."
            )
        return

    normalized_status = normalize_enum(
        override_status or "active",
        field_name="status",
        allowed=TENANT_EXTRA_PARAMETER_STATUSES,
    )
    validate_tenant_extra_parameter_definition(
        parameter_code=parameter_code,
        slug=slug,
        label=label,
        data_type=data_type,
        unit=unit,
        section=section,
        is_required=required,
        status=normalized_status,
        vision_extractable=vision_extractable,
        manual_override_allowed=manual_override_allowed,
        min_number_value=min_number_value,
        max_number_value=max_number_value,
        default_text_value=default_text_value,
        default_number_value=default_number_value,
        default_boolean_value=default_boolean_value,
        default_option_code=default_option_code,
        option_codes=option_codes,
    )
    if enabled != (normalized_status == "active"):
        raise CatalogValidationError(
            f"Tenant extra parameter '{parameter_code}' resolved enabled state does not match status '{normalized_status}'."
        )


def coerce_analysis_attribute_value(
    *,
    data_type: str,
    value: Any,
    field_name: str,
) -> Any:
    normalized_type = normalize_enum(
        data_type,
        field_name="dataType",
        allowed=WORK_TYPE_PARAMETER_DATA_TYPES,
    )
    if value is None:
        raise CatalogValidationError(f"{field_name} is required.")
    if normalized_type == "number":
        return parse_decimal(value, field_name=field_name)
    if normalized_type == "boolean":
        if not isinstance(value, bool):
            raise CatalogValidationError(f"{field_name} must be boolean.")
        return value
    if normalized_type == "text":
        normalized = normalize_optional_name(value, field_name=field_name)
        if normalized is None:
            raise CatalogValidationError(f"{field_name} must be a non-empty string.")
        return normalized
    return normalize_machine_code(value, field_name=field_name)


def validate_analysis_profile_definition(
    *,
    code: str,
    version: int,
    status: str,
    provider_family: str,
    task_type: str,
    scope_code: str,
    target_objects: list[dict[str, Any]],
    ignored_objects: list[dict[str, Any]],
    extraction_rules: list[dict[str, Any]],
    validation_rules: list[dict[str, Any]],
    confidence_thresholds: list[dict[str, Any]],
    output_mappings: list[dict[str, Any]],
    fallback_mode: str,
    fallback_instructions: str | None,
    parameter_codes: set[str],
    extractable_parameter_codes: set[str],
) -> None:
    normalize_machine_code(code, field_name="analysisProfileCode")
    if not isinstance(version, int) or version < 1:
        raise CatalogValidationError("analysisProfileVersion must be an integer >= 1.")
    normalize_enum(status, field_name="analysisProfileStatus", allowed=ANALYSIS_PROFILE_STATUSES)
    normalize_machine_code(provider_family, field_name="providerFamily")
    normalize_enum(task_type, field_name="taskType", allowed=ANALYSIS_PROFILE_TASK_TYPES)
    normalize_machine_code(scope_code, field_name="scopeCode")
    normalize_enum(fallback_mode, field_name="fallbackMode", allowed=ANALYSIS_PROFILE_FALLBACK_MODES)
    if fallback_instructions is not None and not str(fallback_instructions).strip():
        raise CatalogValidationError("fallbackInstructions must be non-empty when provided.")
    if not target_objects:
        raise CatalogValidationError("Analysis profile must define at least one target object.")
    if not extraction_rules:
        raise CatalogValidationError("Analysis profile must define at least one extraction rule.")
    if not output_mappings:
        raise CatalogValidationError("Analysis profile must define at least one output mapping.")

    seen_target_codes: set[str] = set()
    for target in target_objects:
        target_code = normalize_machine_code(target["code"], field_name="targetObjectCode")
        if target_code in seen_target_codes:
            raise CatalogValidationError(f"Duplicate target object code '{target_code}'.")
        seen_target_codes.add(target_code)
        normalize_enum(target["object_role"], field_name="objectRole", allowed=ANALYSIS_PROFILE_OBJECT_ROLES)
        if not isinstance(target.get("label"), str) or not target["label"].strip():
            raise CatalogValidationError(f"Target object '{target_code}' must define label.")

    seen_ignored_codes: set[str] = set()
    for ignored in ignored_objects:
        ignored_code = normalize_machine_code(ignored["code"], field_name="ignoredObjectCode")
        if ignored_code in seen_ignored_codes:
            raise CatalogValidationError(f"Duplicate ignored object code '{ignored_code}'.")
        seen_ignored_codes.add(ignored_code)

    seen_extraction_codes: set[str] = set()
    for rule in extraction_rules:
        attribute_code = normalize_machine_code(rule["attribute_code"], field_name="attributeCode")
        if attribute_code in seen_extraction_codes:
            raise CatalogValidationError(f"Duplicate extraction attribute '{attribute_code}'.")
        seen_extraction_codes.add(attribute_code)
        normalize_enum(rule["data_type"], field_name="dataType", allowed=WORK_TYPE_PARAMETER_DATA_TYPES)
        source_object_code = normalize_machine_code(
            rule["source_object_code"],
            field_name="sourceObjectCode",
        )
        if source_object_code not in seen_target_codes:
            raise CatalogValidationError(
                f"Extraction rule '{attribute_code}' references unknown source object '{source_object_code}'."
            )
        parameter_code = normalize_machine_code(rule["target_parameter_code"], field_name="targetParameterCode")
        if parameter_code not in parameter_codes:
            raise CatalogValidationError(
                f"Extraction rule '{attribute_code}' references unknown target parameter '{parameter_code}'."
            )
        if parameter_code not in extractable_parameter_codes:
            raise CatalogValidationError(
                f"Extraction rule '{attribute_code}' references non-vision-extractable parameter '{parameter_code}'."
            )

    for rule in validation_rules:
        normalize_machine_code(rule["code"], field_name="validationRuleCode")
        normalize_enum(
            rule["rule_type"],
            field_name="validationRuleType",
            allowed=ANALYSIS_PROFILE_VALIDATION_RULE_TYPES,
        )
        normalize_enum(
            rule["severity"],
            field_name="validationSeverity",
            allowed=ANALYSIS_PROFILE_VALIDATION_SEVERITIES,
        )
        target_attribute_code = rule.get("target_attribute_code")
        if target_attribute_code is not None:
            normalized_attribute = normalize_machine_code(
                target_attribute_code,
                field_name="targetAttributeCode",
            )
            if normalized_attribute not in seen_extraction_codes:
                raise CatalogValidationError(
                    f"Validation rule references unknown attribute '{normalized_attribute}'."
                )

    for threshold in confidence_thresholds:
        attribute_code = normalize_machine_code(
            threshold["attribute_code"],
            field_name="confidenceAttributeCode",
        )
        if attribute_code not in seen_extraction_codes:
            raise CatalogValidationError(
                f"Confidence threshold references unknown attribute '{attribute_code}'."
            )
        min_confidence = parse_decimal(
            threshold["min_confidence"],
            field_name="minConfidence",
        )
        preferred_confidence = parse_decimal(
            threshold["preferred_confidence"],
            field_name="preferredConfidence",
        )
        if min_confidence is None or preferred_confidence is None:
            raise CatalogValidationError("Confidence thresholds require both min and preferred confidence.")
        if min_confidence < 0 or preferred_confidence > 1 or min_confidence > preferred_confidence:
            raise CatalogValidationError(
                f"Invalid confidence thresholds for attribute '{attribute_code}'."
            )
        normalize_enum(
            threshold["action_below_threshold"],
            field_name="actionBelowThreshold",
            allowed=ANALYSIS_PROFILE_CONFIDENCE_ACTIONS,
        )

    for mapping in output_mappings:
        normalize_machine_code(mapping["code"], field_name="outputMappingCode")
        normalize_enum(
            mapping["target_entity"],
            field_name="targetEntity",
            allowed=ANALYSIS_PROFILE_MAPPING_TARGET_ENTITIES,
        )
        source_attribute_code = normalize_machine_code(
            mapping["source_attribute_code"],
            field_name="sourceAttributeCode",
        )
        if source_attribute_code not in seen_extraction_codes and source_attribute_code not in {
            "object-type",
            "surface-condition",
            "recommended-scope",
            "estimated-quantity",
            "estimated-unit",
            "estimated-area-sqm",
            "area-confidence",
            "mask-polygon",
            "materials",
            "workflow-steps",
            "estimated-total-days",
            "labor-hours-total",
        }:
            raise CatalogValidationError(
                f"Output mapping references unsupported source attribute '{source_attribute_code}'."
            )
        parameter_code = mapping.get("target_parameter_code")  # type: ignore[assignment]
        if parameter_code is not None:
            normalized_parameter_code = normalize_machine_code(
                parameter_code,
                field_name="targetParameterCode",
            )
            if normalized_parameter_code not in parameter_codes:
                raise CatalogValidationError(
                    f"Output mapping references unknown target parameter '{normalized_parameter_code}'."
                )


def validate_pricing_profile_definition(
    *,
    code: str,
    version: int,
    status: str,
    pricing_basis: str,
    currency: str,
    pricing_strategy: str,
    labor_rate_source: str,
    material_pricing_source: str,
    min_job_price: Any | None,
    required_inputs: list[dict[str, Any]],
    base_rules: list[dict[str, Any]],
    adjustment_rules: list[dict[str, Any]],
    labor_assumptions: list[dict[str, Any]],
    material_assumptions: list[dict[str, Any]],
    parameter_codes: set[str],
) -> None:
    normalize_machine_code(code, field_name="catalogPricingProfileCode")
    if not isinstance(version, int) or version < 1:
        raise CatalogValidationError("catalogPricingProfileVersion must be an integer >= 1.")
    normalize_enum(
        status,
        field_name="catalogPricingProfileStatus",
        allowed=CATALOG_PRICING_PROFILE_STATUSES,
    )
    normalize_enum(
        pricing_basis,
        field_name="pricingBasis",
        allowed=CATALOG_PRICING_BASES,
    )
    if not isinstance(currency, str) or not currency.strip():
        raise CatalogValidationError("currency is required for catalog pricing profiles.")
    normalize_enum(
        pricing_strategy,
        field_name="pricingStrategy",
        allowed=CATALOG_PRICING_STRATEGIES,
    )
    normalize_enum(
        labor_rate_source,
        field_name="laborRateSource",
        allowed=LABOR_RATE_SOURCES,
    )
    normalize_enum(
        material_pricing_source,
        field_name="materialPricingSource",
        allowed=MATERIAL_PRICING_SOURCES,
    )
    minimum_price = parse_decimal(min_job_price, field_name="minJobPrice")
    if minimum_price is not None and minimum_price < 0:
        raise CatalogValidationError("minJobPrice cannot be negative.")
    if not required_inputs:
        raise CatalogValidationError("Catalog pricing profile must declare required inputs.")
    if not base_rules:
        raise CatalogValidationError("Catalog pricing profile must define at least one base rule.")

    seen_required_codes: set[str] = set()
    required_input_sources: set[tuple[str, str]] = set()
    for required_input in required_inputs:
        input_code = normalize_machine_code(required_input["code"], field_name="requiredInputCode")
        if input_code in seen_required_codes:
            raise CatalogValidationError(f"Duplicate required input code '{input_code}'.")
        seen_required_codes.add(input_code)
        normalize_enum(
            required_input["source_type"],
            field_name="requiredInputSourceType",
            allowed=CATALOG_PRICING_REQUIRED_INPUT_SOURCES,
        )
        source_key = normalize_machine_code(required_input["source_key"], field_name="requiredInputSourceKey")
        source_type = required_input["source_type"]
        if source_type == "parameter" and source_key not in parameter_codes:
            raise CatalogValidationError(
                f"Required input '{input_code}' references unknown parameter '{source_key}'."
            )
        if source_type == "work_item_field" and source_key not in CATALOG_PRICING_WORK_ITEM_FIELDS:
            raise CatalogValidationError(
                f"Required input '{input_code}' references unsupported work item field '{source_key}'."
            )
        required_input_sources.add((source_type, source_key))

    labor_assumption_codes: set[str] = set()
    for assumption in labor_assumptions:
        assumption_code = normalize_machine_code(assumption["code"], field_name="laborAssumptionCode")
        if assumption_code in labor_assumption_codes:
            raise CatalogValidationError(f"Duplicate labor assumption '{assumption_code}'.")
        labor_assumption_codes.add(assumption_code)
        normalize_enum(
            assumption["quantity_source_type"],
            field_name="laborAssumptionQuantitySourceType",
            allowed=CATALOG_PRICING_RULE_QUANTITY_SOURCES,
        )
        source_key = assumption.get("quantity_source_key")  # type: ignore[assignment]
        if assumption["quantity_source_type"] == "parameter":
            normalized_source = normalize_machine_code(
                source_key,
                field_name="laborAssumptionQuantitySourceKey",
            )
            if normalized_source not in parameter_codes:
                raise CatalogValidationError(
                    f"Labor assumption '{assumption_code}' references unknown parameter '{normalized_source}'."
                )
        if assumption["quantity_source_type"] == "work_item_field":
            normalized_source = normalize_machine_code(
                source_key,
                field_name="laborAssumptionQuantitySourceKey",
            )
            if normalized_source not in CATALOG_PRICING_WORK_ITEM_FIELDS:
                raise CatalogValidationError(
                    f"Labor assumption '{assumption_code}' references unsupported work item field '{normalized_source}'."
                )
        if parse_decimal(assumption["hours_per_unit"], field_name="hoursPerUnit") is None:
            raise CatalogValidationError(
                f"Labor assumption '{assumption_code}' must define hoursPerUnit."
            )

    material_assumption_codes: set[str] = set()
    for assumption in material_assumptions:
        assumption_code = normalize_machine_code(assumption["code"], field_name="materialAssumptionCode")
        if assumption_code in material_assumption_codes:
            raise CatalogValidationError(f"Duplicate material assumption '{assumption_code}'.")
        material_assumption_codes.add(assumption_code)
        normalize_enum(
            assumption["quantity_source_type"],
            field_name="materialAssumptionQuantitySourceType",
            allowed=CATALOG_PRICING_RULE_QUANTITY_SOURCES,
        )
        source_key = assumption.get("quantity_source_key")  # type: ignore[assignment]
        if assumption["quantity_source_type"] == "parameter":
            normalized_source = normalize_machine_code(
                source_key,
                field_name="materialAssumptionQuantitySourceKey",
            )
            if normalized_source not in parameter_codes:
                raise CatalogValidationError(
                    f"Material assumption '{assumption_code}' references unknown parameter '{normalized_source}'."
                )
        if assumption["quantity_source_type"] == "work_item_field":
            normalized_source = normalize_machine_code(
                source_key,
                field_name="materialAssumptionQuantitySourceKey",
            )
            if normalized_source not in CATALOG_PRICING_WORK_ITEM_FIELDS:
                raise CatalogValidationError(
                    f"Material assumption '{assumption_code}' references unsupported work item field '{normalized_source}'."
                )
        quantity_per_unit = parse_decimal(assumption["quantity_per_unit"], field_name="quantityPerUnit")
        if quantity_per_unit is None or quantity_per_unit < 0:
            raise CatalogValidationError(
                f"Material assumption '{assumption_code}' must define non-negative quantityPerUnit."
            )
        if not isinstance(assumption.get("unit"), str) or not assumption["unit"].strip():
            raise CatalogValidationError(
                f"Material assumption '{assumption_code}' must define unit."
            )

    base_rule_codes: set[str] = set()
    for rule in base_rules:
        rule_code = normalize_machine_code(rule["code"], field_name="baseRuleCode")
        if rule_code in base_rule_codes:
            raise CatalogValidationError(f"Duplicate base rule '{rule_code}'.")
        base_rule_codes.add(rule_code)
        normalize_enum(
            rule["line_type"],
            field_name="baseRuleLineType",
            allowed=CATALOG_PRICING_RULE_LINE_TYPES,
        )
        normalize_enum(
            rule["calculation_method"],
            field_name="baseRuleCalculationMethod",
            allowed=CATALOG_PRICING_RULE_CALCULATION_METHODS,
        )
        source_type = normalize_enum(
            rule["quantity_source_type"],
            field_name="baseRuleQuantitySourceType",
            allowed=CATALOG_PRICING_RULE_QUANTITY_SOURCES,
        )
        source_key = rule.get("quantity_source_key")  # type: ignore[assignment]
        if source_type == "parameter":
            normalized_source = normalize_machine_code(source_key, field_name="baseRuleQuantitySourceKey")
            if normalized_source not in parameter_codes:
                raise CatalogValidationError(
                    f"Base rule '{rule_code}' references unknown parameter '{normalized_source}'."
                )
        elif source_type == "work_item_field":
            normalized_source = normalize_machine_code(source_key, field_name="baseRuleQuantitySourceKey")
            if normalized_source not in CATALOG_PRICING_WORK_ITEM_FIELDS:
                raise CatalogValidationError(
                    f"Base rule '{rule_code}' references unsupported work item field '{normalized_source}'."
                )
        elif source_key is not None and str(source_key).strip():
            normalize_machine_code(source_key, field_name="baseRuleQuantitySourceKey")

        quantity_multiplier = parse_decimal(rule["quantity_multiplier"], field_name="quantityMultiplier")
        if quantity_multiplier is None or quantity_multiplier <= 0:
            raise CatalogValidationError(
                f"Base rule '{rule_code}' must define quantityMultiplier > 0."
            )
        if not isinstance(rule.get("unit"), str) or not rule["unit"].strip():
            raise CatalogValidationError(f"Base rule '{rule_code}' must define unit.")
        rate_source = normalize_enum(
            rule["rate_source"],
            field_name="baseRuleRateSource",
            allowed=CATALOG_PRICING_RULE_RATE_SOURCES,
        )
        rate_value = parse_decimal(rule.get("rate_value"), field_name="rateValue")
        if rate_source in {"catalog_unit_rate", "catalog_flat_rate"} and rate_value is None:
            raise CatalogValidationError(
                f"Base rule '{rule_code}' requires rateValue for rate source '{rate_source}'."
            )
        labor_assumption_code = rule.get("labor_assumption_code")
        if labor_assumption_code is not None:
            normalized_labor_assumption = normalize_machine_code(
                labor_assumption_code,
                field_name="laborAssumptionCode",
            )
            if normalized_labor_assumption not in labor_assumption_codes:
                raise CatalogValidationError(
                    f"Base rule '{rule_code}' references unknown labor assumption '{normalized_labor_assumption}'."
                )
        material_assumption_code = rule.get("material_assumption_code")
        if material_assumption_code is not None:
            normalized_material_assumption = normalize_machine_code(
                material_assumption_code,
                field_name="materialAssumptionCode",
            )
            if normalized_material_assumption not in material_assumption_codes:
                raise CatalogValidationError(
                    f"Base rule '{rule_code}' references unknown material assumption '{normalized_material_assumption}'."
                )

    seen_adjustment_codes: set[str] = set()
    for rule in adjustment_rules:
        rule_code = normalize_machine_code(rule["code"], field_name="adjustmentRuleCode")
        if rule_code in seen_adjustment_codes:
            raise CatalogValidationError(f"Duplicate adjustment rule '{rule_code}'.")
        seen_adjustment_codes.add(rule_code)
        target_scope = normalize_enum(
            rule["target_scope"],
            field_name="adjustmentTargetScope",
            allowed=CATALOG_PRICING_ADJUSTMENT_TARGET_SCOPES,
        )
        target_line_type = rule.get("target_line_type")
        if target_line_type is not None:
            normalize_enum(
                target_line_type,
                field_name="adjustmentTargetLineType",
                allowed=CATALOG_PRICING_RULE_LINE_TYPES,
            )
        target_base_rule_code = rule.get("target_base_rule_code")
        if target_scope == "base_rule":
            if target_base_rule_code is None:
                raise CatalogValidationError(
                    f"Adjustment rule '{rule_code}' must declare targetBaseRuleCode."
                )
            normalized_target_base_rule = normalize_machine_code(
                target_base_rule_code,
                field_name="targetBaseRuleCode",
            )
            if normalized_target_base_rule not in base_rule_codes:
                raise CatalogValidationError(
                    f"Adjustment rule '{rule_code}' references unknown base rule '{normalized_target_base_rule}'."
                )
        normalize_enum(
            rule["operation"],
            field_name="adjustmentOperation",
            allowed=CATALOG_PRICING_ADJUSTMENT_OPERATIONS,
        )
        adjustment_value = parse_decimal(rule["adjustment_value"], field_name="adjustmentValue")
        if adjustment_value is None:
            raise CatalogValidationError(
                f"Adjustment rule '{rule_code}' must define adjustmentValue."
            )
        condition_source_type = normalize_enum(
            rule["condition_source_type"],
            field_name="adjustmentConditionSourceType",
            allowed=CATALOG_PRICING_REQUIRED_INPUT_SOURCES,
        )
        condition_source_key = normalize_machine_code(
            rule["condition_source_key"],
            field_name="adjustmentConditionSourceKey",
        )
        if condition_source_type == "parameter" and condition_source_key not in parameter_codes:
            raise CatalogValidationError(
                f"Adjustment rule '{rule_code}' references unknown parameter '{condition_source_key}'."
            )
        if condition_source_type == "work_item_field" and condition_source_key not in CATALOG_PRICING_WORK_ITEM_FIELDS:
            raise CatalogValidationError(
                f"Adjustment rule '{rule_code}' references unsupported work item field '{condition_source_key}'."
            )
        normalize_enum(
            rule["condition_operator"],
            field_name="adjustmentConditionOperator",
            allowed=CATALOG_PRICING_ADJUSTMENT_CONDITION_OPERATORS,
        )
        populated_condition_values = sum(
            value is not None
            for value in (
                rule.get("condition_text_value"),
                rule.get("condition_number_value"),
                rule.get("condition_boolean_value"),
                rule.get("condition_option_code"),
            )
        )
        if rule["condition_operator"] != "true" and populated_condition_values == 0:
            raise CatalogValidationError(
                f"Adjustment rule '{rule_code}' must define a typed comparison value."
            )
        if condition_source_type == "parameter" and (condition_source_type, condition_source_key) not in required_input_sources:
            raise CatalogValidationError(
                f"Adjustment rule '{rule_code}' depends on parameter '{condition_source_key}' which is not declared as a required input."
            )


def coerce_parameter_value(
    *,
    data_type: str,
    text_value: str | None = None,
    number_value: Any | None = None,
    boolean_value: bool | None = None,
    option_value: str | None = None,
    # Optional bounds — only applied to number parameters.
    min_number_value: Any | None = None,
    max_number_value: Any | None = None,
    # Optional allowed option codes — only applied to option parameters.
    allowed_option_codes: set[str] | None = None,
    # Used in error messages.
    parameter_code: str = "parameter",
) -> dict[str, Any]:
    normalized_type = normalize_enum(
        data_type,
        field_name="data_type",
        allowed=WORK_TYPE_PARAMETER_DATA_TYPES,
    )
    text = normalize_optional_name(text_value, field_name="textValue")
    number = parse_decimal(number_value, field_name="numberValue")
    option = normalize_machine_code(option_value, field_name="optionValue") if option_value is not None else None

    populated = [value is not None for value in (text, number, boolean_value, option)]
    if sum(populated) != 1:
        raise CatalogValidationError("Exactly one typed parameter value must be provided.")

    if normalized_type == "text" and text is None:
        raise CatalogValidationError("textValue is required for text parameters.")
    if normalized_type == "number" and number is None:
        raise CatalogValidationError("numberValue is required for number parameters.")
    if normalized_type == "boolean" and boolean_value is None:
        raise CatalogValidationError("booleanValue is required for boolean parameters.")
    if normalized_type == "option" and option is None:
        raise CatalogValidationError("optionValue is required for option parameters.")

    if normalized_type != "text" and text is not None:
        raise CatalogValidationError("textValue can only be used for text parameters.")
    if normalized_type != "number" and number is not None:
        raise CatalogValidationError("numberValue can only be used for number parameters.")
    if normalized_type != "boolean" and boolean_value is not None:
        raise CatalogValidationError("booleanValue can only be used for boolean parameters.")
    if normalized_type != "option" and option is not None:
        raise CatalogValidationError("optionValue can only be used for option parameters.")

    # Bounds check for number parameters.
    if normalized_type == "number" and number is not None:
        validate_number_bounds(
            number,
            field_name=parameter_code,
            min_value=min_number_value,
            max_value=max_number_value,
        )

    # Option code whitelist check.
    if normalized_type == "option" and option is not None and allowed_option_codes is not None:
        validate_option_code(option, field_name=parameter_code, allowed_codes=allowed_option_codes)

    return {
        "value_text": text,
        "value_number": number,
        "value_boolean": boolean_value,
        "value_option_code": option,
    }
