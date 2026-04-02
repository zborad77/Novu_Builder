from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter
from typing import Any

from redis.asyncio import Redis

from app.core.cache import VersionTaggedLocalCache, get_cache_tag
from app.core.metrics import (
    observe_cache_operation,
    observe_work_catalog_resolution,
    record_work_catalog_validation_failure,
)
from app.core.tenant_timing import (
    TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
    enforce_timing_floor,
)
from app.models import PricingProfile
from app.models.work_catalog import CatalogPricingProfile, ProjectWorkItem, ProjectWorkItemValue, WorkType
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.services.tenant_work_type_resolution_service import TenantWorkTypeResolutionService
from app.work_catalog.cache import LOCAL_RESOLUTION_TTL_SECONDS, pricing_resolution_cache_scope
from app.work_catalog.domain import CatalogValidationError, normalize_machine_code


def _as_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


class PricingProfileResolutionError(LookupError):
    """Raised when no valid effective pricing configuration can be resolved."""


@dataclass(frozen=True)
class ResolvedPricingConfiguration:
    organization_id: str
    work_type: WorkType
    catalog_pricing_profile: CatalogPricingProfile
    tenant_pricing_profile: PricingProfile | None

    @property
    def work_type_code(self) -> str:
        return self.work_type.code

    @property
    def profile_code(self) -> str:
        return self.catalog_pricing_profile.code

    @property
    def profile_version(self) -> int:
        return int(self.catalog_pricing_profile.profile_version)


