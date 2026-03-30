from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


class TestMeasurementRouteTenantEnforcement:
    @pytest.mark.asyncio
    async def test_patch_measurement_forwards_org_scope_to_service_update(self):
        from app.api.routes.measurements import patch_measurement
        from app.schemas.measurement import MeasurementUpsert
        from app.services.analysis_service import AnalysisService
        from app.services.project_service import ProjectService

        current_user = MagicMock()
        current_user.isSuperAdmin = False
        current_user.organizationId = "org_A"
        current_user.id = "usr_1"

        existing = MagicMock()
        existing.id = "ana_1"
        existing.projectId = "prj_A"
        existing.referencePhotoId = None
        existing.selectedRepairPolygon = None
        existing.estimatedAreaSqm = 12.0
        existing.manualAreaSqm = 15.0
        existing.finalAreaSource = "manual"
        existing.createdAt = None

        analysis_service = AsyncMock(spec=AnalysisService)
        analysis_service.get_analysis_result_by_id = AsyncMock(return_value=existing)
        analysis_service.update_manual_selection_by_result_id = AsyncMock(return_value=existing)

        project_service = AsyncMock(spec=ProjectService)

        response = await patch_measurement(
            measurement_id="ana_1",
            payload=MeasurementUpsert(manualAreaSqm=15.0),
            current_user=current_user,
            analysis_service=analysis_service,
            project_service=project_service,
        )

        assert response.id == "ana_1"
        analysis_service.update_manual_selection_by_result_id.assert_awaited_once_with(
            "ana_1",
            {"manualAreaSqm": 15.0},
            organization_id="org_A",
        )

    @pytest.mark.asyncio
    async def test_patch_measurement_keeps_not_found_when_service_denies_cross_tenant_update(self):
        from app.api.routes.measurements import patch_measurement
        from app.schemas.measurement import MeasurementUpsert
        from app.services.analysis_service import AnalysisService
        from app.services.project_service import ProjectService

        current_user = MagicMock()
        current_user.isSuperAdmin = False
        current_user.organizationId = "org_A"
        current_user.id = "usr_1"

        existing = MagicMock()
        existing.id = "ana_1"
        existing.projectId = "prj_A"

        analysis_service = AsyncMock(spec=AnalysisService)
        analysis_service.get_analysis_result_by_id = AsyncMock(return_value=existing)
        analysis_service.update_manual_selection_by_result_id = AsyncMock(return_value=None)

        project_service = AsyncMock(spec=ProjectService)

        with pytest.raises(HTTPException) as exc_info:
            await patch_measurement(
                measurement_id="ana_1",
                payload=MeasurementUpsert(manualAreaSqm=15.0),
                current_user=current_user,
                analysis_service=analysis_service,
                project_service=project_service,
            )

        assert exc_info.value.status_code == 404


class TestAnalysisSelectionRouteTenantEnforcement:
    @pytest.mark.asyncio
    async def test_patch_analysis_selection_forwards_org_scope_to_service_update(self):
        from app.api.routes.analysis_jobs import patch_analysis_selection
        from app.services.analysis_service import AnalysisService
        from app.services.project_service import ProjectService

        current_user = MagicMock()
        current_user.isSuperAdmin = False
        current_user.organizationId = "org_A"

        project = MagicMock()
        project.id = "prj_A"

        analysis_result = MagicMock()
        analysis_result.id = "ana_1"
        analysis_result.projectId = "prj_A"

        project_service = AsyncMock(spec=ProjectService)
        project_service.get_project = AsyncMock(return_value=project)

        analysis_service = AsyncMock(spec=AnalysisService)
        analysis_service.get_analysis_result_by_id = AsyncMock(return_value=analysis_result)
        updated = MagicMock()
        updated.id = "ana_1"
        analysis_service.update_manual_selection_by_result_id = AsyncMock(return_value=updated)

        response = await patch_analysis_selection(
            case_id="prj_A",
            result_id="ana_1",
            body={"manualAreaSqm": 15.0},
            current_user=current_user,
            project_service=project_service,
            analysis_service=analysis_service,
        )

        assert response == {"id": "ana_1", "status": "ok"}
        analysis_service.update_manual_selection_by_result_id.assert_awaited_once_with(
            "ana_1",
            {"manualAreaSqm": 15.0, "finalAreaSource": "manual"},
            organization_id="org_A",
        )
