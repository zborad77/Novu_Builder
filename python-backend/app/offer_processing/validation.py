"""AI output validation layer — security boundary between AI and database.

Rule: AI output NEVER goes directly to the DB.
Pipeline:
    raw AI output (measurements only — no prices)
    → schema validation   (Pydantic — structure and types)
    → business validation (domain rules — known codes, bounds)
    → normalization       (rounding, defaults)
    → ValidatedMeasurements (safe to persist; pricing computed separately)

Full price separation: the AI returns measured quantities only. Prices are
computed deterministically server-side from the tenant catalog/pricing
profile, NOT taken from the model. See app/offer_processing/provider.py.

All validation failures are recorded — tracking AI output quality over time.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.offer_processing.domain import AGENT_OUTCOME_INSUFFICIENT_DATA

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_MEASUREMENTS = 100
MAX_QUANTITY = Decimal("100000")
MAX_WARNINGS = 20
MAX_QUESTIONS = 10

ALLOWED_SURFACE_CONDITIONS = frozenset({"good", "requires_attention", "critical"})
ALLOWED_SCOPES = frozenset({"cleaning", "local_repair", "full_reconstruction"})

# ---------------------------------------------------------------------------
# Raw AI output schemas (Pydantic)
# ---------------------------------------------------------------------------


class RawMeasurementItem(BaseModel):
    model_config = {"extra": "ignore"}

    work_type_code: str = Field(min_length=1, max_length=64)
    quantity: float = Field(gt=0, le=100_000)
    unit: str = Field(default="ks", max_length=32)
    surface_condition: str = Field(max_length=32)
    recommended_scope: str = Field(default="", max_length=64)
    description: str = Field(default="", max_length=512)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("work_type_code")
    @classmethod
    def _code_format(cls, v: str) -> str:
        return v.strip().lower()


class RawMeasurementOutput(BaseModel):
    """Schema for a successful measurement extraction (no prices)."""
    model_config = {"extra": "ignore"}

    outcome: str = Field(default="offer_generated")
    measurements: list[RawMeasurementItem] = Field(min_length=1, max_length=MAX_MEASUREMENTS)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list, max_length=MAX_WARNINGS)


class RawInsufficientDataOutput(BaseModel):
    """Schema when AI needs more information."""
    model_config = {"extra": "ignore"}

    outcome: str
    questions: list[str] = Field(min_length=1, max_length=MAX_QUESTIONS)

# ---------------------------------------------------------------------------
# Validated result types
# ---------------------------------------------------------------------------


class ValidatedMeasurementItem(BaseModel):
    work_type_code: str
    quantity: Decimal
    unit: str
    surface_condition: str
    recommended_scope: str
    description: str
    confidence: float


class ValidatedMeasurements(BaseModel):
    """Measurements safe to persist. Prices are computed downstream."""
    outcome: str
    measurements: list[ValidatedMeasurementItem]
    overall_confidence: float
    warnings: list[str]


class InsufficientDataResult(BaseModel):
    outcome: str
    questions: list[str]


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class OfferValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class OfferOutputValidator:
    """Validates and normalizes raw AI measurement output.

    Returns ValidatedMeasurements or InsufficientDataResult.
    Raises OfferValidationError on any failure.

    `known_work_type_codes` should ALWAYS be passed in production — it is the
    whitelist preventing the model from inventing work type codes that do not
    exist in the catalog.
    """

    def __init__(self, known_work_type_codes: frozenset[str] | None = None) -> None:
        self._known_codes = known_work_type_codes

    def validate(
        self, raw: dict[str, Any]
    ) -> ValidatedMeasurements | InsufficientDataResult:
        outcome = raw.get("outcome", "offer_generated")

        if outcome == AGENT_OUTCOME_INSUFFICIENT_DATA:
            return self._validate_insufficient_data(raw)
        return self._validate_measurements(raw)

    def _validate_insufficient_data(self, raw: dict[str, Any]) -> InsufficientDataResult:
        try:
            parsed = RawInsufficientDataOutput.model_validate(raw)
        except Exception as exc:
            raise OfferValidationError([f"insufficient_data schema: {exc}"]) from exc
        return InsufficientDataResult(outcome=parsed.outcome, questions=parsed.questions)

    def _validate_measurements(self, raw: dict[str, Any]) -> ValidatedMeasurements:
        errors: list[str] = []

        # 0 — Fail-closed: a work_type_code whitelist is MANDATORY for a priced offer
        #     path (Constitution Art. 6 & 9; INV-004, INV-015). `None` means the caller
        #     could not prove which codes are valid — reject rather than pass permissively.
        if self._known_codes is None:
            raise OfferValidationError(
                ["fail-closed: no work_type_code whitelist provided for validation"]
            )

        # 1 — Schema validation
        try:
            parsed = RawMeasurementOutput.model_validate(raw)
        except Exception as exc:
            raise OfferValidationError([f"schema: {exc}"]) from exc

        # 2 — Business validation: surface condition + scope enums
        for i, item in enumerate(parsed.measurements):
            if item.surface_condition not in ALLOWED_SURFACE_CONDITIONS:
                errors.append(
                    f"item[{i}] {item.work_type_code}: "
                    f"surface_condition '{item.surface_condition}' not allowed"
                )
            if item.recommended_scope and item.recommended_scope not in ALLOWED_SCOPES:
                errors.append(
                    f"item[{i}] {item.work_type_code}: "
                    f"recommended_scope '{item.recommended_scope}' not allowed"
                )

        # 3 — Business validation: work_type_code whitelist
        if self._known_codes is not None:
            unknown = [
                item.work_type_code
                for item in parsed.measurements
                if item.work_type_code not in self._known_codes
            ]
            if unknown:
                errors.append(f"unknown work_type_codes: {unknown}")

        if errors:
            raise OfferValidationError(errors)

        # 4 — Normalization
        return ValidatedMeasurements(
            outcome=parsed.outcome,
            measurements=[
                ValidatedMeasurementItem(
                    work_type_code=item.work_type_code,
                    quantity=Decimal(str(item.quantity)).quantize(
                        Decimal("0.0001"), ROUND_HALF_UP
                    ),
                    unit=item.unit,
                    surface_condition=item.surface_condition,
                    recommended_scope=item.recommended_scope,
                    description=item.description,
                    confidence=item.confidence,
                )
                for item in parsed.measurements
            ],
            overall_confidence=parsed.overall_confidence,
            warnings=parsed.warnings[:MAX_WARNINGS],
        )
