"""API schémata návrhu nabídky (draft a finální návrh) – modul quoting."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    analysisResultId: str | None = None
    inputVersions: dict | None = None
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
    # Optimistic concurrency token.  When provided, the server rejects the
    # update with 409 PROPOSAL_STALE if the stored draft has a different version.
    expectedVersion: int | None = None
