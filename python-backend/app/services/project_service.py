import json
from uuid import uuid4

from app.models import Project, ProjectPhoto
from app.repositories.final_proposal_repository import FinalProposalRepository
from app.repositories.proposal_draft_repository import ProposalDraftRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectDuplicateRequest, ProjectSummary
from app.services.export_service import ExportService
from app.services.proposal_draft_service import (
    build_final_proposal_from_record,
    build_final_proposal_snapshot_payload,
    build_project_proposal_draft,
    normalize_proposal_patch_payload,
)
from app.storage.local_photo_storage import copy_storage_file


DEFAULT_ORGANIZATION_ID = "org_1"
DEFAULT_CREATED_BY_USER_ID = "usr_1"
MIN_READY_PHOTOS_FOR_FINAL_PROPOSAL = 3


def is_reference_dataset_project(project: Project) -> bool:
    return project.id.startswith("ref_case_")


def build_project_summary(project: Project) -> ProjectSummary:
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
    )


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
        latestAnalysis=None,
        proposalDraft=proposal_draft,
        finalProposal=build_final_proposal_from_record(latest_final),
        quoteVariants=[],
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

            duplicated_photos.append(
                ProjectPhoto(
                    id=duplicated_photo_id,
                    project_id=duplicated_project.id,
                    storage_key=duplicated_storage_key or "",
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

    async def get_project(self, project_id: str) -> Project | None:
        return await self.repository.get_project(project_id)

    async def list_projects(self, *, status: str | None = None, search: str | None = None) -> list[ProjectSummary]:
        projects = await self.repository.list_projects(status=status, search=search)
        return [build_project_summary(project) for project in projects]

    async def get_project_detail(self, project_id: str) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id)
        if not project:
            return None
        return build_project_detail(project)

    async def create_project(self, payload: ProjectCreate) -> Project:
        project_id = f"prj_{uuid4().hex[:8]}"
        return await self.repository.create_project(
            project_id=project_id,
            organization_id=DEFAULT_ORGANIZATION_ID,
            created_by_user_id=DEFAULT_CREATED_BY_USER_ID,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else "",
            client_id=payload.clientId,
            property_type=payload.propertyType,
            repair_scope=payload.repairScope,
            location_lat=payload.locationLat,
            location_lng=payload.locationLng,
            address_label=payload.addressLabel,
        )

    async def duplicate_project(self, project_id: str, payload: ProjectDuplicateRequest) -> Project | None:
        source_project = await self.repository.get_project(project_id)
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

    async def mark_project_sent(self, project_id: str) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id)
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

    async def update_proposal_draft(self, project_id: str, payload: dict) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id)
        if not project:
            return None

        normalized_payload = normalize_proposal_patch_payload(payload)
        updated_draft = await self.proposal_draft_repository.upsert_for_project(project.id, normalized_payload)
        project.proposal_draft = updated_draft
        return build_project_detail(project)

    async def create_final_proposal(self, project_id: str) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id)
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

    async def update_project(self, project_id: str, payload: dict) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id)
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
