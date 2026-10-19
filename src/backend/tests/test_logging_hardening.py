import inspect
import json
import logging
from pathlib import Path
from uuid import uuid4

import structlog

from app.core.logging import (
    REDACTED,
    REDACTED_BEARER,
    REDACTED_TOKEN,
    configure_logging,
    redact_sensitive_data,
)


def test_redact_sensitive_data_masks_nested_credentials_and_urls():
    payload = {
        "authorization": "Bearer super-secret-access-token",
        "password": "Sup3rSecret!",
        "accessToken": "aaaabbbb.ccccdddd.eeeeffff",
        "refreshToken": "refresh-secret-token-value",
        "nested": {
            "token": "reset-token-value",
            "safe": "ok",
        },
        "url": (
            "https://example.test/reset-password?token=reset-token-value"
            "&x-amz-signature=signature-value"
        ),
        "redis_url": "redis://:verysecretpassword@localhost:6379/0",
    }

    sanitized = redact_sensitive_data(payload)

    assert sanitized["authorization"] == REDACTED
    assert sanitized["password"] == REDACTED
    assert sanitized["accessToken"] == REDACTED
    assert sanitized["refreshToken"] == REDACTED
    assert sanitized["nested"]["token"] == REDACTED
    assert "reset-token-value" not in sanitized["url"]
    assert "signature-value" not in sanitized["url"]
    assert "verysecretpassword" not in sanitized["redis_url"]


def test_configured_structlog_output_redacts_sensitive_values_and_normalizes_security_event(capsys):
    # Anchored to this file: an absolute Windows path is merely relative on Linux,
    # so CI would write the log into a stray "d:" directory instead.
    log_path = Path(__file__).resolve().parents[1] / f".log-test-{uuid4().hex}.json"
    logger = structlog.get_logger("logging-test")
    configure_logging("INFO", log_file=str(log_path))
    try:
        logger.warning(
            "SECURITY_EVENT: auth_refresh_failed",
            authorization="Bearer super-secret-access-token",
            accessToken="aaaabbbb.ccccdddd.eeeeffff",
            refreshToken="refresh-secret-token-value",
            password="Sup3rSecret!",
            token="reset-token-value",
            error=(
                "authorization=Bearer super-secret-access-token "
                "url=https://example.test/reset?token=reset-token-value"
            ),
        )

        captured = capsys.readouterr().out.strip().splitlines()
        record = json.loads(captured[-1])

        rendered = json.dumps(record)
        assert "super-secret-access-token" not in rendered
        assert "refresh-secret-token-value" not in rendered
        assert "reset-token-value" not in rendered
        assert "Sup3rSecret!" not in rendered
        assert record["event"] == "security_event"
        assert record["security_event"] == "auth_refresh_failed"
        assert record["event_category"] == "security"
        assert REDACTED in rendered or REDACTED_BEARER in rendered or REDACTED_TOKEN in rendered
    finally:
        logging.shutdown()
        log_path.unlink(missing_ok=True)


def test_worker_payload_validation_summary_does_not_echo_raw_input():
    from app.worker.runner import WorkerPayloadValidationError, _validate_worker_payload

    raw_secret = "Bearer super-secret-access-token"
    try:
        _validate_worker_payload(
            {
                "job_id": "job_1",
                "project_id": "proj_1",
                "organization_id": "org_1",
                "is_superadmin_context": raw_secret,
            }
        )
    except WorkerPayloadValidationError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected WorkerPayloadValidationError")

    assert raw_secret not in message
    assert "is_superadmin_context" in message


def test_request_logging_source_does_not_log_headers_or_authorization():
    from app.main import create_app

    src = inspect.getsource(create_app)
    log_request_section = src.split('async def log_requests')[1].split('async def request_id_context')[0]

    assert "Authorization" not in log_request_section
    assert "headers=" not in log_request_section
    assert "authorization=" not in log_request_section.lower()
