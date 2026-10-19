"""F3.4: the gateway zone accepts only requests signed by the gateway.

Contract: docs/security/GATEWAY_CORE_CONTRACT.md. The zone is process
configuration (``nc_zone``); nothing in a request selects it. Mechanics are
tested on a small echo app with the real middleware; the integration tests at
the end run through the real application.
"""

from __future__ import annotations

import secrets
import time

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.platform.config import get_settings
from app.platform.http.gateway_auth import (
    GatewayKeyConfigError,
    GatewaySignatureMiddleware,
    canonical_string,
    parse_gateway_keys,
    sign_request,
)
from tests.conftest import TEST_GATEWAY_KEY_ID, TEST_GATEWAY_SECRET, UNSIGNED_MARKER

SECRET = TEST_GATEWAY_SECRET.encode()
CLIENT_IP = "198.51.100.23"


@pytest.fixture
def gateway_zone(monkeypatch):
    monkeypatch.setattr(get_settings(), "nc_zone", "gateway")


def _echo_app() -> FastAPI:
    app = FastAPI()

    @app.api_route("/api/v1/echo", methods=["GET", "POST"])
    async def echo(request: Request) -> dict:
        return {
            "client": request.client.host if request.client else None,
            "body": (await request.body()).decode(),
            "headers": sorted(k for k in request.headers.keys() if k.startswith(("x-nc", "x-forwarded", "x-real"))),
        }

    app.add_middleware(GatewaySignatureMiddleware)
    return app


def _signed(method: str, path: str, *, query: str = "", body: bytes = b"", authorization: str | None = None,
            client_ip: str = CLIENT_IP, key_id: str = TEST_GATEWAY_KEY_ID, secret: bytes = SECRET,
            timestamp: int | None = None, nonce: str | None = None) -> dict[str, str]:
    headers = sign_request(
        key_id=key_id,
        secret=secret,
        method=method,
        raw_path=path,
        query_string=query,
        client_ip=client_ip,
        body=body,
        authorization=authorization,
        timestamp=timestamp,
        nonce=nonce or secrets.token_urlsafe(24),
    )
    if authorization:
        headers["Authorization"] = authorization
    return headers


async def _call(app, method: str, url: str, headers: dict[str, str], content: bytes = b""):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://core") as client:
        return await client.request(method, url, headers={UNSIGNED_MARKER: "1", **headers}, content=content)


# ── Mechanics ─────────────────────────────────────────────────────────────────


