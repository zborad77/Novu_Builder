from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.routes.case_activity_ws import (
    CaseActivitySnapshot,
    CaseActivitySubscription,
    _build_snapshot_events,
)
from app.main import app as fastapi_app
from app.models import AnalysisJob
from tests.conftest import _InMemoryAuthRedis, _TestSession


def test_build_snapshot_events_emits_terminal_job_and_changed_images():
    subscription = CaseActivitySubscription(
        case_id="case_123",
        job_id="job_123",
        organization_id="org_123",
        is_superadmin_context=False,
    )
    previous = CaseActivitySnapshot(
        job_status="running",
        image_statuses={"img_1": "processing"},
    )
    current = CaseActivitySnapshot(
        job_status="completed",
        image_statuses={"img_1": "ready", "img_2": "uploaded"},
    )

    events = _build_snapshot_events(subscription, previous, current)

    assert [event["type"] for event in events] == [
        "job_completed",
        "image_status_changed",
        "image_status_changed",
    ]
    assert events[0]["status"] == "completed"
    assert events[1]["imageId"] == "img_1"
    assert events[2]["imageId"] == "img_2"
    assert isinstance(datetime.fromisoformat(events[0]["timestamp"].replace("Z", "+00:00")), datetime)


@pytest.mark.asyncio
async def test_case_activity_websocket_emits_initial_job_snapshot(test_tenants):
    original_auth_store = getattr(fastapi_app.state, "auth_token_store", None)
    fastapi_app.state.auth_token_store = _InMemoryAuthRedis()

    try:
        with TestClient(fastapi_app) as client:
            login_response = client.post(
                "/api/v1/auth/login",
                json=test_tenants["user_a"],
            )
            assert login_response.status_code == 200, login_response.text
            token = login_response.json()["accessToken"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            create_case_response = client.post(
                "/api/v1/cases",
                json={"title": "WS Route Snapshot Case"},
                headers=auth_headers,
            )
            assert create_case_response.status_code == 201, create_case_response.text
            case_id = create_case_response.json()["id"]

            async with _TestSession() as session:
                session.add(
                    AnalysisJob(
                        id="job_ws_snapshot_1",
                        project_id=case_id,
                        status="queued",
                        job_type="manual_trigger",
                        requested_by_user_id="usr_e2e_a1",
                    )
                )
                await session.commit()

            with client.websocket_connect(f"/api/v1/ws/case-activity?token={token}") as websocket:
                websocket.send_json(
                    {
                        "type": "subscribe",
                        "caseId": case_id,
                        "jobId": "job_ws_snapshot_1",
                    }
                )
                event = websocket.receive_json()

            assert event["type"] == "job_status_changed"
            assert event["caseId"] == case_id
            assert event["jobId"] == "job_ws_snapshot_1"
            assert event["status"] == "queued"
    finally:
        fastapi_app.state.auth_token_store = original_auth_store
