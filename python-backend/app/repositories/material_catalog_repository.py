from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MaterialCatalog, Supplier, SupplierMaterialPrice


class MaterialCatalogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_material_catalog(self, *, organization_id: str = "org_1", active_only: bool = True, search: str | None = None) -> list[MaterialCatalog]:
        query = select(MaterialCatalog).where(MaterialCatalog.organization_id == organization_id)
        if active_only:
            query = query.where(MaterialCatalog.is_active.is_(True))
        if search:
            query = query.where(MaterialCatalog.name.ilike(f"%{search}%"))
        query = query.order_by(MaterialCatalog.name.asc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_material(self, material_id: str) -> MaterialCatalog | None:
        return await self.session.get(MaterialCatalog, material_id)

    async def list_supplier_prices(self, material_id: str) -> list[tuple[SupplierMaterialPrice, Supplier]]:
        result = await self.session.execute(
            select(SupplierMaterialPrice, Supplier)
            .join(Supplier, Supplier.id == SupplierMaterialPrice.supplier_id)
            .where(SupplierMaterialPrice.material_catalog_id == material_id)
            .order_by(SupplierMaterialPrice.unit_price.asc(), Supplier.name.asc())
        )
        return list(result.all())

    async def get_supplier_name(self, supplier_id: str | None) -> str | None:
        if not supplier_id:
            return None
        supplier = await self.session.get(Supplier, supplier_id)
        return supplier.name if supplier else None

    async def update_material(self, material: MaterialCatalog, *, default_unit_price: float, default_supplier_id: str | None, notes: str | None) -> MaterialCatalog:
        material.default_unit_price = default_unit_price
        material.default_supplier_id = default_supplier_id
        material.notes = notes
        await self.session.commit()
        await self.session.refresh(material)
        return material
