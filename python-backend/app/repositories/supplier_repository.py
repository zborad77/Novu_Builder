from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Supplier


class SupplierRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_suppliers(self, *, organization_id: str = "org_1", active_only: bool = True) -> list[Supplier]:
        query = select(Supplier).where(Supplier.organization_id == organization_id)
        if active_only:
            query = query.where(Supplier.is_active.is_(True))
        query = query.order_by(Supplier.name.asc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_supplier(self, supplier_id: str) -> Supplier | None:
        return await self.session.get(Supplier, supplier_id)

    async def update_supplier(
        self,
        supplier: Supplier,
        *,
        name: str,
        website_url: str | None,
        integration_type: str,
        contact_name: str | None,
        contact_email: str | None,
    ) -> Supplier:
        supplier.name = name
        supplier.website_url = website_url
        supplier.integration_type = integration_type
        supplier.contact_name = contact_name
        supplier.contact_email = contact_email
        await self.session.commit()
        await self.session.refresh(supplier)
        return supplier
