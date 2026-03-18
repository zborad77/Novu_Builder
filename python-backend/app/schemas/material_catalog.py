from datetime import datetime

from pydantic import BaseModel


class MaterialCatalogRead(BaseModel):
    id: str
    organization_id: str
    name: str
    category: str | None = None
    unit: str
    norm_per_sqm: float
    default_unit_price: float
    default_supplier_id: str | None = None
    default_supplier_name: str | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SupplierPriceRead(BaseModel):
    id: str
    material_catalog_id: str
    supplier_id: str
    supplier_name: str
    supplier_product_name: str | None = None
    supplier_sku: str | None = None
    unit: str
    unit_price: float
    currency: str
    availability_status: str | None = None
    source_type: str
    source_url: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    last_seen_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MaterialCatalogPatch(BaseModel):
    defaultUnitPrice: float
    defaultSupplierId: str | None = None
    notes: str | None = None
