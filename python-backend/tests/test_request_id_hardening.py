import json
import logging
import re
import tempfile
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.request_id import REQUEST_ID_MAX_LENGTH, sanitize_request_id
from app.main import create_app


_HEX_REQUEST_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _load_http_request_log(output: str) -> dict:
    records = [
        json.loads(line)
        for line in output.splitlines()
        if line.strip().startswith("{")
    ]
    return next(record for record in reversed(records) if record.get("event") == "http.request")


async def _perform_request_with_log(monkeypatch, capsys, request_id: str | None):
    log_path = Path(tempfile.gettempdir()) / f"novu-request-id-{sanitize_request_id(None)}.json"
    monkeypatch.setenv("LOG_FILE", str(log_path))
    # /alive returns 200, so main.py logs "http.request" at INFO. Pin the level
    # instead of inheriting it: CI runs with LOG_LEVEL=WARNING, which filters the
    # record out and leaves nothing for _load_http_request_log to parse.
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    get_settings.cache_clear()

    app = create_app()
    headers = {"X-Request-ID": request_id} if request_id is not None else {}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/alive", headers=headers)
        logging.shutdown()
        output = capsys.readouterr().out
        return response, _load_http_request_log(output)
    finally:
        log_path.unlink(missing_ok=True)
        get_settings.cache_clear()


async def test_request_id_preserves_valid_short_ascii_header(monkeypatch, capsys):
    request_id = "client-req-123.ABC_xyz"

    response, record = await _perform_request_with_log(monkeypatch, capsys, request_id)

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert record["request_id"] == request_id


async def test_request_id_replaces_too_long_header(monkeypatch, capsys):
    request_id = "a" * (REQUEST_ID_MAX_LENGTH + 1)

    response, record = await _perform_request_with_log(monkeypatch, capsys, request_id)

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != request_id
    assert _HEX_REQUEST_ID_RE.fullmatch(response.headers["X-Request-ID"])
    assert record["request_id"] == response.headers["X-Request-ID"]


def test_request_id_replaces_newline_or_nonprintable_input():
    for request_id in ("line1\nline2", "tab\tvalue", "nul\x00byte"):
        sanitized = sanitize_request_id(request_id)
        assert sanitized != request_id
        assert _HEX_REQUEST_ID_RE.fullmatch(sanitized)


async def test_request_id_generates_safe_value_when_header_missing(monkeypatch, capsys):
    response, record = await _perform_request_with_log(monkeypatch, capsys, None)

    assert response.status_code == 200
    assert _HEX_REQUEST_ID_RE.fullmatch(response.headers["X-Request-ID"])
    assert record["request_id"] == response.headers["X-Request-ID"]