async def test_valid_signature_passes_and_sets_the_signed_client_address(gateway_zone):
    body = b'{"x": 1}'
    headers = _signed("POST", "/api/v1/echo", query="a=1&b=2", body=body, authorization="Bearer tok")
    headers["X-Forwarded-For"] = "6.6.6.6"
    headers["X-Real-IP"] = "6.6.6.6"
    response = await _call(_echo_app(), "POST", "/api/v1/echo?a=1&b=2", headers, body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["client"] == CLIENT_IP
    assert data["body"] == '{"x": 1}'
    # Neither the contract headers nor any forwarding header reach the application.
    assert data["headers"] == []


async def test_unsigned_request_is_rejected_with_401(gateway_zone):
    response = await _call(_echo_app(), "GET", "/api/v1/echo", {})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid gateway signature."}


async def test_spoofed_client_ip_without_signature_is_rejected(gateway_zone):
    response = await _call(_echo_app(), "GET", "/api/v1/echo", {"X-NC-Client-IP": "10.0.0.1"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "tamper",
    ["method", "path", "query", "body", "client_ip", "authorization", "timestamp", "key_secret"],
)
async def test_any_change_after_signing_invalidates_the_signature(gateway_zone, tamper):
    body = b'{"amount": 1}'
    headers = _signed("POST", "/api/v1/echo", query="q=1", body=body, authorization="Bearer original")
    method, url, content = "POST", "/api/v1/echo?q=1", body
    if tamper == "method":
        method, content = "GET", b""
        headers = {**_signed("POST", "/api/v1/echo", query="q=1"), "Authorization": "Bearer original"}
    elif tamper == "path":
        url = "/api/v1/echo/?q=1"
    elif tamper == "query":
        url = "/api/v1/echo?q=2"
    elif tamper == "body":
        content = b'{"amount": 9}'
    elif tamper == "client_ip":
        headers["X-NC-Client-IP"] = "198.51.100.99"
    elif tamper == "authorization":
        headers["Authorization"] = "Bearer swapped"
    elif tamper == "timestamp":
        headers["X-NC-Gateway-Ts"] = str(int(headers["X-NC-Gateway-Ts"]) + 1)
    elif tamper == "key_secret":
        headers = _signed("POST", "/api/v1/echo", query="q=1", body=body, authorization="Bearer original",
                          secret=b"x" * 64)
    response = await _call(_echo_app(), method, url, headers, content)
    assert response.status_code == 401, (tamper, response.text)


async def test_replayed_nonce_is_rejected(gateway_zone):
    app = _echo_app()
    headers = _signed("GET", "/api/v1/echo", nonce="replay-nonce-0123456789")
    assert (await _call(app, "GET", "/api/v1/echo", headers)).status_code == 200
    assert (await _call(app, "GET", "/api/v1/echo", headers)).status_code == 401


async def test_invalid_signature_does_not_consume_the_nonce(gateway_zone):
    app = _echo_app()
    nonce = "unconsumed-nonce-0123456789"
    forged = _signed("GET", "/api/v1/echo", nonce=nonce, secret=b"y" * 64)
    assert (await _call(app, "GET", "/api/v1/echo", forged)).status_code == 401
    genuine = _signed("GET", "/api/v1/echo", nonce=nonce)
    assert (await _call(app, "GET", "/api/v1/echo", genuine)).status_code == 200


@pytest.mark.parametrize("offset", [-31, 31, -3600])
async def test_timestamps_outside_the_window_are_rejected(gateway_zone, offset):
    headers = _signed("GET", "/api/v1/echo", timestamp=int(time.time()) + offset)
    assert (await _call(_echo_app(), "GET", "/api/v1/echo", headers)).status_code == 401


@pytest.mark.parametrize(
    "mutate",
    [
        lambda h: h.update({"X-NC-Gateway-Key": "unknown-key"}),
        lambda h: h.update({"X-NC-Gateway-Nonce": "short"}),
        lambda h: h.update({"X-NC-Gateway-Sig": "ZZ" * 32}),
        lambda h: h.update({"X-NC-Gateway-Ts": "12e3"}),
        lambda h: h.update({"X-NC-Client-IP": "not-an-ip"}),
        lambda h: h.pop("X-NC-Gateway-Nonce"),
    ],
)
async def test_malformed_contract_headers_are_rejected(gateway_zone, mutate):
    headers = _signed("GET", "/api/v1/echo")
    mutate(headers)
    assert (await _call(_echo_app(), "GET", "/api/v1/echo", headers)).status_code == 401


async def test_non_canonical_client_address_is_rejected(gateway_zone):
    # "198.051..." or an IPv4-mapped IPv6 address would be a second spelling of one address.
    headers = _signed("GET", "/api/v1/echo", client_ip="::ffff:198.51.100.23")
    assert (await _call(_echo_app(), "GET", "/api/v1/echo", headers)).status_code == 401


async def test_duplicate_contract_header_is_rejected(gateway_zone):
    signed = _signed("GET", "/api/v1/echo")
    async with AsyncClient(transport=ASGITransport(app=_echo_app()), base_url="http://core") as client:
        headers = [(k, v) for k, v in signed.items()] + [("X-NC-Client-IP", "198.51.100.77")]
        response = await client.get("/api/v1/echo", headers=headers)
    assert response.status_code == 401


async def test_key_rotation_accepts_every_configured_key(gateway_zone, monkeypatch):
    old, new = "a" * 64, "b" * 64
    monkeypatch.setattr(get_settings(), "nc_gateway_hmac_keys", f"gw-2026a:{old},gw-2026b:{new}")
    app = _echo_app()
    for key_id, secret in (("gw-2026a", old), ("gw-2026b", new)):
        headers = _signed("GET", "/api/v1/echo", key_id=key_id, secret=secret.encode())
        assert (await _call(app, "GET", "/api/v1/echo", headers)).status_code == 200
    # The retired key stops working as soon as it is removed from the configuration.
    monkeypatch.setattr(get_settings(), "nc_gateway_hmac_keys", f"gw-2026b:{new}")
    headers = _signed("GET", "/api/v1/echo", key_id="gw-2026a", secret=old.encode())
    assert (await _call(app, "GET", "/api/v1/echo", headers)).status_code == 401


async def test_oversized_body_is_refused_before_the_application(gateway_zone, monkeypatch):
    monkeypatch.setattr(get_settings(), "nc_gateway_max_body_bytes", 1024)
    body = b"x" * 2048
    headers = _signed("POST", "/api/v1/echo", body=body)
    assert (await _call(_echo_app(), "POST", "/api/v1/echo", headers, body)).status_code == 413


async def test_strict_environment_without_shared_nonce_store_fails_closed(gateway_zone, monkeypatch):
    # Outside development a per-process nonce cache would let a replay hit another worker.
    monkeypatch.setattr(get_settings(), "app_env", "production")
    headers = _signed("GET", "/api/v1/echo")
    assert (await _call(_echo_app(), "GET", "/api/v1/echo", headers)).status_code == 503


@pytest.mark.parametrize("zone", ["desktop", "admin", "dev"])
async def test_other_zones_drop_gateway_headers(monkeypatch, zone):
    monkeypatch.setattr(get_settings(), "nc_zone", zone)
    headers = {"X-NC-Client-IP": "10.9.9.9", "X-NC-Gateway-Sig": "0" * 64, "X-NC-Gateway-Key": "k"}
    response = await _call(_echo_app(), "GET", "/api/v1/echo", headers)
    assert response.status_code == 200
    assert response.json()["client"] != "10.9.9.9"
    assert response.json()["headers"] == []


# ── Contract and configuration ────────────────────────────────────────────────

# Published in docs/security/GATEWAY_CORE_CONTRACT.md for the gateway implementation.
VECTOR = {
    "key_id": "gw-test",
    "secret": b"0123456789abcdef0123456789abcdef",
    "timestamp": 1792224000,
    "nonce": "AAAAAAAAAAAAAAAAAAAAAAAA",
    "method": "POST",
    "raw_path": "/api/v1/org/users",
    "query_string": "",
    "client_ip": "203.0.113.10",
    "body": b'{"email":"novak@firma.cz"}',
    "authorization": "Bearer eyJ.test.token",
}
VECTOR_SIGNATURE = "834a1b955a9ac25a806c4c77dc4eeda33381fa89c2633ca6d9791251d80ef91f"


def test_signature_matches_the_published_test_vector():
    headers = sign_request(
        key_id=VECTOR["key_id"],
        secret=VECTOR["secret"],
        method=VECTOR["method"],
        raw_path=VECTOR["raw_path"],
        query_string=VECTOR["query_string"],
        client_ip=VECTOR["client_ip"],
        body=VECTOR["body"],
        authorization=VECTOR["authorization"],
        timestamp=VECTOR["timestamp"],
        nonce=VECTOR["nonce"],
    )
    assert headers["X-NC-Gateway-Sig"] == VECTOR_SIGNATURE


def test_canonical_string_has_one_field_per_line_in_contract_order():
    text = canonical_string(
        key_id="k", timestamp="1", nonce="n", method="get", raw_path="/p", query_string="q=1",
        client_ip="1.2.3.4", body_sha256="b", authorization_sha256="a",
    ).decode()
    assert text.split("\n") == ["NC-GW-1", "k", "1", "n", "GET", "/p", "q=1", "1.2.3.4", "b", "a"]


@pytest.mark.parametrize(
    "raw",
    ["nokey", "k:short", "bad id!:" + "s" * 40, "k:" + "s" * 40 + ",k:" + "t" * 40],
)
def test_malformed_key_configuration_is_rejected(raw):
    with pytest.raises(GatewayKeyConfigError):
        parse_gateway_keys(raw)


def test_gateway_zone_outside_development_requires_keys():
    settings = get_settings().model_copy(
        update={"app_env": "production", "nc_zone": "gateway", "nc_gateway_hmac_keys": ""}
    )
    with pytest.raises(ValueError, match="NC_GATEWAY_HMAC_KEYS"):
        settings._check_network_zone()


def test_malformed_keys_fail_settings_validation():
    settings = get_settings().model_copy(update={"nc_gateway_hmac_keys": "k:short"})
    with pytest.raises(ValueError, match="shorter than"):
        settings._check_network_zone()


# ── Integration through the real application ─────────────────────────────────


async def test_real_app_answers_401_not_404_to_unsigned_requests(app_client, gateway_zone):
    for path in ("/api/v1/auth/me", "/api/v1/admin/users", "/api/v1/does-not-exist"):
        response = await app_client.get(path, headers={UNSIGNED_MARKER: "1"})
        assert response.status_code == 401, path


async def test_real_app_signed_request_still_meets_the_exposure_guard(app_client, gateway_zone):
    # Signed by the gateway, but the admin API is not in the gateway zone.
    assert (await app_client.get("/api/v1/admin/users")).status_code == 404
    assert (await app_client.get("/api/v1/does-not-exist")).status_code == 404


async def test_real_app_login_through_the_signed_gateway_ignores_forwarded_for(app_client, gateway_zone):
    response = await app_client.post(
        "/api/v1/auth/login",
        json={"email": "manager_a@test.local", "password": "TestPassA1!"},
        headers={"X-Forwarded-For": "6.6.6.6"},
    )
    assert response.status_code == 200, response.text
    token = response.json()["accessToken"]
    me = await app_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


# ── Shared nonce store (Redis) ───────────────────────────────────────────────


async def test_redis_nonce_store_claims_each_nonce_once():
    import os

    import redis.asyncio as aioredis

    from app.platform.http.gateway_auth import RedisNonceStore

    url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    client = aioredis.from_url(url, socket_connect_timeout=0.5)
    try:
        await client.ping()
    except Exception:
        pytest.skip("no Redis reachable (REDIS_URL)")
    try:
        store = RedisNonceStore(client)
        key = f"test-gw:{secrets.token_urlsafe(16)}"
        assert await store.claim(key, ttl_seconds=10) is True
        assert await store.claim(key, ttl_seconds=10) is False
        assert 0 < await client.ttl(f"nc:gw:nonce:{key}") <= 10
    finally:
        await client.aclose()


async def test_redis_nonce_store_failure_fails_closed():
    from app.platform.http.gateway_auth import NonceStoreUnavailableError, RedisNonceStore

    class Broken:
        async def set(self, *args, **kwargs):
            raise ConnectionError("redis down")

    with pytest.raises(NonceStoreUnavailableError):
        await RedisNonceStore(Broken()).claim("k", ttl_seconds=10)
