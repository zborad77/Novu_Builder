import json
from uuid import uuid4

import structlog

from app.models import Project, ProjectPhoto
from app.repositories.final_proposal_repository import FinalProposalRepository
from app.repositories.proposal_draft_repository import ProposalDraftRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import (
    ProjectCreate,
    ProjectDetail,
    ProjectDuplicateRequest,
    ProjectSummary,
    ProjectWorkflowPhotoReadiness,
    ProjectWorkflowStatusSummary,
)
from app.services.export_service import ExportService
from app.services.proposal_draft_service import (
    build_final_proposal_from_record,
    build_final_proposal_snapshot_payload,
    build_project_proposal_draft,
    normalize_proposal_patch_payload,
)
from app.storage.local_photo_storage import copy_storage_file

logger = structlog.get_logger(__name__)

MIN_READY_PHOTOS_FOR_FINAL_PROPOSAL = 3


def is_reference_dataset_project(project: Project) -> bool:
    return project.id.startswith("ref_case_")


def build_project_summary(project: Project) -> ProjectSummary:
    creator = getattr(project, "created_by_user", None)
    return ProjectSummary(
        id=project.id,
        title=project.title,
        status=project.status,
        isReferenceDataset=is_reference_dataset_project(project),
        propertyType=project.property_type,
        repairScope=project.repair_scope,
        addressLabel=project.address_label,
        photoCount=len(project.photos) if getattr(project, "photos", None) else 0,
        estimatedAreaSqm=None,
        latestQuoteTotal=None,
        updatedAt=project.updated_at,
        createdByName=creator.full_name if creator else None,
    )


def build_project_workflow_status_summary(
    project: Project,
    *,
    proposal_draft,
    latest_final,
) -> ProjectWorkflowStatusSummary:
    photos = project.photos or []
    ready_photos = [photo for photo in photos if photo.processing_status == "ready"]
    total_photo_count = len(photos)
    ready_photo_count = len(ready_photos)
    has_primary_ready_photo = any(photo.is_primary for photo in ready_photos)
    has_analysis_reference_ready_photo = any(photo.is_analysis_reference for photo in ready_photos)
    has_pending_processing = any(photo.processing_status in {"uploaded", "processing"} for photo in photos)
    has_minimum_recommended_count = ready_photo_count >= MIN_READY_PHOTOS_FOR_FINAL_PROPOSAL

    photo_readiness = ProjectWorkflowPhotoReadiness(
        totalPhotoCount=total_photo_count,
        readyPhotoCount=ready_photo_count,
        minimumRecommendedCount=MIN_READY_PHOTOS_FOR_FINAL_PROPOSAL,
        hasMinimumRecommendedCount=has_minimum_recommended_count,
        hasPrimaryReadyPhoto=has_primary_ready_photo,
        hasAnalysisReferenceReadyPhoto=has_analysis_reference_ready_photo,
    )

    blocking_reasons: list[str] = []
    if total_photo_count == 0:
        analysis_status = "waiting_for_photos"
        blocking_reasons.append("No photos have been uploaded yet.")
    elif has_pending_processing:
        analysis_status = "processing_photos"
        blocking_reasons.append("Server is still processing uploaded photos.")
    elif not has_minimum_recommended_count:
        analysis_status = "awaiting_more_photos"
        blocking_reasons.append(
            f"At least {MIN_READY_PHOTOS_FOR_FINAL_PROPOSAL} ready photos are recommended before finalizing."
        )
    else:
        analysis_status = "ready_for_server_analysis"

    if not has_primary_ready_photo:
        blocking_reasons.append("A primary photo in ready state is required.")
    if not has_analysis_reference_ready_photo:
        blocking_reasons.append("An analysis reference photo in ready state is required.")

    draft_status = proposal_draft.status if proposal_draft is not None else "missing"
    if proposal_draft is None:
        blocking_reasons.append("Proposal draft is not available.")
    elif proposal_draft.status != "ready":
        blocking_reasons.append(f"Proposal draft must be ready. Current status: {proposal_draft.status}.")

    can_create_final_proposal = (
        proposal_draft is not None
        and proposal_draft.status == "ready"
        and has_minimum_recommended_count
        and has_primary_ready_photo
        and has_analysis_reference_ready_photo
    )

    final_proposal_status = latest_final.status if latest_final is not None else None
    can_send = latest_final is not None
    if latest_final is None:
        blocking_reasons.append("Final proposal has not been created yet.")

    deduplicated_blocking_reasons = list(dict.fromkeys(blocking_reasons))

    return ProjectWorkflowStatusSummary(
        photoReadiness=photo_readiness,
        analysisStatus=analysis_status,
        draftStatus=draft_status,
        finalProposalStatus=final_proposal_status,
        canCreateFinalProposal=can_create_final_proposal,
        canSend=can_send,
        blockingReasons=deduplicated_blocking_reasons,
    )


