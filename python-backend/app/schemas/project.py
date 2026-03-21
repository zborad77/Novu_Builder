from datetime import datetime
from typing import Literal

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


class ProjectReferenceExpectations(BaseModel):
    sourceRepo: str | None = None
    sourcePage: str | None = None
    expectedScope: str | None = None
    expectedPrimaryFilename: str | None = None
    expectedAnalysisReferenceFilename: str | None = None


class ProjectSummary(BaseModel):
    id: str
    title: str
    status: str
    isReferenceDataset: bool = False
    propertyType: str | None = None
    repairScope: str | None = None
    addressLabel: str | None = None
    photoCount: int = 0
    estimatedAreaSqm: float | None = None
    latestQuoteTotal: float | None = None
    updatedAt: datetime | None = None
    createdByName: str | None = None


class ProposalDraftWorkItem(BaseModel):
    name: str
    note: str | None = None


class ProposalDraftMaterial(BaseModel):
    name: str
    quantity: float
    unit: str
    unitPrice: float
    totalPrice: float
    note: str | None = None


class ProposalDraftField(BaseModel):
    id: str
    label: str
    value: str | float | int | None = None
    displayValue: str | None = None
    source: str
    editable: bool = True
    manualOverride: bool = False


class ProposalDraftItem(BaseModel):
    id: str
    label: str
    description: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unitPrice: float | None = None
    totalPrice: float | None = None
    source: str
    editable: bool = False
    manualOverride: bool = False


class ProposalDraftSection(BaseModel):
    id: str
    title: str
    kind: Literal["fields", "items"]
    fields: list[ProposalDraftField] = Field(default_factory=list)
    items: list[ProposalDraftItem] = Field(default_factory=list)


class ProjectProposalDraft(BaseModel):
    status: str
    version: int = 1
    sourcePhotoCount: int = 0
    readyPhotoCount: int = 0
    primaryPhotoId: str | None = None
    subject: str | None = None
    summary: str | None = None
    suggestedWorkItems: list[ProposalDraftWorkItem] = Field(default_factory=list)
    materials: list[ProposalDraftMaterial] = Field(default_factory=list)
    materialCost: float | None = None
    laborCost: float | None = None
    transportCost: float | None = None
    amortization: float | None = None
    margin: float | None = None
    recommendedSupplier: str | None = None
    recommendedCompany: str | None = None
    totalPrice: float | None = None
    sections: list[ProposalDraftSection] = Field(default_factory=list)


class ProjectFinalProposal(BaseModel):
    id: str
    status: str
    draftVersion: int
    currency: str = "CZK"
    subject: str | None = None
    summary: str | None = None
    totalPrice: float | None = None
    sections: list[ProposalDraftSection] = Field(default_factory=list)
    createdAt: datetime | None = None


class ProjectProposalDraftPatch(BaseModel):
    subject: str | None = None
    summary: str | None = None
    materialCost: float | None = None
    laborCost: float | None = None
    transportCost: float | None = None
    amortization: float | None = None
    margin: float | None = None
    recommendedSupplier: str | None = None
    recommendedCompany: str | None = None


class ProjectWorkflowPhotoReadiness(BaseModel):
    totalPhotoCount: int = 0
    readyPhotoCount: int = 0
    minimumRecommendedCount: int = 3
    hasMinimumRecommendedCount: bool = False
    hasPrimaryReadyPhoto: bool = False
    hasAnalysisReferenceReadyPhoto: bool = False


class ProjectWorkflowStatusSummary(BaseModel):
    photoReadiness: ProjectWorkflowPhotoReadiness
    analysisStatus: str
    draftStatus: str
    finalProposalStatus: str | None = None
    canCreateFinalProposal: bool = False
    canSend: bool = False
    blockingReasons: list[str] = Field(default_factory=list)


class ProjectDetail(BaseModel):
    id: str
    title: str
    description: str | None = None
    status: str
    isReferenceDataset: bool = False
    source: str = "mobile"
    propertyType: str | None = None
    repairScope: str | None = None
    location: ProjectLocation
    client: ProjectClient | None = None
    photos: list = Field(default_factory=list)
    latestAnalysis: dict | None = None
    proposalDraft: ProjectProposalDraft | None = None
    finalProposal: ProjectFinalProposal | None = None
    workflowStatus: ProjectWorkflowStatusSummary | None = None
    quoteVariants: list = Field(default_factory=list)
    referenceExpectations: ProjectReferenceExpectations | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]
    total: int


class ProjectCreate(BaseModel):
    title: str
    description: str | None = None
    source: str = "mobile"
    clientId: str | None = None
    locationLat: float | None = None
    locationLng: float | None = None
    addressLabel: str | None = None
    propertyType: str | None = None
    repairScope: str | None = None


class ProjectCreateResponse(BaseModel):
    id: str
    status: str


class ProjectDuplicateRequest(BaseModel):
    title: str | None = None
    mode: Literal["copy", "variant"] = "copy"


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
