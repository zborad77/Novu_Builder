from datetime import datetime

from pydantic import BaseModel


class QuoteItemRead(BaseModel):
    id: str
    quoteVariantId: str
    itemType: str
    name: str
    description: str | None = None
    quantity: float
    unit: str
    unitPrice: float
    totalPrice: float
    materialCatalogId: str | None = None
    supplierId: str | None = None
    priceSource: str
    isManualOverride: bool
    aiSuggestedUnitPrice: float | None = None
    supplierReferenceUnitPrice: float | None = None
    companyDefaultUnitPrice: float | None = None
    sortOrder: int
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class QuoteVariantRead(BaseModel):
    id: str
    projectId: str
    analysisResultId: str | None = None
    pricingProfileId: str | None = None
    variantType: str
    laborCost: float
    materialCost: float
    otherCost: float
    marginPct: float
    totalExVat: float
    vatAmount: float
    totalIncVat: float
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    items: list[QuoteItemRead]


class QuoteVariantListResponse(BaseModel):
    items: list[QuoteVariantRead]


class QuoteVariantRecalculateSummary(BaseModel):
    id: str
    variantType: str
    totalIncVat: float


class QuoteVariantRecalculateResponse(BaseModel):
    variants: list[QuoteVariantRecalculateSummary]


class QuoteVariantPatch(BaseModel):
    laborCost: float | None = None
    materialCost: float | None = None
    otherCost: float | None = None
    marginPct: float | None = None


class AnalysisJobRead(BaseModel):
    id: str
    projectId: str
    status: str
    jobType: str
    requestedByUserId: str | None = None
    startedAt: datetime | None = None
    finishedAt: datetime | None = None
    errorMessage: str | None = None
    createdAt: datetime | None = None
