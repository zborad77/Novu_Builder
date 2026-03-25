from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MaterialCatalog, PricingProfile


class PricebookRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_pricebooks(self, organization_id: str) -> list[PricingProfile]:
        result = await self.session.execute(
            select(PricingProfile)
            .where(PricingProfile.organization_id == organization_id)
            .order_by(PricingProfile.is_default.desc(), PricingProfile.name.asc())
        )
        return list(result.scalars().all())

    async def create_pricebook(self, payload: dict, organization_id: str) -> PricingProfile:
        pricebook = PricingProfile(
            id=f"pb_{uuid4().hex[:8]}",
            organization_id=organization_id,
            name=payload["name"],
            hourly_rate=payload["hourlyRate"],
            daily_rate=payload["dailyRate"],
            labor_hours_per_sqm=payload["laborHoursPerSqm"],
            margin_economy_pct=12,
            margin_standard_pct=18,
            margin_premium_pct=28,
            vat_pct=payload["vatPct"],
            currency=payload["currency"],
            is_default=payload["isDefault"],
        )
        if pricebook.is_default:
            existing = await self.list_pricebooks(organization_id)
            for item in existing:
                item.is_default = False
        self.session.add(pricebook)
        await self.session.commit()
        await self.session.refresh(pricebook)
        return pricebook

    async def list_pricebook_items(self, pricebook_id: str, organization_id: str) -> tuple[PricingProfile | None, list[MaterialCatalog]]:
        pricebook = await self.session.get(PricingProfile, pricebook_id)
        if not pricebook or pricebook.organization_id != organization_id:
            return None, []
        result = await self.session.execute(
            select(MaterialCatalog)
            .where(MaterialCatalog.organization_id == organization_id)
            .order_by(MaterialCatalog.category.asc(), MaterialCatalog.name.asc())
        )
        return pricebook, list(result.scalars().all())
