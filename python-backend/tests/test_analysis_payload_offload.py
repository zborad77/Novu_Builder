import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import get_settings
from app.services.analysis_service import AnalysisService, _payload_has_large_blob


def test_payload_has_large_blob_detects_base64_like_string():
    payload = {
        "imageBase64": "A" * 4096,
        "provider": "mock",
    }

    assert _payload_has_large_blob(payload) is True


@pytest.mark.asyncio
async def test_persist_job_input_payload_offloads_large_payload(monkeypatch):
    monkeypatch.setenv("ANALYSIS_JOB_INLINE_PAYLOAD_MAX_BYTES", "1024")
    get_settings.cache_clear()
    service = AnalysisService(
        repository=None,  # type: ignore[arg-type]
        photo_repository=None,  # type: ignore[arg-type]
        provider_key="mock",
    )
    job = SimpleNamespace(
        id="job_payload_1",
        input_payload=None,
        input_payload_storage_key=None,
    )
    payload = {"imageBase64": "A" * 5000, "provider": "mock"}

    try:
        with patch(
            "app.services.analysis_service.write_storage_file",
            new=AsyncMock(),
        ) as write_storage_file:
            cleanup_key = await service._persist_job_input_payload(job, payload)
    finally:
        get_settings.cache_clear()

    assert cleanup_key is None
    assert job.input_payload_storage_key == "analysis-jobs/job_payload_1/input-payload.json"
    write_storage_file.assert_awaited_once()
    stored_summary = json.loads(job.input_payload)
    assert stored_summary["offloaded"] is True
    assert stored_summary["storageKey"] == job.input_payload_storage_key
    assert stored_summary["payloadBytes"] > 1024


@pytest.mark.asyncio
async def test_persist_job_input_payload_returns_previous_storage_key_when_inline_again(monkeypatch):
    monkeypatch.setenv("ANALYSIS_JOB_INLINE_PAYLOAD_MAX_BYTES", "32768")
    get_settings.cache_clear()
    service = AnalysisService(
        repository=None,  # type: ignore[arg-type]
        photo_repository=None,  # type: ignore[arg-type]
        provider_key="mock",
    )
    job = SimpleNamespace(
        id="job_payload_2",
        input_payload=None,
        input_payload_storage_key="analysis-jobs/job_payload_2/input-payload.json",
    )

    try:
        cleanup_key = await service._persist_job_input_payload(
            job,
            {"provider": "mock", "photo_count": 3},
        )
    finally:
        get_settings.cache_clear()

    assert cleanup_key == "analysis-jobs/job_payload_2/input-payload.json"
    assert job.input_payload_storage_key is None
    assert json.loads(job.input_payload) == {"provider": "mock", "photo_count": 3}
