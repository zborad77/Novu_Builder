from datetime import datetime

from pydantic import BaseModel


class SupplierRead(BaseModel):
    id: str
    organization_id: str
    name: str
    code: str | None = None
    website_url: str | None = None
    integration_type: str
    is_active: bool
    contact_name: str | None = None
    contact_email: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SupplierPatch(BaseModel):
    name: str
    websiteUrl: str | None = None
    integrationType: str
    contactName: str | None = None
    contactEmail: str | None = None
