from datetime import datetime

from pydantic import BaseModel


class ExportRead(BaseModel):
    id: str
    caseId: str
    exportType: str
    status: str
    fileName: str
    downloadUrl: str | None = None
    createdAt: datetime
    completedAt: datetime | None = None


class ExportCreateResponse(BaseModel):
    exportId: str
    status: str
