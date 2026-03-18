from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.export import ExportRead


_EXPORT_STORE: dict[str, ExportRead] = {}


class ExportService:
    def create_export(self, *, case_id: str, export_type: str) -> ExportRead:
        export_id = f"exp_{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        export = ExportRead(
            id=export_id,
            caseId=case_id,
            exportType=export_type,
            status="completed",
            fileName=f"{case_id}-{export_type}.pdf",
            downloadUrl=f"/mock-storage/exports/{case_id}-{export_type}.pdf",
            createdAt=now,
            completedAt=now,
        )
        _EXPORT_STORE[export_id] = export
        return export

    def get_export(self, export_id: str) -> ExportRead | None:
        return _EXPORT_STORE.get(export_id)
