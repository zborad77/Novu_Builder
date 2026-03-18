from datetime import datetime

from pydantic import BaseModel


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
    sortOrder: int
    url: str
    variants: PhotoVariants


class PhotoListMeta(BaseModel):
    minimumRecommendedCount: int
    hasMinimumCount: bool
    primaryPhotoId: str | None = None
    derivativeStrategy: dict[str, str]


class PhotoListResponse(BaseModel):
    items: list[ProjectPhotoRead]
    meta: PhotoListMeta


class PhotoJsonUploadItem(BaseModel):
    originalFilename: str | None = None
    mimeType: str = "image/jpeg"
    fileSize: int = 0
    width: int | None = None
    height: int | None = None
    takenAt: datetime | None = None
    exifLat: float | None = None
    exifLng: float | None = None
    isPrimary: bool = False
    sortOrder: int | None = None


class PhotoJsonUploadRequest(BaseModel):
    files: list[PhotoJsonUploadItem]


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


class DeletePhotoResponse(BaseModel):
    message: str
