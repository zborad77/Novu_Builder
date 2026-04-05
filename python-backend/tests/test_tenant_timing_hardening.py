from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException


def _scalar_result(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


class TestAuthTimingHardening:
    @pytest.mark.asyncio
    async def test_login_unknown_email_and_wrong_password_have_consistent_timing(self):
        from app.services.auth_service import AuthService

        missing_session = AsyncMock()
        missing_session.execute = AsyncMock(return_value=_scalar_result(None))

        wrong_user = SimpleNamespace(
            id="usr-1",
            email="known@example.test",
            password_hash="$2b$12$knownhashknownhashknownhashknownhashknownhashknownh",
            is_active=True,
        )
        wrong_password_session = AsyncMock()
        wrong_password_session.execute = AsyncMock(return_value=_scalar_result(wrong_user))

        missing_service = AuthService(missing_session)
        wrong_password_service = AuthService(wrong_password_session)

        def _slow_verify(_plain: str, _hashed: str) -> bool:
            time.sleep(0.003)
            return False

        async def _avg_duration(service: AuthService, email: str) -> float:
            samples = []
            for _ in range(5):
                started_at = perf_counter()
                result = await service.login(email=email, password="WrongPassword99!")
                samples.append(perf_counter() - started_at)
                assert result is None
            return sum(samples) / len(samples)

        with patch("app.services.auth_service._verify_password", side_effect=_slow_verify):
            missing_avg = await _avg_duration(missing_service, "missing@example.test")
            wrong_avg = await _avg_duration(wrong_password_service, "known@example.test")

        assert abs(missing_avg - wrong_avg) < 0.003


class TestTenantResolutionTimingHardening:
    @pytest.mark.asyncio
    async def test_resolution_cache_hit_and_miss_have_consistent_timing(self):
        from app.services.tenant_work_type_resolution_service import TenantWorkTypeResolutionService

        work_type = SimpleNamespace(id="wt-1", code="roof-repair")
        resolved = SimpleNamespace(work_type=work_type)

        async def _measure_miss() -> float:
            repository = AsyncMock()
            repository.get_work_type_by_code_for_resolution = AsyncMock(return_value=work_type)
            service = TenantWorkTypeResolutionService(repository)
            service._resolve_for_work_types = AsyncMock(return_value=[resolved])  # type: ignore[method-assign]
            started_at = perf_counter()
            result = await service.resolve_for_work_type(
                organization_id="org-a",
                work_type_code="roof-repair",
            )
            assert result is resolved
            return perf_counter() - started_at

        async def _measure_hit() -> float:
            repository = AsyncMock()
            repository.get_work_type_by_code_for_resolution = AsyncMock(return_value=work_type)
            service = TenantWorkTypeResolutionService(repository)
            service._resolved_by_work_type.set(
                ("org-a", "roof-repair"),
                resolved,
                tag="0",
            )
            started_at = perf_counter()
            result = await service.resolve_for_work_type(
                organization_id="org-a",
                work_type_code="roof-repair",
            )
            assert result is resolved
            return perf_counter() - started_at

        with patch(
            "app.services.tenant_work_type_resolution_service.TENANT_SENSITIVE_TIMING_FLOOR_SECONDS",
            0.01,
        ):
            miss_avg = sum([await _measure_miss() for _ in range(5)]) / 5
            hit_avg = sum([await _measure_hit() for _ in range(5)]) / 5

        assert miss_avg >= 0.009
        assert hit_avg >= 0.009
        assert abs(miss_avg - hit_avg) < 0.006


class TestAnalysisTenantIsolationHardening:
    @pytest.mark.asyncio
    async def test_get_job_uses_tenant_scoped_lookup_before_any_global_lookup(self):
        from app.services.analysis_service import AnalysisService

        repository = AsyncMock()
        repository.get_analysis_job_in_org = AsyncMock(return_value=None)
        repository.get_analysis_job = AsyncMock(side_effect=AssertionError("global lookup must not be used"))

        service = AnalysisService(
            repository=repository,
            photo_repository=AsyncMock(),
            work_catalog_repository=AsyncMock(),
            provider_key="anthropic",
        )

        result = await service.get_job(
            "job-cross-tenant",
            organization_id="org-a",
            is_superadmin_context=False,
            job_queue=None,
        )

        assert result is None
        repository.get_analysis_job_in_org.assert_awaited_once_with("job-cross-tenant", "org-a")
        repository.get_analysis_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_job_uses_tenant_scoped_lookup_before_any_global_lookup(self):
        from app.services.analysis_service import AnalysisService

        repository = AsyncMock()
        repository.get_analysis_job_in_org = AsyncMock(return_value=None)
        repository.get_analysis_job = AsyncMock(side_effect=AssertionError("global lookup must not be used"))

        service = AnalysisService(
            repository=repository,
            photo_repository=AsyncMock(),
            work_catalog_repository=AsyncMock(),
            provider_key="anthropic",
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.retry_job(
                "job-cross-tenant",
                organization_id="org-a",
                is_superadmin_context=False,
                job_queue=None,
            )

        assert exc_info.value.status_code == 404
        repository.get_analysis_job_in_org.assert_awaited_once_with("job-cross-tenant", "org-a")
        repository.get_analysis_job.assert_not_called()


class TestExportTenantIsolationHardening:
    @pytest.mark.asyncio
    async def test_get_export_uses_tenant_scoped_lookup_before_any_global_lookup(self):
        from app.services.export_service import ExportService

        repository = AsyncMock()
        repository.get_by_id_in_org = AsyncMock(return_value=None)
        repository.get_by_id = AsyncMock(side_effect=AssertionError("global lookup must not be used"))

        service = ExportService(repository)

        result = await service.get_export(
            "exp-cross-tenant",
            organization_id="org-a",
            is_superadmin_context=False,
        )

        assert result is None
        repository.get_by_id_in_org.assert_awaited_once_with("exp-cross-tenant", "org-a")
        repository.get_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_export_scoped_hit_and_miss_have_consistent_timing(self):
        from app.services.export_service import ExportService

        async def _sleepy_lookup(export_id: str, organization_id: str):
            await asyncio.sleep(0.003)
            if export_id == "exp-hit":
                return SimpleNamespace(
                    id="exp-hit",
                    project_id="proj-1",
                    export_type="report-pdf",
                    status="pending",
                    file_name="report.pdf",
                    storage_key=None,
                    created_at=datetime.now(UTC),
                    completed_at=None,
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                )
            return None

        repository = AsyncMock()
        repository.get_by_id_in_org = AsyncMock(side_effect=_sleepy_lookup)
        service = ExportService(repository)

        async def _avg_duration(export_id: str) -> float:
            samples = []
            for _ in range(5):
                started_at = perf_counter()
                await service.get_export(
                    export_id,
                    organization_id="org-a",
                    is_superadmin_context=False,
                )
                samples.append(perf_counter() - started_at)
            return sum(samples) / len(samples)

        hit_avg = await _avg_duration("exp-hit")
        miss_avg = await _avg_duration("exp-miss")

        assert abs(hit_avg - miss_avg) < 0.004
