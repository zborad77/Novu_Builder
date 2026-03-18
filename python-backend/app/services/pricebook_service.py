from app.models import MaterialCatalog, PricingProfile
from app.repositories.pricebook_repository import PricebookRepository
from app.schemas.pricebook import PricebookCreate, PricebookItemRead, PricebookRead


def to_pricebook_read(pricebook: PricingProfile) -> PricebookRead:
    return PricebookRead(
        id=pricebook.id,
        name=pricebook.name,
        organizationId=pricebook.organization_id,
        hourlyRate=pricebook.hourly_rate,
        dailyRate=pricebook.daily_rate,
        laborHoursPerSqm=pricebook.labor_hours_per_sqm,
        vatPct=pricebook.vat_pct,
        currency=pricebook.currency,
        isDefault=pricebook.is_default,
        createdAt=pricebook.created_at,
        updatedAt=pricebook.updated_at,
    )


def to_pricebook_item_read(item: MaterialCatalog) -> PricebookItemRead:
    return PricebookItemRead(
        id=item.id,
        materialCatalogId=item.id,
        name=item.name,
        category=item.category,
        unit=item.unit,
        normPerSqm=item.norm_per_sqm,
        defaultUnitPrice=item.default_unit_price,
        defaultSupplierId=item.default_supplier_id,
        notes=item.notes,
        isActive=item.is_active,
    )


class PricebookService:
    def __init__(self, repository: PricebookRepository):
        self.repository = repository

    async def list_pricebooks(self) -> list[PricebookRead]:
        pricebooks = await self.repository.list_pricebooks()
        return [to_pricebook_read(item) for item in pricebooks]

    async def create_pricebook(self, payload: PricebookCreate) -> PricebookRead:
        pricebook = await self.repository.create_pricebook(payload.model_dump())
        return to_pricebook_read(pricebook)

    async def list_pricebook_items(self, pricebook_id: str) -> list[PricebookItemRead] | None:
        pricebook, items = await self.repository.list_pricebook_items(pricebook_id)
        if not pricebook:
            return None
        return [to_pricebook_item_read(item) for item in items]