def _build_latest_analysis_dict(project: Project) -> dict | None:
    results = getattr(project, "analysis_results", None) or []
    if not results:
        return None
    latest = max(results, key=lambda r: (r.created_at or project.created_at, r.id))
    workflow_raw = _parse_json(latest.workflow_suggestion_json)
    materials_raw = _parse_json(latest.materials_suggestion_json)
    mask_polygon_raw = _parse_json(latest.mask_polygon_json)
    return {
        "id": latest.id,
        "objectType": latest.object_type,
        "surfaceCondition": latest.surface_condition,
        "recommendedScope": latest.recommended_scope,
        "estimatedAreaSqm": latest.estimated_area_sqm,
        "areaConfidence": latest.area_confidence,
        "manualAreaSqm": latest.manual_area_sqm,
        "finalAreaSource": latest.final_area_source,
        "maskPolygon": mask_polygon_raw if isinstance(mask_polygon_raw, list) else [],
        "workflowSteps": workflow_raw if isinstance(workflow_raw, list) else [],
        "materials": materials_raw if isinstance(materials_raw, list) else [],
        "estimatedDurationDays": latest.estimated_duration_days,
        "laborHoursTotal": latest.labor_hours_total,
        "modelName": latest.model_name,
        "modelVersion": latest.model_version,
        "createdAt": latest.created_at.isoformat() if latest.created_at else None,
    }


def _build_quote_variants_list(project: Project) -> list:
    from app.services.quote_variant_service import to_variant_read
    variants = getattr(project, "quote_variants", None) or []
    if not variants:
        return []
    sorted_variants = sorted(variants, key=lambda v: (v.created_at or project.created_at, v.id))
    return [to_variant_read(v).model_dump() for v in sorted_variants]


