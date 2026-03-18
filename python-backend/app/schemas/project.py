from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectLocation(BaseModel):
    lat: float | None = None
    lng: float | None = None
    addressLabel: str | None = None


class ProjectClient(BaseModel):
    id: str
    fullName: str
    companyName: str | None = None
    email: str | None = None
    phone: str | None = None


class ProjectSummary(BaseModel):
    id: str
    title: str
    status: str
    propertyType: str | None = None
    repairScope: str | None = None
    addressLabel: str | None = None
    photoCount: int = 0
    estimatedAreaSqm: float | None = None
    latestQuoteTotal: float | None = None
    updatedAt: datetime | None = None


class ProjectDetail(BaseModel):
    id: str
    title: str
    description: str | None = None
    status: str
    propertyType: str | None = None
    repairScope: str | None = None
    location: ProjectLocation
    client: ProjectClient | None = None
    photos: list = Field(default_factory=list)
    latestAnalysis: dict | None = None
    quoteVariants: list = Field(default_factory=list)
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]
    total: int


class ProjectCreate(BaseModel):
    title: str
    description: str | None = None
    clientId: str | None = None
    locationLat: float | None = None
    locationLng: float | None = None
    addressLabel: str | None = None
    propertyType: str | None = None
    repairScope: str | None = None


class ProjectCreateResponse(BaseModel):
    id: str
    status: str


class ProjectPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    propertyType: str | None = None
    repairScope: str | None = None
    locationLat: float | None = None
    locationLng: float | None = None
    addressLabel: str | None = None
    clientId: str | None = None


class ORMProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
