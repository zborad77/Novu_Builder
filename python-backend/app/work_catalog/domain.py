from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


CODE_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")

WORK_TYPE_STATES = frozenset({"active", "hidden", "deprecated"})
WORK_TYPE_PARAMETER_DATA_TYPES = frozenset({"number", "text", "boolean", "option"})
TENANT_WORK_TYPE_SETTING_STATUSES = frozenset({"inherited", "enabled", "disabled"})
PROJECT_WORK_ITEM_STATUSES = frozenset({"draft", "resolved", "accepted", "rejected"})
PROJECT_WORK_ITEM_SOURCE_TYPES = frozenset({"manual", "vision", "import", "system"})
VISION_DETECTION_STATUSES = frozenset({"pending", "accepted", "rejected", "linked"})
ANALYSIS_PROFILE_TASK_TYPES = frozenset({"classification", "detection", "measurement", "hybrid"})
CATALOG_PRICING_STRATEGIES = frozenset({"tenant_pricebook", "fixed_formula", "manual_review"})
LABOR_RATE_SOURCES = frozenset({"tenant_default", "catalog_default", "manual"})
MATERIAL_PRICING_SOURCES = frozenset({"tenant_pricebook", "catalog_default", "manual"})

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
