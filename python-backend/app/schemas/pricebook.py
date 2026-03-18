from datetime import datetime

from pydantic import BaseModel


class PricebookRead(BaseModel):
    id: str
    name: str
    organizationId: str
    hourlyRate: float
    dailyRate: float
    laborHoursPerSqm: float
    vatPct: float
    currency: str
    isDefault: bool
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class PricebookCreate(BaseModel):
    name: str
    hourlyRate: float
    dailyRate: float
    laborHoursPerSqm: float
    vatPct: float = 21
    currency: str = "CZK"
    isDefault: bool = False


class PricebookItemRead(BaseModel):
    id: str
    materialCatalogId: str
    name: str
    category: str | None = None
    unit: str
    normPerSqm: float
    defaultUnitPrice: float
    defaultSupplierId: str | None = None
    notes: str | None = None
    isActive: bool


class PricebookListResponse(BaseModel):
    items: list[PricebookRead]
