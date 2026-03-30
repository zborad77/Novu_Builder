from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


def _make_project(project_id: str = "prj_A", org_id: str = "org_A"):
    project = MagicMock()
    project.id = project_id
    project.organization_id = org_id
    return project


class TestImageLeanGuards:
    @pytest.mark.asyncio
    async def test_set_primary_image_returns_404_when_case_not_found(self):
        from app.api.routes.images import set_case_primary_image
        from app.services.photo_service import PhotoService
        from app.services.project_service import ProjectService

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_A"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=None)

        mock_photo_service = AsyncMock(spec=PhotoService)

        with pytest.raises(HTTPException) as exc_info:
            await set_case_primary_image(
                case_id="prj_missing",
                image_id="pho_1",
                current_user=mock_user,
                project_service=mock_project_service,
                photo_service=mock_photo_service,
            )

        assert exc_info.value.status_code == 404
        mock_project_service.get_project_lean.assert_called_once_with("prj_missing", organization_id="org_A")
        mock_photo_service.set_primary_photo.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_primary_image_succeeds_with_lean_guard(self):
        from app.api.routes.images import set_case_primary_image
        from app.services.photo_service import PhotoService
        from app.services.project_service import ProjectService

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_A"

        from app.schemas.photo import ProjectPhotoRead

        variant = {"storageKey": None, "fileSize": None, "width": None, "height": None, "url": None}
        photo = ProjectPhotoRead(
            id="pho_1",
            projectId="prj_A",
            originalFilename="photo.jpg",
            storageKey="projects/prj_A/photo.jpg",
            mimeType="image/jpeg",
            fileSize=123,
            processingStatus="ready",
            isPrimary=True,
            isAnalysisReference=False,
            sortOrder=1,
            url="/mock-storage/projects/prj_A/photo.jpg",
            variants={"original": variant, "preview": variant, "aiInput": variant},
        )

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=_make_project())

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.set_primary_photo = AsyncMock(return_value=photo)

        response = await set_case_primary_image(
            case_id="prj_A",
            image_id="pho_1",
            current_user=mock_user,
            project_service=mock_project_service,
            photo_service=mock_photo_service,
        )

        assert response.message == "Primary image updated."
        mock_project_service.get_project_lean.assert_called_once_with("prj_A", organization_id="org_A")
        mock_photo_service.set_primary_photo.assert_called_once_with("prj_A", "pho_1")


class TestMeasurementLeanGuards:
    @pytest.mark.asyncio
    async def test_create_measurement_returns_404_when_case_not_found(self):
        from app.api.routes.measurements import create_or_update_measurement
        from app.schemas.measurement import MeasurementUpsert
        from app.services.analysis_service import AnalysisService
        from app.services.project_service import ProjectService

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_A"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=None)

        mock_analysis_service = AsyncMock(spec=AnalysisService)

        with pytest.raises(HTTPException) as exc_info:
            await create_or_update_measurement(
                case_id="prj_missing",
                payload=MeasurementUpsert(),
                current_user=mock_user,
                project_service=mock_project_service,
                analysis_service=mock_analysis_service,
            )

        assert exc_info.value.status_code == 404
        mock_project_service.get_project_lean.assert_called_once_with("prj_missing", organization_id="org_A")
        mock_analysis_service.update_manual_selection.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_measurement_succeeds_with_lean_guard(self):
        from app.api.routes.measurements import create_or_update_measurement
        from app.schemas.measurement import MeasurementUpsert
        from app.services.analysis_service import AnalysisService
        from app.services.project_service import ProjectService

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_A"

        updated = MagicMock()
        updated.id = "res_1"
        updated.projectId = "prj_A"
        updated.referencePhotoId = "pho_ref"
        updated.selectedRepairPolygon = [{"x": 1.0, "y": 2.0}]
        updated.estimatedAreaSqm = 12.5
        updated.manualAreaSqm = 15.0
        updated.finalAreaSource = "manual"
        updated.createdAt = None

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=_make_project())

        mock_analysis_service = AsyncMock(spec=AnalysisService)
        mock_analysis_service.update_manual_selection = AsyncMock(return_value=updated)

        response = await create_or_update_measurement(
            case_id="prj_A",
            payload=MeasurementUpsert(manualAreaSqm=15.0),
            current_user=mock_user,
            project_service=mock_project_service,
            analysis_service=mock_analysis_service,
        )

        assert response.id == "res_1"
        assert response.caseId == "prj_A"
        assert response.confirmed is True
        mock_project_service.get_project_lean.assert_called_once_with("prj_A", organization_id="org_A")
        mock_analysis_service.update_manual_selection.assert_called_once_with("prj_A", {"manualAreaSqm": 15.0})
