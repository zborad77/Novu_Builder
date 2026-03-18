from app.repositories.supplier_repository import SupplierRepository
from app.schemas.supplier import SupplierRead


class SupplierService:
    def __init__(self, repository: SupplierRepository):
        self.repository = repository

    async def list_suppliers(self, *, include_inactive: bool = False) -> list[SupplierRead]:
        items = await self.repository.list_suppliers(active_only=not include_inactive)
        return [
            SupplierRead(
                id=item.id,
                organization_id=item.organization_id,
                name=item.name,
                code=item.code,
                website_url=item.website_url,
                integration_type=item.integration_type,
                is_active=item.is_active,
                contact_name=item.contact_name,
                contact_email=item.contact_email,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]

    async def update_supplier(
        self,
        supplier_id: str,
        *,
        name: str,
        website_url: str | None,
        integration_type: str,
        contact_name: str | None,
        contact_email: str | None,
    ) -> SupplierRead | None:
        supplier = await self.repository.get_supplier(supplier_id)
        if not supplier:
            return None
        updated = await self.repository.update_supplier(
            supplier,
            name=name,
            website_url=website_url,
            integration_type=integration_type,
            contact_name=contact_name,
            contact_email=contact_email,
        )
        return SupplierRead(
            id=updated.id,
            organization_id=updated.organization_id,
            name=updated.name,
            code=updated.code,
            website_url=updated.website_url,
            integration_type=updated.integration_type,
            is_active=updated.is_active,
            contact_name=updated.contact_name,
            contact_email=updated.contact_email,
            created_at=updated.created_at,
            updated_at=updated.updated_at,
        )
