from app.models import AnalysisJob, QuoteItem, QuoteVariant
from app.repositories.quote_variant_repository import QuoteVariantRepository
from app.schemas.quote_variant import AnalysisJobRead, QuoteItemRead, QuoteVariantRead


def round_currency(value: float) -> float:
    return round(value + 1e-9, 2)


def round_measure(value: float) -> float:
    return round(value + 1e-9, 3)


def to_job_read(job: AnalysisJob) -> AnalysisJobRead:
    return AnalysisJobRead(
        id=job.id,
        projectId=job.project_id,
        status=job.status,
        jobType=job.job_type,
        requestedByUserId=job.requested_by_user_id,
        startedAt=job.started_at,
        finishedAt=job.finished_at,
        errorMessage=job.error_message,
        createdAt=job.created_at,
    )


def to_item_read(item: QuoteItem) -> QuoteItemRead:
    return QuoteItemRead(
        id=item.id,
        quoteVariantId=item.quote_variant_id,
        itemType=item.item_type,
        name=item.name,
        description=item.description,
        quantity=item.quantity,
        unit=item.unit,
        unitPrice=item.unit_price,
        totalPrice=item.total_price,
        materialCatalogId=item.material_catalog_id,
        supplierId=item.supplier_id,
        priceSource=item.price_source,
        isManualOverride=item.is_manual_override,
        aiSuggestedUnitPrice=item.ai_suggested_unit_price,
        supplierReferenceUnitPrice=item.supplier_reference_unit_price,
        companyDefaultUnitPrice=item.company_default_unit_price,
        sortOrder=item.sort_order,
        createdAt=item.created_at,
        updatedAt=item.updated_at,
    )


def to_variant_read(variant: QuoteVariant) -> QuoteVariantRead:
    items = sorted(variant.items, key=lambda item: item.sort_order)
    return QuoteVariantRead(
        id=variant.id,
        projectId=variant.project_id,
        analysisResultId=variant.analysis_result_id,
        pricingProfileId=variant.pricing_profile_id,
        variantType=variant.variant_type,
        laborCost=variant.labor_cost,
        materialCost=variant.material_cost,
        otherCost=variant.other_cost,
        marginPct=variant.margin_pct,
        totalExVat=variant.total_ex_vat,
        vatAmount=variant.vat_amount,
        totalIncVat=variant.total_inc_vat,
        createdAt=variant.created_at,
        updatedAt=variant.updated_at,
        items=[to_item_read(item) for item in items],
    )


