from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PhotoVariant(BaseModel):
    storageKey: str | None = None
    fileSize: int | None = None
    width: int | None = None
    height: int | None = None
    url: str | None = None


class PhotoVariants(BaseModel):
    original: PhotoVariant
    preview: PhotoVariant
    aiInput: PhotoVariant


class ProjectPhotoRead(BaseModel):
    id: str
    projectId: str
    originalFilename: str
    storageKey: str
    mimeType: str
    fileSize: int
    width: int | None = None
    height: int | None = None
    takenAt: datetime | None = None
    exifLat: float | None = None
    exifLng: float | None = None
    processingStatus: str
    isPrimary: bool
    isAnalysisReference: bool
    sortOrder: int
    url: str
    variants: PhotoVariants
    # Additive (F0.3): optional so existing clients and fixtures stay valid.
    # Author recorded by the server; None for legacy photos or a removed account.
    uploadedByUserId: str | None = None
    # Whether the requesting user may soft-delete/restore this photo. None where
    # the response is not tied to a requesting user.
    canDelete: bool | None = None


class PhotoListMeta(BaseModel):
    minimumRecommendedCount: int
    hasMinimumCount: bool
    primaryPhotoId: str | None = None
    analysisReferencePhotoId: str | None = None
    derivativeStrategy: dict[str, str]


class PhotoListResponse(BaseModel):
    items: list[ProjectPhotoRead]
    meta: PhotoListMeta


class UploadedPhotoPayload(BaseModel):
    id: str
    storageKey: str
    isPrimary: bool
    processingStatus: str
    variants: PhotoVariants


class PhotoUploadResponse(BaseModel):
    uploaded: list[UploadedPhotoPayload]


class PrimaryPhotoResponse(BaseModel):
    message: str
    photo: ProjectPhotoRead


class AnalysisReferencePhotoResponse(BaseModel):
    message: str
    photo: ProjectPhotoRead


class DeletePhotoResponse(BaseModel):
    message: str


class RestorePhotoResponse(BaseModel):
    message: str


class DeletedPhotoRead(BaseModel):
    """A soft-deleted photo that can still be restored."""

    id: str
    originalFilename: str
    deletedAt: datetime | None
    deletedByUserId: str | None


class DeletedPhotoListResponse(BaseModel):
    items: list[DeletedPhotoRead]


class PurgePhotoRequest(BaseModel):
    """Permanent deletion must be confirmed by repeating the photo id."""

    model_config = ConfigDict(extra="forbid")

    confirmImageId: str


class PurgePhotoResponse(BaseModel):
    imageId: str
    # "purged": storage removed. "purge_pending": authorised and hidden; the
    # worker finishes storage removal (storage was unavailable).
    status: Literal["purged", "purge_pending"]


class PhotoMoveRequest(BaseModel):
    direction: Literal["up", "down"]
