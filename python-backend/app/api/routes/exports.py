from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_export_service, get_project_service
from app.schemas.export import ExportCreateResponse, ExportRead
from app.services.export_service import ExportService
from app.services.project_service import ProjectService

router = APIRouter(tags=["exports"])


@router.post("/cases/{case_id}/exports/report-pdf", response_model=ExportCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_report_pdf(
    case_id: str,
    project_service: ProjectService = Depends(get_project_service),
    export_service: ExportService = Depends(get_export_service),
) -> ExportCreateResponse:
    project = await project_service.get_project(case_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    export = export_service.create_export(case_id=case_id, export_type="report-pdf")
    return ExportCreateResponse(exportId=export.id, status=export.status)


@router.post("/cases/{case_id}/exports/quote-pdf", response_model=ExportCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_quote_pdf(
    case_id: str,
    project_service: ProjectService = Depends(get_project_service),
    export_service: ExportService = Depends(get_export_service),
) -> ExportCreateResponse:
    project = await project_service.get_project(case_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    export = export_service.create_export(case_id=case_id, export_type="quote-pdf")
    return ExportCreateResponse(exportId=export.id, status=export.status)


@router.get("/exports/{export_id}", response_model=ExportRead)
async def get_export(
    export_id: str,
    export_service: ExportService = Depends(get_export_service),
) -> ExportRead:
    export = export_service.get_export(export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Export not found.")
    return export