def _parse_json(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def build_project_detail(project: Project) -> ProjectDetail:
    proposal_draft = build_project_proposal_draft(project, project.photos or [], proposal_record=project.proposal_draft)
    latest_final = None
    if getattr(project, "final_proposals", None):
        latest_final = max(
            project.final_proposals,
            key=lambda proposal: ((proposal.created_at or project.created_at), proposal.id),
        )
    reference_expectations = None
    if project.reference_expectations_json:
        try:
            reference_expectations = json.loads(project.reference_expectations_json)
        except json.JSONDecodeError:
            reference_expectations = None

    return ProjectDetail(
        id=project.id,
        title=project.title,
        description=project.description,
        status=project.status,
        isReferenceDataset=is_reference_dataset_project(project),
        source=getattr(project, "source", "mobile") or "mobile",  # backward compatibility fallback — source absent in pre-migration records
        propertyType=project.property_type,
        repairScope=project.repair_scope,
        location={
            "lat": project.location_lat,
            "lng": project.location_lng,
            "addressLabel": project.address_label,
        },
        client=(
            {
                "id": project.client.id,
                "fullName": project.client.full_name,
                "companyName": project.client.company_name,
                "email": project.client.email,
                "phone": project.client.phone,
            }
            if project.client
            else None
        ),
        photos=[],
        latestAnalysis=_build_latest_analysis_dict(project),
        proposalDraft=proposal_draft,
        finalProposal=build_final_proposal_from_record(latest_final),
        workflowStatus=build_project_workflow_status_summary(
            project,
            proposal_draft=proposal_draft,
            latest_final=latest_final,
        ),
        quoteVariants=_build_quote_variants_list(project),
        referenceExpectations=reference_expectations,
        createdAt=project.created_at,
        updatedAt=project.updated_at,
    )


def build_duplicate_project_title(source_title: str, mode: str) -> str:
    suffix = "Varianta" if mode == "variant" else "Kopie"
    normalized_title = source_title.strip() if source_title else "Zakazka"
    duplicate_suffixes = (" - Kopie", " - Varianta")
    title_changed = True
    while title_changed:
        title_changed = False
        for duplicate_suffix in duplicate_suffixes:
            if normalized_title.endswith(duplicate_suffix):
                normalized_title = normalized_title[: -len(duplicate_suffix)].rstrip()
                title_changed = True
    return f"{normalized_title} - {suffix}"


def build_duplicated_storage_key(source_storage_key: str | None, source_project_id: str, target_project_id: str) -> str | None:
    if not source_storage_key:
        return None

    source_prefix = f"projects/{source_project_id}/"
    target_prefix = f"projects/{target_project_id}/"
    if source_storage_key.startswith(source_prefix):
        return target_prefix + source_storage_key[len(source_prefix):]
    return source_storage_key.replace(source_project_id, target_project_id, 1)


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        proposal_draft_repository: ProposalDraftRepository,
        final_proposal_repository: FinalProposalRepository,
        export_service: ExportService,
    ):
        self.repository = repository
        self.proposal_draft_repository = proposal_draft_repository
        self.final_proposal_repository = final_proposal_repository
        self.export_service = export_service

    async def _duplicate_project_photos(self, source_project: Project, duplicated_project: Project) -> None:
        duplicated_photos: list[ProjectPhoto] = []

        for source_photo in source_project.photos or []:
            duplicated_photo_id = f"pho_{uuid4().hex[:8]}"
            duplicated_storage_key = build_duplicated_storage_key(source_photo.storage_key, source_project.id, duplicated_project.id)
            duplicated_preview_key = build_duplicated_storage_key(source_photo.preview_storage_key, source_project.id, duplicated_project.id)
            duplicated_ai_key = build_duplicated_storage_key(source_photo.ai_input_storage_key, source_project.id, duplicated_project.id)

            if duplicated_storage_key and source_photo.storage_key:
                copy_storage_file(source_storage_key=source_photo.storage_key, target_storage_key=duplicated_storage_key)
            if duplicated_preview_key and source_photo.preview_storage_key:
                copy_storage_file(source_storage_key=source_photo.preview_storage_key, target_storage_key=duplicated_preview_key)
            if duplicated_ai_key and source_photo.ai_input_storage_key:
                copy_storage_file(source_storage_key=source_photo.ai_input_storage_key, target_storage_key=duplicated_ai_key)

            if not duplicated_storage_key:
                # Intentional fail-safe skip: if the target storage_key cannot be resolved,
                # do not persist a photo record with storage_key="" — that would create a DB
                # reference to a non-existent file and cause 404 errors on photo retrieval.
                # Remaining valid photos continue to be duplicated normally.
                logger.warning(
                    "photo.duplicate.storage_key_unresolvable",
                    source_photo_id=source_photo.id,
                    source_project_id=source_project.id,
                    duplicated_project_id=duplicated_project.id,
                )
                continue

            duplicated_photos.append(
                ProjectPhoto(
                    id=duplicated_photo_id,
                    project_id=duplicated_project.id,
                    storage_key=duplicated_storage_key,
                    preview_storage_key=duplicated_preview_key,
                    ai_input_storage_key=duplicated_ai_key,
                    original_filename=source_photo.original_filename,
                    mime_type=source_photo.mime_type,
                    file_size=source_photo.file_size,
                    width=source_photo.width,
                    height=source_photo.height,
                    preview_file_size=source_photo.preview_file_size,
                    preview_width=source_photo.preview_width,
                    preview_height=source_photo.preview_height,
                    ai_input_file_size=source_photo.ai_input_file_size,
                    ai_input_width=source_photo.ai_input_width,
                    ai_input_height=source_photo.ai_input_height,
                    processing_status=source_photo.processing_status,
                    taken_at=source_photo.taken_at,
                    exif_lat=source_photo.exif_lat,
                    exif_lng=source_photo.exif_lng,
                    is_primary=source_photo.is_primary,
                    is_analysis_reference=source_photo.is_analysis_reference,
                    sort_order=source_photo.sort_order,
                )
            )

        self.repository.session.add_all(duplicated_photos)
        await self.repository.session.commit()

    async def get_project(self, project_id: str, *, organization_id: str | None = None) -> Project | None:
        return await self.repository.get_project(project_id, organization_id=organization_id)

    async def list_projects(
        self,
        *,
        organization_id: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> list[ProjectSummary]:
        projects = await self.repository.list_projects(organization_id=organization_id, status=status, search=search)
        return [build_project_summary(project) for project in projects]

    async def get_project_detail(self, project_id: str, *, organization_id: str | None = None) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id, organization_id=organization_id)
        if not project:
            return None
        return build_project_detail(project)

    async def create_project(self, payload: ProjectCreate, *, organization_id: str, created_by_user_id: str) -> Project:
        project_id = f"prj_{uuid4().hex[:8]}"
        return await self.repository.create_project(
            project_id=project_id,
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else "",
            client_id=payload.clientId,
            property_type=payload.propertyType,
            repair_scope=payload.repairScope,
            location_lat=payload.locationLat,
            location_lng=payload.locationLng,
            address_label=payload.addressLabel,
            source=payload.source or "mobile",  # intentional business default — mobile is the canonical source for new projects
        )

    async def duplicate_project(self, project_id: str, payload: ProjectDuplicateRequest, *, organization_id: str | None = None) -> Project | None:
        source_project = await self.repository.get_project(project_id, organization_id=organization_id)
        if not source_project:
            return None

        duplicate_title = (
            payload.title.strip()
            if payload.title and payload.title.strip()
            else build_duplicate_project_title(source_project.title, payload.mode)
        )

        duplicated_project = await self.repository.create_project(
            project_id=f"prj_{uuid4().hex[:8]}",
            organization_id=source_project.organization_id,
            created_by_user_id=source_project.created_by_user_id,
            title=duplicate_title,
            description=source_project.description,
            client_id=source_project.client_id,
            property_type=source_project.property_type,
            repair_scope=source_project.repair_scope,
            location_lat=source_project.location_lat,
            location_lng=source_project.location_lng,
            address_label=source_project.address_label,
        )
        await self._duplicate_project_photos(source_project, duplicated_project)
        return await self.repository.get_project(duplicated_project.id)

    async def mark_project_sent(self, project_id: str, *, organization_id: str | None = None) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id, organization_id=organization_id)
        if not project:
            return None

        latest_final = None
        if getattr(project, "final_proposals", None):
            latest_final = max(
                project.final_proposals,
                key=lambda proposal: ((proposal.created_at or project.created_at), proposal.id),
            )
        if latest_final is None:
            raise ValueError("Final proposal must exist before sending the case.")

        updated = await self.repository.update_project(project, {"status": "sent"})
        return build_project_detail(updated)

    async def update_proposal_draft(self, project_id: str, payload: dict, *, organization_id: str | None = None) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id, organization_id=organization_id)
        if not project:
            return None

        normalized_payload = normalize_proposal_patch_payload(payload)
        updated_draft = await self.proposal_draft_repository.upsert_for_project(project.id, normalized_payload)
        project.proposal_draft = updated_draft
        return build_project_detail(project)

    async def create_final_proposal(self, project_id: str, *, organization_id: str | None = None) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id, organization_id=organization_id)
        if not project:
            return None

        proposal_draft = build_project_proposal_draft(project, project.photos or [], proposal_record=project.proposal_draft)
        ready_photos = [photo for photo in (project.photos or []) if photo.processing_status == "ready"]
        if proposal_draft.status != "ready":
            raise ValueError(
                f"Final proposal can only be created from a ready proposal draft. Current status: {proposal_draft.status}."
            )
        if len(ready_photos) < MIN_READY_PHOTOS_FOR_FINAL_PROPOSAL:
            raise ValueError(
                f"Final proposal requires at least {MIN_READY_PHOTOS_FOR_FINAL_PROPOSAL} ready photos."
            )
        if not any(photo.is_primary for photo in ready_photos):
            raise ValueError("Final proposal requires a primary ready photo.")
        if not any(photo.is_analysis_reference for photo in ready_photos):
            raise ValueError("Final proposal requires an analysis reference photo in ready state.")
        snapshot_payload = build_final_proposal_snapshot_payload(proposal_draft)
        created_snapshot = await self.final_proposal_repository.create_for_project(project_id=project.id, payload=snapshot_payload)
        project.final_proposals = [*(project.final_proposals or []), created_snapshot]
        detail = build_project_detail(project)
        self.export_service.create_final_proposal_exports(case_detail=detail)
        return detail

    async def update_project(self, project_id: str, payload: dict, *, organization_id: str | None = None) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id, organization_id=organization_id)
        if not project:
            return None

        changes = {}
        field_mapping = {
            "title": "title",
            "description": "description",
            "status": "status",
            "propertyType": "property_type",
            "repairScope": "repair_scope",
            "locationLat": "location_lat",
            "locationLng": "location_lng",
            "addressLabel": "address_label",
            "clientId": "client_id",
        }

        for payload_field, model_field in field_mapping.items():
            if payload_field in payload:
                changes[model_field] = payload[payload_field]

        updated = await self.repository.update_project(project, changes)
        return build_project_detail(updated)