class QuoteVariantService:
    def __init__(self, repository: QuoteVariantRepository):
        self.repository = repository

    async def get_analysis_job(self, job_id: str) -> AnalysisJobRead | None:
        job = await self.repository.get_analysis_job(job_id)
        return to_job_read(job) if job else None

    async def list_quote_variants(self, project_id: str) -> list[QuoteVariantRead]:
        variants = await self.repository.list_quote_variants(project_id)
        return [to_variant_read(variant) for variant in variants]

    async def recalculate_quote_variants(self, project_id: str) -> list[QuoteVariantRead] | None:
        project = await self.repository.get_project(project_id)
        analysis = await self.repository.get_latest_analysis(project_id)
        pricing_profile = await self.repository.get_default_pricing_profile(project.organization_id)

        if not project or not analysis or not pricing_profile:
            return None

        effective_area_sqm = (
            analysis.manual_area_sqm
            if analysis.final_area_source == "manual" and analysis.manual_area_sqm and analysis.manual_area_sqm > 0
            else analysis.estimated_area_sqm
        )
        if not effective_area_sqm:
            return None

        suggested_materials = self.repository.parse_json_field(analysis.materials_suggestion_json) or []
        material_names = [
            str(item.get("name") or "").strip().lower()
            for item in suggested_materials
            if str(item.get("name") or "").strip()
        ]
        matched_materials = await self.repository.list_materials_by_names(project.organization_id, material_names)

        material_line_base = []
        for material in matched_materials:
            raw_quantity = float(effective_area_sqm) * float(material.norm_per_sqm)
            quantity = round_measure(raw_quantity)
            unit_price = float(material.default_unit_price)
            total_price = round_currency(raw_quantity * unit_price)
            suggested_material = next(
                (item for item in suggested_materials if str(item.get("name") or "").strip().lower() == material.name.strip().lower()),
                None,
            )
            supplier_reference = await self.repository.get_lowest_supplier_price(material.id)
            material_line_base.append(
                {
                    "material_catalog_id": material.id,
                    "supplier_id": material.default_supplier_id or (supplier_reference.supplier_id if supplier_reference else None),
                    "name": material.name,
                    "description": (
                        f"AI navrhla material {material.name} pro opravu o plose {effective_area_sqm} m2."
                        if suggested_material
                        else f"Material z firemniho katalogu pro opravu o plose {effective_area_sqm} m2."
                    ),
                    "quantity": quantity,
                    "unit": material.unit,
                    "unit_price": unit_price,
                    "total_price": total_price,
                    "ai_suggested_unit_price": (
                        round_currency(total_price / suggested_material["quantity"])
                        if suggested_material and suggested_material.get("quantity")
                        else None
                    ),
                    "supplier_reference_unit_price": supplier_reference.unit_price if supplier_reference else None,
                    "company_default_unit_price": unit_price,
                }
            )

        base_labor = float(effective_area_sqm) * float(pricing_profile.labor_hours_per_sqm) * float(pricing_profile.hourly_rate)
        base_material = round_currency(sum(item["total_price"] for item in material_line_base))
        base_other = 3500.0

        variants_config = [
            {"type": "economy", "labor_factor": 1.0, "material_factor": 1.0, "other_factor": 1.0, "margin": pricing_profile.margin_economy_pct},
            {"type": "standard", "labor_factor": 1.12, "material_factor": 1.28, "other_factor": 1.08, "margin": pricing_profile.margin_standard_pct},
            {"type": "premium", "labor_factor": 1.22, "material_factor": 1.6, "other_factor": 1.18, "margin": pricing_profile.margin_premium_pct},
        ]

        variants_payload = []
        for index, config in enumerate(variants_config, start=1):
            labor_cost = round_currency(base_labor * float(config["labor_factor"]))
            material_cost = round_currency(base_material * float(config["material_factor"]))
            other_cost = round_currency(base_other * float(config["other_factor"]))
            subtotal = labor_cost + material_cost + other_cost
            total_ex_vat = round_currency(subtotal * (1 + float(config["margin"]) / 100))
            vat_amount = round_currency(total_ex_vat * (float(pricing_profile.vat_pct) / 100))
            total_inc_vat = round_currency(total_ex_vat + vat_amount)
            variant_id = self.repository.build_id("qv")

            items = [
                {
                    "id": self.repository.build_id("qi"),
                    "item_type": "labor",
                    "name": "Prace",
                    "description": f"Prace podle plochy opravy {effective_area_sqm} m2 a firemni normy.",
                    "quantity": round_currency(float(effective_area_sqm) * float(pricing_profile.labor_hours_per_sqm) * float(config["labor_factor"])),
                    "unit": "hod",
                    "unit_price": float(pricing_profile.hourly_rate),
                    "total_price": labor_cost,
                    "material_catalog_id": None,
                    "supplier_id": None,
                    "price_source": "company_catalog",
                    "is_manual_override": False,
                    "ai_suggested_unit_price": None,
                    "supplier_reference_unit_price": None,
                    "company_default_unit_price": float(pricing_profile.hourly_rate),
                    "sort_order": 1,
                },
                {
                    "id": self.repository.build_id("qi"),
                    "item_type": "other",
                    "name": "Vedlejsi naklady",
                    "description": "Doprava, priprava, drobny material",
                    "quantity": 1.0,
                    "unit": "ks",
                    "unit_price": other_cost,
                    "total_price": other_cost,
                    "material_catalog_id": None,
                    "supplier_id": None,
                    "price_source": "company_catalog",
                    "is_manual_override": False,
                    "ai_suggested_unit_price": None,
                    "supplier_reference_unit_price": None,
                    "company_default_unit_price": other_cost,
                    "sort_order": 999,
                },
            ]

            for item_index, item in enumerate(material_line_base, start=2):
                items.insert(
                    item_index - 1,
                    {
                        "id": self.repository.build_id("qi"),
                        "item_type": "material",
                        "name": item["name"],
                        "description": item["description"],
                        "quantity": round_measure(item["quantity"] * float(config["material_factor"])),
                        "unit": item["unit"],
                        "unit_price": item["unit_price"],
                        "total_price": round_currency(item["total_price"] * float(config["material_factor"])),
                        "material_catalog_id": item["material_catalog_id"],
                        "supplier_id": item["supplier_id"],
                        "price_source": "company_catalog",
                        "is_manual_override": False,
                        "ai_suggested_unit_price": item["ai_suggested_unit_price"],
                        "supplier_reference_unit_price": item["supplier_reference_unit_price"],
                        "company_default_unit_price": item["company_default_unit_price"],
                        "sort_order": item_index,
                    },
                )

            variants_payload.append(
                {
                    "id": variant_id,
                    "variant_type": config["type"],
                    "labor_cost": labor_cost,
                    "material_cost": material_cost,
                    "other_cost": other_cost,
                    "margin_pct": float(config["margin"]),
                    "total_ex_vat": total_ex_vat,
                    "vat_amount": vat_amount,
                    "total_inc_vat": total_inc_vat,
                    "items": items,
                }
            )

        created = await self.repository.replace_project_variants(
            project=project,
            analysis=analysis,
            pricing_profile=pricing_profile,
            variants_payload=variants_payload,
        )
        return [to_variant_read(variant) for variant in created]

    async def update_quote_variant(self, variant_id: str, payload: dict) -> QuoteVariantRead | None:
        variant = await self.repository.get_quote_variant(variant_id)
        if not variant:
            return None

        labor_cost = float(payload.get("laborCost", variant.labor_cost))
        material_cost = float(payload.get("materialCost", variant.material_cost))
        other_cost = float(payload.get("otherCost", variant.other_cost))
        margin_pct = float(payload.get("marginPct", variant.margin_pct))
        total_ex_vat = round_currency((labor_cost + material_cost + other_cost) * (1 + margin_pct / 100))
        vat_amount = round_currency(total_ex_vat * 0.21)
        total_inc_vat = round_currency(total_ex_vat + vat_amount)

        updated = await self.repository.update_quote_variant(
            variant,
            {
                "labor_cost": labor_cost,
                "material_cost": material_cost,
                "other_cost": other_cost,
                "margin_pct": margin_pct,
                "total_ex_vat": total_ex_vat,
                "vat_amount": vat_amount,
                "total_inc_vat": total_inc_vat,
            },
        )
        return to_variant_read(updated)
