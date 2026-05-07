from app.repositories.material_catalog_repository import MaterialCatalogRepository
from app.schemas.material_catalog import MaterialCatalogRead, SupplierPriceRead


class MaterialCatalogService:
    def __init__(self, repository: MaterialCatalogRepository):
        self.repository = repository

    async def list_material_catalog(self, *, organization_id: str, search: str | None = None, include_inactive: bool = False) -> list[MaterialCatalogRead]:
        items = await self.repository.list_material_catalog(organization_id=organization_id, search=search, active_only=not include_inactive)
        results = []
        for item in items:
            results.append(
                MaterialCatalogRead(
                    id=item.id,
                    organization_id=item.organization_id,
                    name=item.name,
                    category=item.category,
                    unit=item.unit,
                    norm_per_sqm=float(item.norm_per_sqm),
                    default_unit_price=float(item.default_unit_price),
                    default_supplier_id=item.default_supplier_id,
                    default_supplier_name=item.default_supplier.name if item.default_supplier else None,
                    is_active=item.is_active,
                    notes=item.notes,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )
        return results

    async def list_supplier_prices(self, material_id: str, organization_id: str) -> list[SupplierPriceRead] | None:
        material = await self.repository.get_material_in_org(material_id, organization_id)
        if not material:
            return None
        rows = await self.repository.list_supplier_prices(material_id)
        return [
            SupplierPriceRead(
                id=price.id,
                material_catalog_id=price.material_catalog_id,
                supplier_id=price.supplier_id,
                supplier_name=supplier.name,
                supplier_product_name=price.supplier_product_name,
                supplier_sku=price.supplier_sku,
                unit=price.unit,
                unit_price=float(price.unit_price),
                currency=price.currency,
                availability_status=price.availability_status,
                source_type=price.source_type,
                source_url=price.source_url,
                valid_from=price.valid_from,
                valid_to=price.valid_to,
                last_seen_at=price.last_seen_at,
                created_at=price.created_at,
                updated_at=price.updated_at,
            )
            for price, supplier in rows
        ]

    async def update_material(self, material_id: str, organization_id: str, *, default_unit_price: float, default_supplier_id: str | None, notes: str | None) -> MaterialCatalogRead | None:
        material = await self.repository.get_material_in_org(material_id, organization_id)
        if not material:
            return None
        updated = await self.repository.update_material(
            material,
            default_unit_price=default_unit_price,
            default_supplier_id=default_supplier_id,
            notes=notes,
        )
        return MaterialCatalogRead(
            id=updated.id,
            organization_id=updated.organization_id,
            name=updated.name,
            category=updated.category,
            unit=updated.unit,
            norm_per_sqm=float(updated.norm_per_sqm),
            default_unit_price=float(updated.default_unit_price),
            default_supplier_id=updated.default_supplier_id,
            default_supplier_name=await self.repository.get_supplier_name(updated.default_supplier_id),
            is_active=updated.is_active,
            notes=updated.notes,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )
