import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AnalysisJob, AnalysisResult, MaterialCatalog, PricingProfile, Project, QuoteItem, QuoteVariant, SupplierMaterialPrice


class QuoteVariantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_analysis_job(self, job_id: str) -> AnalysisJob | None:
        return await self.session.get(AnalysisJob, job_id)

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.get(Project, project_id)

    async def get_latest_analysis(self, project_id: str) -> AnalysisResult | None:
        result = await self.session.execute(
            select(AnalysisResult)
            .where(AnalysisResult.project_id == project_id)
            .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_default_pricing_profile(self) -> PricingProfile | None:
        result = await self.session.execute(
            select(PricingProfile).where(PricingProfile.is_default.is_(True)).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_quote_variants(self, project_id: str) -> list[QuoteVariant]:
        result = await self.session.execute(
            select(QuoteVariant)
            .options(selectinload(QuoteVariant.items))
            .where(QuoteVariant.project_id == project_id)
            .order_by(QuoteVariant.created_at.asc(), QuoteVariant.id.asc())
        )
        return list(result.scalars().all())

    async def get_quote_variant(self, variant_id: str) -> QuoteVariant | None:
        result = await self.session.execute(
            select(QuoteVariant)
            .options(selectinload(QuoteVariant.items))
            .where(QuoteVariant.id == variant_id)
        )
        return result.scalar_one_or_none()

    async def list_materials_by_names(self, organization_id: str, names: list[str]) -> list[MaterialCatalog]:
        if not names:
            return []
        lowered_names = [name.lower() for name in names]
        result = await self.session.execute(
            select(MaterialCatalog)
            .where(
                MaterialCatalog.organization_id == organization_id,
                MaterialCatalog.is_active.is_(True),
                func.lower(MaterialCatalog.name).in_(lowered_names),
            )
            .order_by(MaterialCatalog.name.asc())
        )
        return list(result.scalars().all())

    async def get_lowest_supplier_price(self, material_catalog_id: str) -> SupplierMaterialPrice | None:
        result = await self.session.execute(
            select(SupplierMaterialPrice)
            .where(SupplierMaterialPrice.material_catalog_id == material_catalog_id)
            .order_by(SupplierMaterialPrice.unit_price.asc(), SupplierMaterialPrice.supplier_id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def replace_project_variants(
        self,
        *,
        project: Project,
        analysis: AnalysisResult,
        pricing_profile: PricingProfile,
        variants_payload: list[dict],
    ) -> list[QuoteVariant]:
        existing_variants = await self.list_quote_variants(project.id)
        existing_variant_ids = [variant.id for variant in existing_variants]
        if existing_variant_ids:
            await self.session.execute(delete(QuoteItem).where(QuoteItem.quote_variant_id.in_(existing_variant_ids)))
            await self.session.execute(delete(QuoteVariant).where(QuoteVariant.id.in_(existing_variant_ids)))
            await self.session.flush()

        timestamp = datetime.now(UTC)
        created_variant_ids: list[str] = []

        for variant_payload in variants_payload:
            variant = QuoteVariant(
                id=variant_payload["id"],
                project_id=project.id,
                analysis_result_id=analysis.id,
                pricing_profile_id=pricing_profile.id,
                variant_type=variant_payload["variant_type"],
                labor_cost=variant_payload["labor_cost"],
                material_cost=variant_payload["material_cost"],
                other_cost=variant_payload["other_cost"],
                margin_pct=variant_payload["margin_pct"],
                total_ex_vat=variant_payload["total_ex_vat"],
                vat_amount=variant_payload["vat_amount"],
                total_inc_vat=variant_payload["total_inc_vat"],
                created_at=timestamp,
                updated_at=timestamp,
            )
            self.session.add(variant)
            created_variant_ids.append(variant.id)

            for item_payload in variant_payload["items"]:
                self.session.add(
                    QuoteItem(
                        id=item_payload["id"],
                        quote_variant_id=variant.id,
                        item_type=item_payload["item_type"],
                        name=item_payload["name"],
                        description=item_payload.get("description"),
                        quantity=item_payload["quantity"],
                        unit=item_payload["unit"],
                        unit_price=item_payload["unit_price"],
                        total_price=item_payload["total_price"],
                        material_catalog_id=item_payload.get("material_catalog_id"),
                        supplier_id=item_payload.get("supplier_id"),
                        price_source=item_payload["price_source"],
                        is_manual_override=item_payload["is_manual_override"],
                        ai_suggested_unit_price=item_payload.get("ai_suggested_unit_price"),
                        supplier_reference_unit_price=item_payload.get("supplier_reference_unit_price"),
                        company_default_unit_price=item_payload.get("company_default_unit_price"),
                        sort_order=item_payload["sort_order"],
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )

        project.status = "quoted"
        project.updated_at = timestamp
        await self.session.commit()

        result = await self.session.execute(
            select(QuoteVariant)
            .options(selectinload(QuoteVariant.items))
            .where(QuoteVariant.id.in_(created_variant_ids))
            .order_by(QuoteVariant.created_at.asc(), QuoteVariant.id.asc())
        )
        return list(result.scalars().all())

    async def update_quote_variant(self, variant: QuoteVariant, changes: dict) -> QuoteVariant:
        for key, value in changes.items():
            setattr(variant, key, value)
        variant.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(variant)
        result = await self.session.execute(
            select(QuoteVariant)
            .options(selectinload(QuoteVariant.items))
            .where(QuoteVariant.id == variant.id)
        )
        return result.scalar_one()

    @staticmethod
    def parse_json_field(value: str | None):
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def build_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:10]}"
