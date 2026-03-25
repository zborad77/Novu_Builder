from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_export_service, get_current_user, get_project_service, require_manager
from app.schemas.auth import AuthUserRead
from app.schemas.export import ExportCreateResponse, ExportRead
from app.services.export_service import ExportService
from app.services.project_service import ProjectService

router = APIRouter(tags=["exports"])


@router.post("/cases/{case_id}/exports/report-pdf", response_model=ExportCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_report_pdf(
    case_id: str,
    current_user: AuthUserRead = Depends(require_manager),
    project_service: ProjectService = Depends(get_project_service),
    export_service: ExportService = Depends(get_export_service),
) -> ExportCreateResponse:
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    export = export_service.create_export(case_id=case_id, export_type="report-pdf")
    return ExportCreateResponse(exportId=export.id, status=export.status)


@router.post("/cases/{case_id}/exports/proposal-docx", response_model=ExportCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_proposal_docx(
    case_id: str,
    current_user: AuthUserRead = Depends(require_manager),
    project_service: ProjectService = Depends(get_project_service),
    export_service: ExportService = Depends(get_export_service),
) -> ExportCreateResponse:
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
    detail = await project_service.get_project_detail(case_id, organization_id=org_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    if detail.proposalDraft is None:
        raise HTTPException(status_code=409, detail="Proposal draft must exist before working DOCX export.")
    export = export_service.create_proposal_docx_export(case_detail=detail)
    return ExportCreateResponse(exportId=export.id, status=export.status)


@router.post("/cases/{case_id}/exports/quote-pdf", response_model=ExportCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_quote_pdf(
    case_id: str,
    current_user: AuthUserRead = Depends(require_manager),
    project_service: ProjectService = Depends(get_project_service),
    export_service: ExportService = Depends(get_export_service),
) -> ExportCreateResponse:
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    detail = await project_service.get_project_detail(case_id, organization_id=org_id)
    if not detail or detail.finalProposal is None:
        raise HTTPException(status_code=409, detail="Final proposal must be created before PDF export.")
    export = export_service.create_quote_pdf_export(case_detail=detail)
    return ExportCreateResponse(exportId=export.id, status=export.status)


@router.post("/cases/{case_id}/exports/quote-docx", response_model=ExportCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_quote_docx(
    case_id: str,
    current_user: AuthUserRead = Depends(require_manager),
    project_service: ProjectService = Depends(get_project_service),
    export_service: ExportService = Depends(get_export_service),
) -> ExportCreateResponse:
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
    detail = await project_service.get_project_detail(case_id, organization_id=org_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    if detail.finalProposal is None:
        raise HTTPException(status_code=409, detail="Final proposal must be created before DOCX export.")
    export = export_service.create_quote_docx_export(case_detail=detail)
    return ExportCreateResponse(exportId=export.id, status=export.status)


@router.post("/cases/{case_id}/exports/case-zip", response_model=ExportCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_case_zip(
    case_id: str,
    current_user: AuthUserRead = Depends(require_manager),
    project_service: ProjectService = Depends(get_project_service),
    export_service: ExportService = Depends(get_export_service),
) -> ExportCreateResponse:
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
    detail = await project_service.get_project_detail(case_id, organization_id=org_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    export = export_service.create_case_zip_export(case_detail=detail)
    return ExportCreateResponse(exportId=export.id, status=export.status)


@router.get("/exports/{export_id}", response_model=ExportRead)
async def get_export(
    export_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    export_service: ExportService = Depends(get_export_service),
) -> ExportRead:
    export = export_service.get_export(export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Export not found.")
    if not current_user.isSuperAdmin:
        project = await project_service.get_project(
            export.caseId,
            organization_id=current_user.organizationId,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Export not found.")
    return export
