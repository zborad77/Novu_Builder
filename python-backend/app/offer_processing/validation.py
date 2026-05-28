"""AI output validation layer — security boundary between AI and database.

Rule: AI output NEVER goes directly to the DB.
Pipeline:
    raw AI output
    → schema validation   (Pydantic — structure and types)
    → business validation (domain rules — prices, codes, consistency)
    → normalization       (rounding, defaults)
    → ValidatedOffer      (safe to persist)

All validation failures are recorded — tracking AI output quality over time.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.offer_processing.domain import AGENT_OUTCOME_INSUFFICIENT_DATA

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_LINE_ITEMS = 100
MAX_PRICE_CZK = Decimal("50_000_000")   # 50M CZK hard ceiling
MIN_PRICE_CZK = Decimal("0")
ALLOWED_CURRENCIES = frozenset({"CZK", "EUR", "USD"})
MAX_WARNINGS = 20
MAX_QUESTIONS = 10

# ---------------------------------------------------------------------------
# Raw AI output schemas (Pydantic)
# ---------------------------------------------------------------------------


class RawLineItem(BaseModel):
    model_config = {"extra": "ignore"}

    work_type_code: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=512)
    quantity: float = Field(gt=0, le=100_000)
    unit: str = Field(default="ks", max_length=32)
    unit_price_czk: float = Field(ge=0, le=10_000_000)
    total_price_czk: float = Field(ge=0, le=50_000_000)

    @field_validator("work_type_code")
    @classmethod
    def _code_format(cls, v: str) -> str:
        return v.strip().lower()


class RawOfferOutput(BaseModel):
    """Schema for a successful offer generation."""
    model_config = {"extra": "ignore"}

    outcome: str = Field(default="offer_generated")
    line_items: list[RawLineItem] = Field(min_length=1, max_length=MAX_LINE_ITEMS)
    total_price_czk: float = Field(ge=0, le=50_000_000)
    confidence_score: float = Field(ge=0.0, le=1.0)
    currency: str = Field(default="CZK", max_length=8)
    warnings: list[str] = Field(default_factory=list, max_length=MAX_WARNINGS)

    @field_validator("currency")
    @classmethod
    def _currency_allowed(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ALLOWED_CURRENCIES:
            raise ValueError(f"currency '{v}' not in allowed set {ALLOWED_CURRENCIES}")
        return v

    @model_validator(mode="after")
    def _no_duplicate_codes(self) -> "RawOfferOutput":
        codes = [item.work_type_code for item in self.line_items]
        if len(codes) != len(set(codes)):
            raise ValueError("duplicate work_type_code values in line_items")
        return self


class RawInsufficientDataOutput(BaseModel):
    """Schema when AI needs more information."""
    model_config = {"extra": "ignore"}

    outcome: str
    questions: list[str] = Field(min_length=1, max_length=MAX_QUESTIONS)

# ---------------------------------------------------------------------------
# Validated result types
# ---------------------------------------------------------------------------


class ValidatedLineItem(BaseModel):
    work_type_code: str
    description: str
    quantity: Decimal
    unit: str
    unit_price_czk: Decimal
    total_price_czk: Decimal


class ValidatedOffer(BaseModel):
    outcome: str
    line_items: list[ValidatedLineItem]
    total_price_czk: Decimal
    confidence_score: float
    currency: str
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
    """Validates and normalizes raw AI output.

    Returns ValidatedOffer or InsufficientDataResult.
    Raises OfferValidationError on any failure.
    """

    def __init__(self, known_work_type_codes: frozenset[str] | None = None) -> None:
        self._known_codes = known_work_type_codes

    def validate(self, raw: dict[str, Any]) -> ValidatedOffer | InsufficientDataResult:
        outcome = raw.get("outcome", "offer_generated")

        if outcome == AGENT_OUTCOME_INSUFFICIENT_DATA:
            return self._validate_insufficient_data(raw)
        return self._validate_offer(raw)

    def _validate_insufficient_data(self, raw: dict[str, Any]) -> InsufficientDataResult:
        try:
            parsed = RawInsufficientDataOutput.model_validate(raw)
        except Exception as exc:
            raise OfferValidationError([f"insufficient_data schema: {exc}"]) from exc
        return InsufficientDataResult(outcome=parsed.outcome, questions=parsed.questions)

    def _validate_offer(self, raw: dict[str, Any]) -> ValidatedOffer:
        errors: list[str] = []

        # 1 — Schema validation
        try:
            parsed = RawOfferOutput.model_validate(raw)
        except Exception as exc:
            raise OfferValidationError([f"schema: {exc}"]) from exc

        # 2 — Business validation: sum consistency
        computed_sum = sum(
            Decimal(str(item.total_price_czk)) for item in parsed.line_items
        )
        declared_total = Decimal(str(parsed.total_price_czk))
        tolerance = Decimal("0.02")
        if abs(computed_sum - declared_total) > tolerance:
            errors.append(
                f"total_price_czk={declared_total} != sum(line_items)={computed_sum}"
            )

        # 3 — Business validation: work_type_code whitelist
        if self._known_codes is not None:
            unknown = [
                item.work_type_code
                for item in parsed.line_items
                if item.work_type_code not in self._known_codes
            ]
            if unknown:
                errors.append(f"unknown work_type_codes: {unknown}")

        # 4 — Business validation: individual item consistency
        for i, item in enumerate(parsed.line_items):
            expected = Decimal(str(item.quantity)) * Decimal(str(item.unit_price_czk))
            actual = Decimal(str(item.total_price_czk))
            if abs(expected - actual) > Decimal("0.02"):
                errors.append(
                    f"item[{i}] {item.work_type_code}: "
                    f"qty*unit_price={expected} != total={actual}"
                )

        if errors:
            raise OfferValidationError(errors)

        # 5 — Normalization
        return ValidatedOffer(
            outcome=parsed.outcome,
            line_items=[
                ValidatedLineItem(
                    work_type_code=item.work_type_code,
                    description=item.description,
                    quantity=Decimal(str(item.quantity)).quantize(Decimal("0.0001"), ROUND_HALF_UP),
                    unit=item.unit,
                    unit_price_czk=Decimal(str(item.unit_price_czk)).quantize(Decimal("0.01"), ROUND_HALF_UP),
                    total_price_czk=Decimal(str(item.total_price_czk)).quantize(Decimal("0.01"), ROUND_HALF_UP),
                )
                for item in parsed.line_items
            ],
            total_price_czk=declared_total.quantize(Decimal("0.01"), ROUND_HALF_UP),
            confidence_score=parsed.confidence_score,
            currency=parsed.currency,
            warnings=parsed.warnings[:MAX_WARNINGS],
        )
