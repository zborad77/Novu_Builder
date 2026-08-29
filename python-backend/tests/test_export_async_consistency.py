from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.project_service import ProjectService


@pytest.mark.asyncio
async def test_create_final_proposal_awaits_export_generation():
    ready_primary = SimpleNamespace(
        processing_status="ready",
        is_primary=True,
        is_analysis_reference=False,
    )
    ready_reference = SimpleNamespace(
        processing_status="ready",
        is_primary=False,
        is_analysis_reference=True,
    )
    ready_other = SimpleNamespace(
        processing_status="ready",
        is_primary=False,
        is_analysis_reference=False,
    )
    project = SimpleNamespace(
        id="prj_001",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        proposal_draft=object(),
        photos=[ready_primary, ready_reference, ready_other],
        final_proposals=[],
        analysis_results=[],
        quote_variants=[],
    )
    detail = SimpleNamespace(id="prj_001", finalProposal=object())
    created_snapshot = SimpleNamespace(id="fin_001")

    repository = MagicMock()
    repository.get_project = AsyncMock(return_value=project)
    # Archive timeline query — no outbox rows for this case.
    _timeline_rows = MagicMock()
    _timeline_rows.scalars.return_value.all.return_value = []
    repository.session.execute = AsyncMock(return_value=_timeline_rows)
    final_proposal_repository = MagicMock()
    final_proposal_repository.create_for_project = AsyncMock(return_value=created_snapshot)
    export_service = MagicMock()
    export_service.create_final_proposal_exports = AsyncMock(return_value=[])

    service = ProjectService(
        repository=repository,
        proposal_draft_repository=MagicMock(),
        final_proposal_repository=final_proposal_repository,
        export_service=export_service,
    )

    with (
        patch(
            "app.services.project_service.build_project_proposal_draft",
            return_value=SimpleNamespace(status="ready"),
        ),
        patch(
            "app.services.project_service.build_final_proposal_snapshot_payload",
            return_value={"subject": "Test"},
        ),
        patch("app.services.project_service.build_project_detail", return_value=detail),
    ):
        result = await service.create_final_proposal("prj_001", organization_id="org_001")

    assert result is detail
    # The immutable archive always carries at least the synthetic case.created entry.
    export_service.create_final_proposal_exports.assert_awaited_once_with(
        case_detail=detail,
        timeline_events=[
            {
                "eventType": "case.created",
                "occurredAt": "2026-01-01T00:00:00+00:00",
                "payload": {},
            }
        ],
    )