class PricingProfileService:
    def __init__(self, repository: WorkCatalogRepository, redis: Redis | None = None):
        self.repository = repository
        self.redis = redis
        self.resolution_service = TenantWorkTypeResolutionService(repository, redis=redis)
        self._resolved_by_work_type = VersionTaggedLocalCache(
            namespace="work_catalog_local",
            ttl_seconds=LOCAL_RESOLUTION_TTL_SECONDS,
        )
        self._resolved_snapshots = VersionTaggedLocalCache(
            namespace="work_catalog_local",
            ttl_seconds=LOCAL_RESOLUTION_TTL_SECONDS,
        )

    async def _cache_tag_for_org(self, organization_id: str) -> str:
        return await get_cache_tag(self.redis, pricing_resolution_cache_scope(organization_id))

    async def resolve_for_work_type(
        self,
        *,
        organization_id: str,
        work_type_code: str,
    ) -> ResolvedPricingConfiguration:
        started_at = perf_counter()
        normalized_code = normalize_machine_code(work_type_code, field_name="workTypeCode")
        cache_key = (organization_id, normalized_code)
        cache_tag = await self._cache_tag_for_org(organization_id)
        cached = self._resolved_by_work_type.get(cache_key, tag=cache_tag)
        outcome = "success"
        if cached is not None:
            observe_cache_operation(
                namespace="work_catalog_local",
                operation="pricing_profile.resolve_for_work_type",
                outcome="hit",
            )
            outcome = "cache_hit"
            try:
                return cached
            finally:
                observe_work_catalog_resolution(
                    path="pricing_profile.resolve_for_work_type",
                    outcome=outcome,
                    duration_seconds=perf_counter() - started_at,
                )
                await enforce_timing_floor(
                    started_at,
                    minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
                )
        observe_cache_operation(
            namespace="work_catalog_local",
            operation="pricing_profile.resolve_for_work_type",
            outcome="miss",
        )
        try:
            resolved = await self.resolution_service.resolve_for_work_type(
                organization_id=organization_id,
                work_type_code=normalized_code,
            )
        except CatalogValidationError as exc:
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="pricing_profile.resolve_for_work_type",
                reason="invalid_effective_configuration",
            )
            raise PricingProfileResolutionError(str(exc)) from exc
        except Exception:
            outcome = "error"
            raise
        finally:
            observe_work_catalog_resolution(
                path="pricing_profile.resolve_for_work_type",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
            await enforce_timing_floor(
                started_at,
                minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
            )
        work_type = resolved.work_type
        profile = resolved.catalog_pricing_profile
        if profile is None:
            raise PricingProfileResolutionError(
                f"Work type '{normalized_code}' has no active pricing profile."
            )

        tenant_pricing_profile = None
        tenant_pricing_profile_id = resolved.tenant_pricing_profile_id
        if tenant_pricing_profile_id:
            tenant_pricing_profile = await self.repository.get_tenant_pricing_profile(
                tenant_pricing_profile_id,
                organization_id=organization_id,
            )
        if tenant_pricing_profile is None:
            tenant_pricing_profile = await self.repository.get_default_pricing_profile(organization_id)

        configured = ResolvedPricingConfiguration(
            organization_id=organization_id,
            work_type=work_type,
            catalog_pricing_profile=profile,
            tenant_pricing_profile=tenant_pricing_profile,
        )
        self._resolved_by_work_type.set(cache_key, configured, tag=cache_tag)
        return configured

    async def resolve_for_snapshot(
        self,
        *,
        organization_id: str,
        work_type_code: str,
        catalog_pricing_profile_id: str,
        tenant_pricing_profile_id: str | None,
    ) -> ResolvedPricingConfiguration:
        started_at = perf_counter()
        normalized_code = normalize_machine_code(work_type_code, field_name="workTypeCode")
        cache_key = (
            organization_id,
            normalized_code,
            catalog_pricing_profile_id,
            tenant_pricing_profile_id,
        )
        cache_tag = await self._cache_tag_for_org(organization_id)
        cached = self._resolved_snapshots.get(cache_key, tag=cache_tag)
        outcome = "success"
        if cached is not None:
            observe_cache_operation(
                namespace="work_catalog_local",
                operation="pricing_profile.resolve_for_snapshot",
                outcome="hit",
            )
            outcome = "cache_hit"
            try:
                return cached
            finally:
                observe_work_catalog_resolution(
                    path="pricing_profile.resolve_for_snapshot",
                    outcome=outcome,
                    duration_seconds=perf_counter() - started_at,
                )
                await enforce_timing_floor(
                    started_at,
                    minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
                )
        observe_cache_operation(
            namespace="work_catalog_local",
            operation="pricing_profile.resolve_for_snapshot",
            outcome="miss",
        )
        work_type = await self.repository.get_work_type_by_code(normalized_code)
        if work_type is None:
            outcome = "not_found"
            try:
                raise PricingProfileResolutionError(f"Work type '{normalized_code}' was not found.")
            finally:
                observe_work_catalog_resolution(
                    path="pricing_profile.resolve_for_snapshot",
                    outcome=outcome,
                    duration_seconds=perf_counter() - started_at,
                )
                await enforce_timing_floor(
                    started_at,
                    minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
                )
        profile = await self.repository.get_catalog_pricing_profile_by_id(catalog_pricing_profile_id)
        if profile is None:
            outcome = "not_found"
            try:
                raise PricingProfileResolutionError(
                    f"Catalog pricing profile '{catalog_pricing_profile_id}' was not found."
                )
            finally:
                observe_work_catalog_resolution(
                    path="pricing_profile.resolve_for_snapshot",
                    outcome=outcome,
                    duration_seconds=perf_counter() - started_at,
                )
                await enforce_timing_floor(
                    started_at,
                    minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
                )
        if not profile.code.startswith(f"{work_type.code}-"):
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="pricing_profile.resolve_for_snapshot",
                reason="profile_work_type_mismatch",
            )
            observe_work_catalog_resolution(
                path="pricing_profile.resolve_for_snapshot",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
            await enforce_timing_floor(
                started_at,
                minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
            )
            raise PricingProfileResolutionError(
                f"Catalog pricing profile '{profile.code}' is inconsistent with work type '{work_type.code}'."
            )
        if not profile.is_active or profile.status != "active":
            outcome = "validation_error"
            record_work_catalog_validation_failure(
                operation="pricing_profile.resolve_for_snapshot",
                reason="inactive_profile",
            )
            observe_work_catalog_resolution(
                path="pricing_profile.resolve_for_snapshot",
                outcome=outcome,
                duration_seconds=perf_counter() - started_at,
            )
            await enforce_timing_floor(
                started_at,
                minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
            )
            raise PricingProfileResolutionError(
                f"Catalog pricing profile '{profile.code}' is not active."
            )

        tenant_pricing_profile = None
        if tenant_pricing_profile_id:
            tenant_pricing_profile = await self.repository.get_tenant_pricing_profile(
                tenant_pricing_profile_id,
                organization_id=organization_id,
            )
        if tenant_pricing_profile is None:
            tenant_pricing_profile = await self.repository.get_default_pricing_profile(organization_id)

        configured = ResolvedPricingConfiguration(
            organization_id=organization_id,
            work_type=work_type,
            catalog_pricing_profile=profile,
            tenant_pricing_profile=tenant_pricing_profile,
        )
        self._resolved_snapshots.set(cache_key, configured, tag=cache_tag)
        observe_work_catalog_resolution(
            path="pricing_profile.resolve_for_snapshot",
            outcome=outcome,
            duration_seconds=perf_counter() - started_at,
        )
        await enforce_timing_floor(
            started_at,
            minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
        )
        return configured

    @staticmethod
    def _value_from_runtime_row(row: ProjectWorkItemValue) -> Any:
        if row.resolved_data_type == "number":
            return _as_float(row.value_number)
        if row.resolved_data_type == "boolean":
            return row.value_boolean
        if row.resolved_data_type == "option":
            return row.value_option_code
        return row.value_text

    def _resolve_source_value(
        self,
        *,
        source_type: str,
        source_key: str | None,
        work_item: ProjectWorkItem,
        values_by_code: dict[str, Any],
    ) -> Any:
        if source_type == "constant":
            return 1
        if source_type == "work_item_field":
            if source_key == "measured_quantity":
                return _as_float(work_item.measured_quantity)
            if source_key == "measured_unit":
                return work_item.measured_unit
            if source_key == "item_sequence":
                return work_item.item_sequence
            raise CatalogValidationError(f"Unsupported work item field source '{source_key}'.")
        if not source_key:
            raise CatalogValidationError("Pricing rule sourceKey is required.")
        return values_by_code.get(source_key)

    @staticmethod
    def _comparison_value(rule) -> Any:
        if rule.condition_text_value is not None:
            return rule.condition_text_value
        if rule.condition_number_value is not None:
            return _as_float(rule.condition_number_value)
        if rule.condition_boolean_value is not None:
            return rule.condition_boolean_value
        if rule.condition_option_code is not None:
            return rule.condition_option_code
        return None

    def _condition_matches(self, *, rule, value: Any) -> bool:
        if value is None:
            return False
        if rule.condition_operator == "true":
            return bool(value) is True
        expected = self._comparison_value(rule)
        if rule.condition_operator == "eq":
            return value == expected
        if not isinstance(value, (int, float)) or expected is None:
            return False
        if rule.condition_operator == "gte":
            return float(value) >= float(expected)
        if rule.condition_operator == "lte":
            return float(value) <= float(expected)
        return False

    def _unit_price_for_rule(
        self,
        *,
        rule,
        tenant_pricing_profile: PricingProfile | None,
    ) -> float:
        if rule.rate_source == "tenant_hourly_rate":
            if tenant_pricing_profile is None:
                raise CatalogValidationError("Tenant pricing profile is required for hourly-rate pricing.")
            return float(tenant_pricing_profile.hourly_rate)
        if rule.rate_source == "tenant_daily_rate":
            if tenant_pricing_profile is None:
                raise CatalogValidationError("Tenant pricing profile is required for daily-rate pricing.")
            return float(tenant_pricing_profile.daily_rate)
        if rule.rate_value is None:
            raise CatalogValidationError(f"Catalog pricing rule '{rule.code}' is missing rateValue.")
        return float(rule.rate_value)

    def calculate_project_work_item(
        self,
        *,
        work_item: ProjectWorkItem,
        resolved: ResolvedPricingConfiguration,
    ) -> dict[str, Any]:
        profile = resolved.catalog_pricing_profile
        values_by_code = {
            row.resolved_parameter_code: self._value_from_runtime_row(row)
            for row in (work_item.values or [])
        }

        input_snapshot: dict[str, Any] = {}
        for input_rule in sorted(profile.required_inputs or [], key=lambda row: (row.sort_order, row.code)):
            value = self._resolve_source_value(
                source_type=input_rule.source_type,
                source_key=input_rule.source_key,
                work_item=work_item,
                values_by_code=values_by_code,
            )
            if input_rule.is_required and value in (None, "", []):
                raise CatalogValidationError(
                    f"Missing required pricing input '{input_rule.code}' for work type '{work_item.resolved_work_type_code}'."
                )
            input_snapshot[input_rule.code] = value

        lines: list[dict[str, Any]] = []
        for rule in sorted(profile.base_rules or [], key=lambda row: (row.sort_order, row.code)):
            source_value = self._resolve_source_value(
                source_type=rule.quantity_source_type,
                source_key=rule.quantity_source_key,
                work_item=work_item,
                values_by_code=values_by_code,
            )
            if source_value is None:
                continue
            if rule.quantity_source_type == "constant":
                quantity = float(rule.quantity_multiplier)
            else:
                quantity = float(source_value) * float(rule.quantity_multiplier)
            unit_price = self._unit_price_for_rule(rule=rule, tenant_pricing_profile=resolved.tenant_pricing_profile)
            total_price = round(quantity * unit_price + 1e-9, 2)
            lines.append(
                {
                    "item_type": rule.line_type,
                    "name": rule.label,
                    "description": rule.description,
                    "quantity": round(quantity + 1e-9, 3),
                    "unit": rule.unit,
                    "unit_price": round(unit_price + 1e-9, 2),
                    "total_price": total_price,
                    "catalog_pricing_rule_code": rule.code,
                    "project_work_item_id": work_item.id,
                    "work_type_code": work_item.resolved_work_type_code,
                    "catalog_pricing_profile_id": profile.id,
                    "resolved_catalog_pricing_profile_code": profile.code,
                    "resolved_catalog_pricing_profile_version": profile.profile_version,
                    "price_source": "catalog_formula",
                    "sort_order": rule.sort_order,
                }
            )

        for rule in sorted(profile.adjustment_rules or [], key=lambda row: (row.sort_order, row.code)):
            value = self._resolve_source_value(
                source_type=rule.condition_source_type,
                source_key=rule.condition_source_key,
                work_item=work_item,
                values_by_code=values_by_code,
            )
            if not self._condition_matches(rule=rule, value=value):
                continue

            if rule.target_scope == "base_rule":
                target_total = sum(
                    line["total_price"]
                    for line in lines
                    if line["catalog_pricing_rule_code"] == rule.target_base_rule_code
                )
                target_line_type = rule.target_line_type or next(
                    (
                        line["item_type"]
                        for line in lines
                        if line["catalog_pricing_rule_code"] == rule.target_base_rule_code
                    ),
                    "other",
                )
            else:
                scoped_lines = lines
                if rule.target_line_type:
                    scoped_lines = [line for line in lines if line["item_type"] == rule.target_line_type]
                target_total = sum(line["total_price"] for line in scoped_lines)
                target_line_type = rule.target_line_type or "other"

            if rule.operation == "multiply":
                if target_total <= 0:
                    continue
                adjustment_amount = round(target_total * (float(rule.adjustment_value) - 1) + 1e-9, 2)
            else:
                adjustment_amount = round(float(rule.adjustment_value) + 1e-9, 2)
            if adjustment_amount == 0:
                continue
            lines.append(
                {
                    "item_type": target_line_type,
                    "name": rule.label,
                    "description": rule.description,
                    "quantity": 1.0,
                    "unit": "job",
                    "unit_price": adjustment_amount,
                    "total_price": adjustment_amount,
                    "catalog_pricing_rule_code": rule.code,
                    "project_work_item_id": work_item.id,
                    "work_type_code": work_item.resolved_work_type_code,
                    "catalog_pricing_profile_id": profile.id,
                    "resolved_catalog_pricing_profile_code": profile.code,
                    "resolved_catalog_pricing_profile_version": profile.profile_version,
                    "price_source": "catalog_formula_adjustment",
                    "sort_order": rule.sort_order + 500,
                }
            )

        subtotal_labor = round(sum(line["total_price"] for line in lines if line["item_type"] == "labor") + 1e-9, 2)
        subtotal_material = round(sum(line["total_price"] for line in lines if line["item_type"] == "material") + 1e-9, 2)
        subtotal_other = round(sum(line["total_price"] for line in lines if line["item_type"] == "other") + 1e-9, 2)
        total_before_floor = round(subtotal_labor + subtotal_material + subtotal_other + 1e-9, 2)

        minimum_job_adjustment = 0.0
        if profile.min_job_price is not None and total_before_floor < float(profile.min_job_price):
            minimum_job_adjustment = round(float(profile.min_job_price) - total_before_floor + 1e-9, 2)
            subtotal_other = round(subtotal_other + minimum_job_adjustment + 1e-9, 2)
            lines.append(
                {
                    "item_type": "other",
                    "name": "Minimum Job Charge Adjustment",
                    "description": "Catalog pricing profile minimum charge floor.",
                    "quantity": 1.0,
                    "unit": "job",
                    "unit_price": minimum_job_adjustment,
                    "total_price": minimum_job_adjustment,
                    "catalog_pricing_rule_code": "minimum-job-charge",
                    "project_work_item_id": work_item.id,
                    "work_type_code": work_item.resolved_work_type_code,
                    "catalog_pricing_profile_id": profile.id,
                    "resolved_catalog_pricing_profile_code": profile.code,
                    "resolved_catalog_pricing_profile_version": profile.profile_version,
                    "price_source": "catalog_minimum_charge",
                    "sort_order": 9_990,
                }
            )

        total = round(subtotal_labor + subtotal_material + subtotal_other + 1e-9, 2)
        lines.sort(key=lambda row: (row["sort_order"], row["name"]))
        return {
            "project_work_item_id": work_item.id,
            "work_type_code": work_item.resolved_work_type_code,
            "catalog_pricing_profile_id": profile.id,
            "catalog_pricing_profile_code": profile.code,
            "catalog_pricing_profile_version": profile.profile_version,
            "tenant_pricing_profile_id": resolved.tenant_pricing_profile.id if resolved.tenant_pricing_profile else None,
            "currency": profile.currency,
            "input_snapshot": input_snapshot,
            "line_items": lines,
            "subtotal_labor": subtotal_labor,
            "subtotal_material": subtotal_material,
            "subtotal_other": subtotal_other,
            "minimum_job_adjustment": minimum_job_adjustment,
            "total": total,
        }

    def build_quote_variants(
        self,
        *,
        work_item_results: list[dict[str, Any]],
        pricing_profile: PricingProfile,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        aggregated_items = [
            item
            for result in work_item_results
            for item in result["line_items"]
        ]
        labor_cost = round(sum(item["total_price"] for item in aggregated_items if item["item_type"] == "labor") + 1e-9, 2)
        material_cost = round(sum(item["total_price"] for item in aggregated_items if item["item_type"] == "material") + 1e-9, 2)
        other_cost = round(sum(item["total_price"] for item in aggregated_items if item["item_type"] == "other") + 1e-9, 2)
        subtotal = round(labor_cost + material_cost + other_cost + 1e-9, 2)

        variants_config = [
            {"type": "economy", "margin": float(pricing_profile.margin_economy_pct)},
            {"type": "standard", "margin": float(pricing_profile.margin_standard_pct)},
            {"type": "premium", "margin": float(pricing_profile.margin_premium_pct)},
        ]
        variants_payload: list[dict[str, Any]] = []
        summary = {
            "currency": pricing_profile.currency,
            "workItemCount": len(work_item_results),
            "catalogProfiles": sorted(
                {
                    result["catalog_pricing_profile_code"]
                    for result in work_item_results
                }
            ),
            "baseSubtotal": subtotal,
        }
        for config in variants_config:
            total_ex_vat = round(subtotal * (1 + float(config["margin"]) / 100) + 1e-9, 2)
            vat_amount = round(total_ex_vat * (float(pricing_profile.vat_pct) / 100) + 1e-9, 2)
            total_inc_vat = round(total_ex_vat + vat_amount + 1e-9, 2)
            variants_payload.append(
                {
                    "variant_type": config["type"],
                    "labor_cost": labor_cost,
                    "material_cost": material_cost,
                    "other_cost": other_cost,
                    "margin_pct": float(config["margin"]),
                    "total_ex_vat": total_ex_vat,
                    "vat_amount": vat_amount,
                    "total_inc_vat": total_inc_vat,
                    "currency": pricing_profile.currency,
                    "vat_pct": float(pricing_profile.vat_pct),
                    "pricing_summary_json": json.dumps(summary, sort_keys=True),
                    "items": aggregated_items,
                }
            )
        return variants_payload, summary
