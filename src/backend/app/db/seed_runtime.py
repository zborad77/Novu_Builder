from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Mapping, Sequence

import structlog
from sqlalchemy.ext.asyncio import AsyncSession


logger = structlog.get_logger(__name__)


class SeedWriteMode(StrEnum):
    AUTHORITATIVE_UPSERT = "authoritative_upsert"
    INSERT_IF_ABSENT = "insert_if_absent"


@dataclass(frozen=True, slots=True)
class SeedModelPlan:
    name: str
    model: type[Any]
    rows: Sequence[Mapping[str, Any]]
    mode: SeedWriteMode = SeedWriteMode.AUTHORITATIVE_UPSERT


@dataclass(frozen=True, slots=True)
class SeedModelReport:
    name: str
    mode: SeedWriteMode
    inserted: int
    updated: int
    unchanged: int
    skipped: int

    @property
    def total_rows(self) -> int:
        return self.inserted + self.updated + self.unchanged + self.skipped


@dataclass(frozen=True, slots=True)
class SeedPlanReport:
    plan_name: str
    model_reports: tuple[SeedModelReport, ...]

    @property
    def inserted(self) -> int:
        return sum(report.inserted for report in self.model_reports)

    @property
    def updated(self) -> int:
        return sum(report.updated for report in self.model_reports)

    @property
    def unchanged(self) -> int:
        return sum(report.unchanged for report in self.model_reports)

    @property
    def skipped(self) -> int:
        return sum(report.skipped for report in self.model_reports)

    @property
    def total_rows(self) -> int:
        return sum(report.total_rows for report in self.model_reports)


async def apply_seed_model_plan(
    session: AsyncSession,
    plan: SeedModelPlan,
) -> SeedModelReport:
    inserted = 0
    updated = 0
    unchanged = 0
    skipped = 0

    for row in plan.rows:
        existing = await session.get(plan.model, row["id"])
        if existing is None:
            session.add(plan.model(**row))
            inserted += 1
            continue

        if plan.mode == SeedWriteMode.INSERT_IF_ABSENT:
            skipped += 1
            continue

        changed = False
        for key, value in row.items():
            if not _seed_values_equal(getattr(existing, key), value):
                setattr(existing, key, value)
                changed = True

        if changed:
            updated += 1
        else:
            unchanged += 1

    return SeedModelReport(
        name=plan.name,
        mode=plan.mode,
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        skipped=skipped,
    )


async def execute_seed_plan(
    session: AsyncSession,
    *,
    plan_name: str,
    model_plans: Sequence[SeedModelPlan],
) -> SeedPlanReport:
    logger.info("db.seed_plan.start", plan=plan_name, model_count=len(model_plans))

    reports: list[SeedModelReport] = []
    for model_plan in model_plans:
        report = await apply_seed_model_plan(session, model_plan)
        reports.append(report)
        logger.info(
            "db.seed_plan.model",
            plan=plan_name,
            name=report.name,
            mode=report.mode,
            inserted=report.inserted,
            updated=report.updated,
            unchanged=report.unchanged,
            skipped=report.skipped,
            total_rows=report.total_rows,
        )

    plan_report = SeedPlanReport(plan_name=plan_name, model_reports=tuple(reports))
    logger.info(
        "db.seed_plan.complete",
        plan=plan_name,
        inserted=plan_report.inserted,
        updated=plan_report.updated,
        unchanged=plan_report.unchanged,
        skipped=plan_report.skipped,
        total_rows=plan_report.total_rows,
    )
    return plan_report


def _seed_values_equal(existing: Any, incoming: Any) -> bool:
    if existing == incoming:
        return True

    if isinstance(existing, Decimal) and _is_seed_numeric(incoming):
        return existing == _coerce_decimal(incoming)

    if isinstance(incoming, Decimal) and _is_seed_numeric(existing):
        return incoming == _coerce_decimal(existing)

    return False


def _is_seed_numeric(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _coerce_decimal(value: int | float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AssertionError(f"Seed numeric value {value!r} cannot be normalized for comparison.") from exc
