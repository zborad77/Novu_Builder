from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Project, ProjectPhoto
from app.repositories.final_proposal_repository import FinalProposalRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.proposal_draft_repository import ProposalDraftRepository
from app.schemas.project import ProjectDuplicateRequest
from app.services.project_service import ProjectService


@pytest.mark.asyncio
async def test_duplicate_project_rolls_back_copied_storage_and_project_row_on_failure(db_session, test_tenants):
    token = uuid4().hex[:8]
    source_project_id = f"prj_dup_{token}"
    created_at = datetime.now(UTC)
    db_session.add(
        Project(
            id=source_project_id,
            organization_id=test_tenants["org_a"],
            created_by_user_id="usr_e2e_a1",
            title="Dup source",
            description="",
            status="draft",
            source="mobile",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db_session.add(
        ProjectPhoto(
            id=f"pho_dup_{token}",
            project_id=source_project_id,
            status="active",
            storage_key=f"projects/{source_project_id}/original.jpg",
            preview_storage_key=f"projects/{source_project_id}/preview.jpg",
            ai_input_storage_key=None,
            original_filename="original.jpg",
            mime_type="image/jpeg",
            file_size=123,
            processing_status="ready",
            is_primary=True,
            is_analysis_reference=True,
            sort_order=1,
            created_at=created_at,
        )
    )
    await db_session.commit()

    service = ProjectService(
        repository=ProjectRepository(db_session),
        proposal_draft_repository=ProposalDraftRepository(db_session),
        final_proposal_repository=FinalProposalRepository(db_session),
        export_service=MagicMock(),
    )
    source_project = await service.get_project(source_project_id, organization_id=test_tenants["org_a"])
    assert source_project is not None

    copied_targets: list[str] = []

    async def failing_copy(*, source_storage_key: str, target_storage_key: str) -> None:
        copied_targets.append(target_storage_key)
        if target_storage_key.endswith("preview.jpg"):
            raise OSError("copy interrupted")

    with (
        patch("app.services.project_service.copy_storage_file", side_effect=failing_copy),
        patch("app.services.project_service.delete_storage_file", new_callable=AsyncMock) as delete_storage,
    ):
        with pytest.raises(OSError, match="copy interrupted"):
            await service.duplicate_project(
                source_project_id,
                ProjectDuplicateRequest(mode="copy"),
                organization_id=test_tenants["org_a"],
            )

    rows = await db_session.execute(
        select(Project).where(Project.title.like("Dup source%"))
    )
    projects = rows.scalars().all()
    assert [project.id for project in projects] == [source_project_id]
    delete_storage.assert_awaited_once_with(relative_storage_key=copied_targets[0])
