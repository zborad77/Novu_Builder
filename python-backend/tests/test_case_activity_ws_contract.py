from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.case_activity import (
    CaseActivitySubscribeCommand,
    ImageStatusChangedEvent,
    JobCompletedEvent,
    JobStatusChangedEvent,
    validate_case_activity_command,
    validate_case_activity_event,
)


def test_validate_case_activity_event_accepts_job_status_changed_payload():
    event = validate_case_activity_event(
        {
            "type": "job_status_changed",
            "caseId": "case_123",
            "jobId": "job_123",
            "status": "running",
            "timestamp": "2026-04-20T12:30:45Z",
        }
    )

    assert isinstance(event, JobStatusChangedEvent)
    assert event.caseId == "case_123"
    assert event.jobId == "job_123"
    assert event.status == "running"
    assert event.timestamp == datetime(2026, 4, 20, 12, 30, 45, tzinfo=event.timestamp.tzinfo)


def test_validate_case_activity_event_accepts_job_completed_payload():
    event = validate_case_activity_event(
        {
            "type": "job_completed",
            "caseId": "case_123",
            "jobId": "job_123",
            "status": "completed",
            "timestamp": "2026-04-20T12:31:10Z",
        }
    )

    assert isinstance(event, JobCompletedEvent)
    assert event.status == "completed"


def test_validate_case_activity_event_accepts_image_status_changed_payload():
    event = validate_case_activity_event(
        {
            "type": "image_status_changed",
            "caseId": "case_123",
            "imageId": "img_123",
            "jobId": "job_123",
            "status": "processing",
            "timestamp": "2026-04-20T12:32:00Z",
        }
    )

    assert isinstance(event, ImageStatusChangedEvent)
    assert event.imageId == "img_123"
    assert event.jobId == "job_123"
    assert event.status == "processing"


def test_validate_case_activity_event_fails_fast_on_wrong_root_shape():
    with pytest.raises(ValidationError):
        validate_case_activity_event(
            {
                "type": "job_status_changed",
                "caseId": "case_123",
                "status": "running",
                "timestamp": "2026-04-20T12:30:45Z",
            }
        )


def test_validate_case_activity_event_fails_fast_on_invalid_terminal_status():
    with pytest.raises(ValidationError):
        validate_case_activity_event(
            {
                "type": "job_completed",
                "caseId": "case_123",
                "jobId": "job_123",
                "status": "running",
                "timestamp": "2026-04-20T12:31:10Z",
            }
        )


def test_validate_case_activity_event_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        validate_case_activity_event(
            {
                "type": "image_status_changed",
                "caseId": "case_123",
                "imageId": "img_123",
                "status": "ready",
                "timestamp": "2026-04-20T12:32:00Z",
                "unexpected": "value",
            }
        )


def test_validate_case_activity_command_accepts_subscribe_payload():
    command = validate_case_activity_command(
        {
            "type": "subscribe",
            "caseId": "case_123",
            "jobId": "job_123",
        }
    )

    assert isinstance(command, CaseActivitySubscribeCommand)
    assert command.caseId == "case_123"
    assert command.jobId == "job_123"


def test_validate_case_activity_command_fails_fast_on_unknown_fields():
    with pytest.raises(ValidationError):
        validate_case_activity_command(
            {
                "type": "unsubscribe",
                "unexpected": "value",
            }
        )
