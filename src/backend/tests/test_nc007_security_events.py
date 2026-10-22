"""NC-007 etapa 1, kap. 6.4: ``POST /api/v1/internal/security-events``.

Endpoint je jen v zóně gateway: požadavek musí nést platný podpis gateway
(``tests/conftest.py::_sign_like_the_gateway`` ho v zóně gateway doplní) a
nesmí mít hlavičku ``Authorization`` (jinak 404). Události se zapisují do
``audit_logs`` jako ``gateway.<type>`` / ``web_session``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.modules.audit.models import AuditLog
from tests.conftest import TEST_GATEWAY_KEY_ID, UNSIGNED_MARKER

URL = "/api/v1/internal/security-events"
TYPES = [
    "login_success",
    "login_failure",
    "logout",
    "logout_all",
    "session_expired",
    "session_revoked",
    "csrf_failure",
    "origin_failure",
    "allowlist_miss",
    "rate_limited",
    "upstream_unavailable",
]


@pytest.fixture
def gateway_zone(monkeypatch):
    from app.platform.config import get_settings

    monkeypatch.setattr(get_settings(), "nc_zone", "gateway")


def _event(type_: str = "login_failure", **overrides) -> dict:
    event = {
        "type": type_,
        "occurredAt": datetime.now(UTC).isoformat(),
        "clientIp": "198.51.100.7",
        "userId": None,
        "organizationId": None,
        "sessionRef": None,
        "requestId": f"req-{uuid.uuid4().hex[:12]}",
        "detail": {"reason": "bad_password"},
    }
    event.update(overrides)
    return event


async def _rows(db_session_factory, request_id: str) -> list[AuditLog]:
    async with db_session_factory() as session:
        rows = (await session.execute(select(AuditLog).where(AuditLog.resource_type == "web_session"))).scalars().all()
    return [row for row in rows if (row.detail or {}).get("requestId") == request_id]


async def test_batch_is_accepted_and_written_to_audit_logs(app_client, gateway_zone, db_session_factory, test_tenants):
    tag = uuid.uuid4().hex[:8]
    events = [
        _event(t, requestId=f"req-{tag}", sessionRef="0123456789abcdef", userId="usr_e2e_a1", organizationId="org_e2e_a")
        for t in TYPES
    ]
    response = await app_client.post(URL, json={"events": events})
    assert response.status_code == 202, response.text
    assert response.json() == {"accepted": len(TYPES)}

    rows = await _rows(db_session_factory, f"req-{tag}")
    assert sorted(row.action for row in rows) == sorted(f"gateway.{t}" for t in TYPES)
    row = rows[0]
    assert row.resource_type == "web_session"
    assert row.resource_id == "0123456789abcdef"
    assert row.ip == "198.51.100.7"
    assert row.user_id == "usr_e2e_a1"
    assert row.org_id == "org_e2e_a"
    assert row.detail["event"] == {"reason": "bad_password"}
    assert row.detail["sessionRef"] == "0123456789abcdef"
    assert row.detail["gatewayKeyId"] == TEST_GATEWAY_KEY_ID
    assert row.detail["occurredAt"]


async def test_audit_middleware_does_not_add_a_generic_row(app_client, gateway_zone, db_session_factory):
    from sqlalchemy import func

    async def count() -> int:
        async with db_session_factory() as session:
            return int((await session.execute(select(func.count()).select_from(AuditLog))).scalar_one())

    before = await count()
    response = await app_client.post(URL, json={"events": [_event()]})
    assert response.status_code == 202
    # Přesně jeden řádek (událost), žádný obecný záznam POST požadavku z AuditMiddleware.
    assert await count() == before + 1


async def test_empty_batch_is_accepted(app_client, gateway_zone):
    response = await app_client.post(URL, json={"events": []})
    assert response.status_code == 202
    assert response.json() == {"accepted": 0}


async def test_request_with_authorization_header_is_404(app_client, gateway_zone, token_a, db_session_factory):
    tag = f"req-auth-{uuid.uuid4().hex[:8]}"
    for value in (f"Bearer {token_a}", "Bearer x", ""):
        response = await app_client.post(URL, json={"events": [_event(requestId=tag)]}, headers={"Authorization": value})
        assert response.status_code == 404, value
        assert response.json() == {"detail": "Not Found"}
    # 404 i s neplatným tělem: kontrola hlavičky předchází validaci.
    response = await app_client.post(URL, json={"events": "nope"}, headers={"Authorization": "Bearer x"})
    assert response.status_code == 404
    assert await _rows(db_session_factory, tag) == []


async def test_unsigned_request_is_401(app_client, gateway_zone, db_session_factory):
    tag = f"req-unsigned-{uuid.uuid4().hex[:8]}"
    response = await app_client.post(URL, json={"events": [_event(requestId=tag)]}, headers={UNSIGNED_MARKER: "1"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid gateway signature."}
    assert await _rows(db_session_factory, tag) == []


@pytest.mark.parametrize(
    "body",
    [
        {"events": [_event("password_changed")]},
        {"events": [_event("LOGIN_FAILURE")]},
        {"events": [_event() for _ in range(51)]},
        {"events": [_event(detail={"blob": "x" * 2100})]},
        {"events": [_event(detail={"blob": "č" * 1100})]},  # 2 200 B v UTF-8
        {"events": [_event(clientIp="not-an-ip")]},
        {"events": [_event(sessionRef="NOT-HEX-0123456")]},
        {"events": [_event(sessionRef="0123456789abcdef0")]},
        {"events": [{k: v for k, v in _event().items() if k != "type"}]},
        {"events": [_event(unexpected="field")]},
        {"events": [_event(occurredAt="yesterday")]},
        {"items": []},
    ],
)
async def test_invalid_batches_are_422(app_client, gateway_zone, body):
    response = await app_client.post(URL, json=body)
    assert response.status_code == 422, response.text


async def test_fifty_events_and_detail_just_under_the_limit_are_accepted(app_client, gateway_zone):
    detail = {"blob": "x" * (2048 - len('{"blob":""}'))}
    response = await app_client.post(URL, json={"events": [_event(detail=detail)] * 50})
    assert response.status_code == 202, response.text
    assert response.json() == {"accepted": 50}


@pytest.mark.parametrize(("zone", "expected"), [("desktop", 404), ("admin", 404)])
async def test_internal_route_exists_only_in_the_gateway_zone(app_client, monkeypatch, zone, expected):
    from app.platform.config import get_settings
    from app.platform.http.exposure import EXPOSURE

    assert EXPOSURE[("POST", URL)] == frozenset({"gateway"})
    monkeypatch.setattr(get_settings(), "nc_zone", zone)
    response = await app_client.post(URL, json={"events": [_event()]})
    assert response.status_code == expected
    assert response.json() == {"detail": "Not Found"}


def test_rate_limit_is_keyed_by_the_verified_gateway_key():
    from app.platform.http.gateway_auth import GATEWAY_KEY_ID_STATE
    from app.platform.http.limiter import gateway_key_rate_limit_key

    signed = SimpleNamespace(state=SimpleNamespace(**{GATEWAY_KEY_ID_STATE: "gw-2026a"}), client=SimpleNamespace(host="10.0.0.1"))
    unsigned = SimpleNamespace(state=SimpleNamespace(), client=SimpleNamespace(host="10.0.0.2"))
    assert gateway_key_rate_limit_key(signed) == "gateway:gw-2026a"
    assert gateway_key_rate_limit_key(unsigned) == "10.0.0.2"


def test_security_surface_declares_the_contract_rate_limit():
    from app.platform.config import get_settings

    assert get_settings().rate_limit_security_events == "120/minute"
