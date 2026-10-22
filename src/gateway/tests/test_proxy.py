"""Proxy /bff/api: pořadí kontrol, CSRF/Origin, obnova tokenu, hlavičky, IP, limity, 5xx, SSE (vyžaduje Redis)."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from nc_gateway.app import GatewayApp
from nc_gateway.config import RateLimit, load_settings
from nc_gateway.store import SessionStore, sid_hash
from tests.conftest import (
    CLIENT_IP,
    PUBLIC_ORIGIN,
    SESSION_KEY_A,
    SESSION_KEY_B,
    TRUSTED_PROXY,
    USER,
    FakeCore,
    Harness,
    asgi_request,
    base_env,
    login,
    make_harness,
    origin_headers,
)


async def test_known_route_proxied_with_signed_request(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        response = await client.get("/bff/api/cases?status=open&page=2", headers=result.cookie)
    assert response.status_code == 200
    echo = response.json()
    assert echo["path"] == "/api/v1/cases"
    assert echo["rawTarget"] == "/api/v1/cases?status=open&page=2"
    assert echo["headers"]["authorization"].startswith("Bearer ")
    assert echo["headers"]["x-nc-client-ip"] == CLIENT_IP


async def test_known_route_without_session_is_401(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.get("/bff/api/cases/abc")
    assert response.status_code == 401


async def test_unknown_route_with_session_is_still_404(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        for path in ("/bff/api/admin/users", "/bff/api/auth/me", "/bff/api/internal/security-events"):
            response = await client.get(path, headers=result.cookie)
            assert response.status_code == 404
    assert harness.core.calls("GET", "/api/v1/auth/me") == []


async def test_head_with_session_is_404(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
    response = await asgi_request(
        harness.app, "HEAD", b"/bff/api/cases", headers=[("Cookie", f"__Host-nc_sid={result.sid}")]
    )
    assert response.status == 404


# ── CSRF a Origin ───────────────────────────────────────────────────────────


async def test_mutation_without_csrf_is_403_with_fixed_body(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        missing = await client.post("/bff/api/cases", json={"a": 1}, headers={**result.cookie, **origin_headers()})
        wrong = await client.post(
            "/bff/api/cases", json={"a": 1}, headers={**result.cookie, **origin_headers("x" * 43)}
        )
    for response in (missing, wrong):
        assert response.status_code == 403
        body = response.json()
        assert body["detail"] == "CSRF validation failed."
        assert body["code"] == "CSRF_FAILED"
        assert set(body) == {"detail", "code", "requestId"}
    assert harness.core.calls("POST", "/api/v1/cases") == []
    assert len([e for e in harness.app.events.pending if e["type"] == "csrf_failure"]) == 2


async def test_foreign_origin_is_403_with_fixed_body(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        foreign = await client.post(
            "/bff/api/cases", json={}, headers={**result.cookie, **origin_headers(result.csrf, "https://evil.example")}
        )
        null_origin = await client.patch(
            "/bff/api/cases/c1", json={}, headers={**result.cookie, **origin_headers(result.csrf, "null")}
        )
        no_origin_cross = await client.delete(
            "/bff/api/cases/c1/images/i1",
            headers={**result.cookie, "X-CSRF-Token": result.csrf, "Sec-Fetch-Site": "same-site"},
        )
        no_origin_no_fetch = await client.post(
            "/bff/api/cases", json={}, headers={**result.cookie, "X-CSRF-Token": result.csrf}
        )
    for response in (foreign, null_origin, no_origin_cross, no_origin_no_fetch):
        assert response.status_code == 403
        body = response.json()
        assert body == {"detail": "Origin not allowed.", "code": "ORIGIN_REJECTED", "requestId": body["requestId"]}
    assert any(e["type"] == "origin_failure" for e in harness.app.events.pending)


async def test_valid_mutation_and_sec_fetch_site_fallback(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        with_origin = await client.post("/bff/api/cases", json={"title": "x"}, headers=result.mutation())
        fallback = await client.post(
            "/bff/api/cases",
            json={"title": "y"},
            headers={**result.cookie, "X-CSRF-Token": result.csrf, "Sec-Fetch-Site": "same-origin"},
        )
        read = await client.get("/bff/api/cases", headers=result.cookie)  # GET bez CSRF
    assert with_origin.status_code == 200
    assert fallback.status_code == 200
    assert read.status_code == 200
    # CSRF token se do core neposílá
    assert "x-csrf-token" not in with_origin.json()["headers"]


async def test_csrf_check_happens_after_session_check(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.post("/bff/api/cases", json={}, headers=origin_headers())
    assert response.status_code == 401


# ── obnova tokenu a revokace ────────────────────────────────────────────────


async def test_refresh_after_core_401(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        harness.core.expire_access_tokens()  # core access token odmítne, refresh je platný
        first = await client.get("/bff/api/cases", headers=result.cookie)
        second = await client.get("/bff/api/cases", headers=result.cookie)
    assert first.status_code == 200
    assert second.status_code == 200
    assert harness.core.refresh_calls == 1
    assert len(harness.core.calls("GET", "/api/v1/cases")) == 3  # 401, opakování, další požadavek


async def test_refresh_before_expiry(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        harness.clock.advance(harness.core.access_ttl - 30)  # < 60 s do expirace
        response = await client.get("/bff/api/cases", headers=result.cookie)
    assert response.status_code == 200
    assert harness.core.refresh_calls == 1
    assert len(harness.core.calls("GET", "/api/v1/cases")) == 1  # žádný 401 navíc


async def test_no_refresh_when_token_fresh(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        harness.clock.advance(60)
        await client.get("/bff/api/cases", headers=result.cookie)
    assert harness.core.refresh_calls == 0


async def test_concurrent_refresh_uses_lock_single_refresh(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        harness.core.expire_access_tokens()
        responses = await asyncio.gather(*(client.get("/bff/api/cases", headers=result.cookie) for _ in range(4)))
    assert [r.status_code for r in responses] == [200] * 4
    # core rotuje refresh token a reuse odmítá – víc obnov by session zrušilo
    assert harness.core.refresh_calls == 1


async def test_revocation_core_rejects_access_and_refresh(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        harness.core.revoke_all()
        response = await client.get("/bff/api/cases", headers=result.cookie)
        again = await client.get("/bff/session", headers=result.cookie)
    assert response.status_code == 401
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert await harness.redis.exists(SessionStore.record_key(sid_hash(result.sid))) == 0
    assert again.json() == {"authenticated": False}
    revoked = [e for e in harness.app.events.pending if e["type"] == "session_revoked"]
    assert revoked and revoked[0]["userId"] == USER["id"]


async def test_session_endpoint_refreshes_and_detects_revocation(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        harness.core.expire_access_tokens()
        ok = await client.get("/bff/session", headers=result.cookie)
        harness.core.revoke_all()
        gone = await client.get("/bff/session", headers=result.cookie)
    assert ok.json()["authenticated"] is True
    assert gone.json() == {"authenticated": False}
    assert "Max-Age=0" in gone.headers["set-cookie"]


# ── rate limit ──────────────────────────────────────────────────────────────


async def test_session_rate_limit_429(settings, redis_client, fake_core, clock) -> None:  # type: ignore[no-untyped-def]
    h = await make_harness(dataclasses.replace(settings, rate_session=RateLimit(3, 60)), redis_client, fake_core, clock)
    try:
        async with h.client() as client:
            result = await login(client)
            statuses = [(await client.get("/bff/api/cases", headers=result.cookie)).status_code for _ in range(4)]
            limited = await client.get("/bff/api/cases", headers=result.cookie)
    finally:
        await h.app.core.aclose()
        await h.app.redis.aclose()
    assert statuses == [200, 200, 200, 429]
    assert limited.status_code == 429
    assert 0 < int(limited.headers["retry-after"]) <= 60
    assert any(e["type"] == "rate_limited" for e in h.app.events.pending)


async def test_ip_rate_limit_429(settings, redis_client, fake_core, clock) -> None:  # type: ignore[no-untyped-def]
    h = await make_harness(dataclasses.replace(settings, rate_ip=RateLimit(2, 60)), redis_client, fake_core, clock)
    try:
        async with h.client() as client:
            result = await login(client)
            statuses = [(await client.get("/bff/api/cases", headers=result.cookie)).status_code for _ in range(3)]
    finally:
        await h.app.core.aclose()
        await h.app.redis.aclose()
    assert statuses == [200, 200, 429]


# ── core nedostupný, 5xx ────────────────────────────────────────────────────


async def test_core_unavailable_returns_502(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        harness.core.down = True
        response = await client.get("/bff/api/cases", headers=result.cookie)
        session = await client.get("/bff/session", headers=result.cookie)
    assert response.status_code == 502
    assert response.json()["detail"] == "Upstream unavailable."
    assert session.status_code == 502
    # session zůstává – výpadek core není revokace
    assert await harness.redis.exists(SessionStore.record_key(sid_hash(result.sid))) == 1


async def test_core_5xx_is_masked(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        response = await client.get("/bff/api/boom", headers=result.cookie)
    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "Upstream error.", "requestId": body["requestId"]}
    assert "Traceback" not in response.text
    assert "set-cookie" not in response.headers
    assert "x-internal-debug" not in response.headers


async def test_core_503_keeps_status_and_retry_after(harness: Harness) -> None:
    harness.core.overrides[("GET", "/api/v1/cases")] = lambda r: httpx.Response(
        503, text="db down at 10.0.0.5", headers={"Retry-After": "7"}
    )
    async with harness.client() as client:
        result = await login(client)
        response = await client.get("/bff/api/cases", headers=result.cookie)
    assert response.status_code == 503
    assert response.json()["detail"] == "Upstream error."
    assert response.headers["retry-after"] == "7"
    assert "10.0.0.5" not in response.text


async def test_core_4xx_passes_through(harness: Harness) -> None:
    harness.core.overrides[("GET", "/api/v1/cases/missing")] = lambda r: httpx.Response(
        404, json={"detail": "Case not found."}
    )
    async with harness.client() as client:
        result = await login(client)
        response = await client.get("/bff/api/cases/missing", headers=result.cookie)
    assert response.status_code == 404
    assert response.json() == {"detail": "Case not found."}


# ── hlavičky ────────────────────────────────────────────────────────────────


async def test_request_headers_from_browser_are_stripped(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        response = await client.get(
            "/bff/api/cases",
            headers={
                "Cookie": f"__Host-nc_sid={result.sid}; other=1",
                "Authorization": "Bearer attacker-token",
                "X-Forwarded-For": "6.6.6.6",
                "X-Real-IP": "6.6.6.6",
                "Forwarded": "for=6.6.6.6",
                "X-NC-Client-IP": "6.6.6.6",
                "X-NC-Gateway-Sig": "0" * 64,
                "X-NC-Gateway-Key": "evil",
                "X-Request-Id": "attacker-rid",
                "User-Agent": "evil-agent",
                "X-CSRF-Token": result.csrf,
                "Accept": "application/json",
                "If-None-Match": '"v0"',
                "Range": "bytes=0-10",
            },
        )
    seen = response.json()["headers"]
    assert "cookie" not in seen
    assert seen["authorization"] != "Bearer attacker-token"
    assert seen["authorization"].startswith("Bearer ")
    for name in ("x-forwarded-for", "x-real-ip", "forwarded", "user-agent", "x-csrf-token"):
        assert name not in seen, name
    assert seen["x-nc-client-ip"] == CLIENT_IP
    assert seen["x-nc-gateway-key"] != "evil"
    assert seen["x-request-id"] != "attacker-rid"
    assert seen["accept"] == "application/json"
    assert seen["if-none-match"] == '"v0"'
    assert seen["range"] == "bytes=0-10"
    assert seen["accept-encoding"] == "identity"


async def test_response_headers_from_core_are_filtered(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        response = await client.get("/bff/api/cases", headers=result.cookie)
    assert "set-cookie" not in response.headers
    assert "x-internal-debug" not in response.headers
    assert "x-nc-gateway-sig" not in response.headers
    assert "access-control-allow-origin" not in response.headers
    assert response.headers.get("server") is None
    assert response.headers["etag"] == '"v1"'
    assert response.headers["cache-control"] == "private, max-age=0"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-request-id"]


# ── klientská IP ────────────────────────────────────────────────────────────


async def test_ip_spoofing_via_xff_from_untrusted_source_is_ignored(harness: Harness) -> None:
    async with harness.client(ip="198.51.100.77") as client:
        result = await login(client, headers={"X-Forwarded-For": "1.2.3.4"})
        response = await client.get("/bff/api/cases", headers={**result.cookie, "X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    assert response.json()["headers"]["x-nc-client-ip"] == "198.51.100.77"
    (login_call,) = harness.core.calls("POST", "/api/v1/auth/login")
    assert login_call.headers["x-nc-client-ip"] == "198.51.100.77"


async def test_trusted_proxy_last_xff_value_is_used(harness: Harness) -> None:
    async with harness.client(ip=TRUSTED_PROXY) as client:
        result = await login(client, headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.9"})
        response = await client.get(
            "/bff/api/cases", headers={**result.cookie, "X-Forwarded-For": "6.6.6.6, 203.0.113.9"}
        )
    assert response.json()["headers"]["x-nc-client-ip"] == "203.0.113.9"


async def test_trusted_proxy_with_invalid_xff_falls_back_to_peer(harness: Harness) -> None:
    async with harness.client(ip=TRUSTED_PROXY) as client:
        result = await login(client)
        response = await client.get("/bff/api/cases", headers={**result.cookie, "X-Forwarded-For": "garbage"})
    assert response.json()["headers"]["x-nc-client-ip"] == TRUSTED_PROXY


async def test_ipv4_mapped_peer_is_canonicalized(harness: Harness) -> None:
    async with harness.client(ip="::ffff:198.51.100.20") as client:
        result = await login(client)
        response = await client.get("/bff/api/cases", headers=result.cookie)
    assert response.json()["headers"]["x-nc-client-ip"] == "198.51.100.20"


# ── tělo a Content-Type ─────────────────────────────────────────────────────


async def test_json_body_over_limit_is_413(harness: Harness) -> None:
    payload = json.dumps({"x": "a" * (256 * 1024)})
    async with harness.client() as client:
        result = await login(client)
        response = await client.post(
            "/bff/api/cases", content=payload, headers={**result.mutation(), "Content-Type": "application/json"}
        )
    assert response.status_code == 413
    assert harness.core.calls("POST", "/api/v1/cases") == []


async def test_body_limit_checked_before_session(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.post(
            "/bff/api/cases", content=b"{" + b" " * (300 * 1024) + b"}", headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 413


async def test_chunked_body_over_limit_is_413(harness: Harness) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(300):
            yield b" " * 1024

    async with harness.client() as client:
        response = await client.post("/bff/api/cases", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


async def test_multipart_upload_allowed_on_upload_route_only(harness: Harness) -> None:
    files = {"file": ("foto.jpg", b"\xff\xd8" + b"x" * (1024 * 1024), "image/jpeg")}
    async with harness.client() as client:
        result = await login(client)
        upload = await client.post("/bff/api/cases/c1/images", files=files, headers=result.mutation())
        not_upload = await client.post("/bff/api/cases", files=files, headers=result.mutation())
    assert upload.status_code == 200
    assert upload.json()["headers"]["content-type"].startswith("multipart/form-data; boundary=")
    assert upload.json()["bodyLength"] > 1024 * 1024
    # multipart nad JSON limitem mimo upload routu = 413, pod limitem = 415
    assert not_upload.status_code == 413
    small = {"file": ("a.txt", b"abc", "text/plain")}
    async with harness.client() as client:
        small_resp = await client.post("/bff/api/cases", files=small, headers=result.mutation())
    assert small_resp.status_code == 415


@pytest.mark.parametrize(
    "content_type", ["text/plain", "application/x-www-form-urlencoded", "application/xml", "text/json"]
)
async def test_other_content_types_are_415(harness: Harness, content_type: str) -> None:
    async with harness.client() as client:
        result = await login(client)
        response = await client.post(
            "/bff/api/cases", content=b"a=1", headers={**result.mutation(), "Content-Type": content_type}
        )
    assert response.status_code == 415


async def test_content_type_checked_before_session(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.post("/bff/api/cases", content=b"a=1", headers={"Content-Type": "text/plain"})
    assert response.status_code == 415


# ── šifrování a rotace klíčů ────────────────────────────────────────────────


async def test_redis_contains_no_plaintext_tokens(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
    raw = await harness.redis.get(SessionStore.record_key(sid_hash(result.sid)))
    assert raw is not None
    text = raw.decode()
    assert text.startswith("v1.k1.")
    for secret in [*harness.core.access_tokens, *harness.core.refresh_tokens, result.csrf, USER["id"], "eyJ"]:
        assert secret not in text
    # sid samotné se v Redisu neobjevuje (klíč je sha256)
    keys = [k.decode() for k in await harness.redis.keys("*")]
    assert not any(result.sid in k for k in keys)


async def test_record_cannot_be_moved_to_another_sid(harness: Harness) -> None:
    """AAD = klíč záznamu: zkopírovaný šifrovaný záznam pod jiným sid nejde dešifrovat."""
    async with harness.client() as client:
        result = await login(client)
        other_sid = "Z" * 43
        raw = await harness.redis.get(SessionStore.record_key(sid_hash(result.sid)))
        await harness.redis.set(SessionStore.record_key(sid_hash(other_sid)), raw)
        response = await client.get("/bff/session", headers={"Cookie": f"__Host-nc_sid={other_sid}"})
    assert response.json() == {"authenticated": False}


async def test_key_rotation_old_key_still_decrypts(allowlist_file, redis_client, fake_core: FakeCore, clock) -> None:  # type: ignore[no-untyped-def]
    old_settings = load_settings(base_env(allowlist_file))
    old = await make_harness(old_settings, redis_client, fake_core, clock)
    async with old.client() as client:
        result = await login(client)
    await old.app.core.aclose()
    await old.app.redis.aclose()

    rotated_settings = load_settings(
        base_env(allowlist_file, NC_BFF_SESSION_KEYS=f"k2:{SESSION_KEY_B},k1:{SESSION_KEY_A}")
    )
    rotated = await make_harness(rotated_settings, redis_client, fake_core, clock)
    try:
        async with rotated.client() as client:
            response = await client.get("/bff/session", headers=result.cookie)
        assert response.json()["authenticated"] is True
        raw = await redis_client.get(SessionStore.record_key(sid_hash(result.sid)))
        assert raw.decode().startswith("v1.k2.")  # přešifrováno novým klíčem
    finally:
        await rotated.app.core.aclose()
        await rotated.app.redis.aclose()

    # starý klíč odebrán úplně → záznam zašifrovaný jen k1 už nejde přečíst
    only_new = load_settings(base_env(allowlist_file, NC_BFF_SESSION_KEYS=f"k3:{base64.b64encode(b'C' * 32).decode()}"))
    h3 = await make_harness(only_new, redis_client, fake_core, clock)
    try:
        async with h3.client() as client:
            gone = await client.get("/bff/session", headers=result.cookie)
        assert gone.json() == {"authenticated": False}
    finally:
        await h3.app.core.aclose()
        await h3.app.redis.aclose()


# ── bezpečnostní události ───────────────────────────────────────────────────


async def test_security_events_are_batched_to_core_without_authorization(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        await client.post("/bff/api/cases", json={}, headers={**result.cookie, **origin_headers()})  # csrf_failure
        await client.get("/bff/api/admin/users", headers=result.cookie)  # allowlist_miss
    sent = await harness.app.events.flush()
    assert sent == 3
    types = [e["type"] for e in harness.core.events]
    assert types == ["login_success", "csrf_failure", "allowlist_miss"]
    (call,) = harness.core.calls("POST", "/api/v1/internal/security-events")
    assert "authorization" not in call.headers
    event = harness.core.events[0]
    assert event["userId"] == USER["id"]
    assert event["organizationId"] == USER["organizationId"]
    assert event["sessionRef"] == sid_hash(result.sid)[:16]
    assert event["clientIp"] == CLIENT_IP
    assert set(event) == {
        "type",
        "occurredAt",
        "clientIp",
        "userId",
        "organizationId",
        "sessionRef",
        "requestId",
        "detail",
    }


async def test_security_event_delivery_failure_does_not_block_user(harness: Harness) -> None:
    harness.core.overrides[("POST", "/api/v1/internal/security-events")] = lambda r: httpx.Response(500)
    async with harness.client() as client:
        result = await login(client)
        assert await harness.app.events.flush() == 0
        harness.core.down = True
        assert await harness.app.events.flush() == 0
        harness.core.down = False
        response = await client.get("/bff/api/cases", headers=result.cookie)
    assert response.status_code == 200
    assert harness.app.events.failed_batches == 2
    # dávka se po přechodné chybě neztratila – po obnovení core se doručí
    del harness.core.overrides[("POST", "/api/v1/internal/security-events")]
    assert await harness.app.events.flush() >= 1
    assert next(e["type"] for e in harness.core.events) == "login_success"


async def test_security_events_batch_max_50(harness: Harness) -> None:
    for _ in range(120):
        harness.app.events.emit("allowlist_miss", client_ip=CLIENT_IP, detail={"path": "/x"})
    assert await harness.app.events.flush() == 120
    sizes = [
        len(json.loads(c.content)["events"]) for c in harness.core.calls("POST", "/api/v1/internal/security-events")
    ]
    assert sizes == [50, 50, 20]


# ── streamování a SSE ───────────────────────────────────────────────────────


async def test_sse_chunks_are_streamed_without_buffering(harness: Harness) -> None:
    harness.app.allowlist = type(harness.app.allowlist)(
        [("GET", "/api/v1/cases/{case_id}/activity/stream"), ("GET", "/api/v1/cases")]
    )
    first_delivered = asyncio.Event()
    seen_timeouts: list[Any] = []

    def sse(request: httpx.Request) -> httpx.Response:
        seen_timeouts.append(request.extensions.get("timeout"))

        async def events() -> AsyncIterator[bytes]:
            yield b'event: activity\ndata: {"n":1}\n\n'
            # druhý blok core pošle až poté, co klient dostal první – při bufferování deadlock
            await asyncio.wait_for(first_delivered.wait(), timeout=5)
            yield b'event: activity\ndata: {"n":2}\n\n'

        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=events())

    harness.core.overrides[("GET", "/api/v1/cases/c1/activity/stream")] = sse
    async with harness.client() as client:
        result = await login(client)

    chunks: list[bytes] = []
    start: dict[str, Any] = {}

    requested = False

    async def receive() -> dict[str, Any]:
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(10)  # klient drží spojení otevřené
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            start.update(message)
        elif message.get("body"):
            chunks.append(message["body"])
            first_delivered.set()

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/bff/api/cases/c1/activity/stream",
        "raw_path": b"/bff/api/cases/c1/activity/stream",
        "query_string": b"",
        "headers": [(b"cookie", f"__Host-nc_sid={result.sid}".encode()), (b"accept", b"text/event-stream")],
        "client": (CLIENT_IP, 4000),
    }
    await asyncio.wait_for(harness.app(scope, receive, send), timeout=10)
    assert start["status"] == 200
    assert (b"content-type", b"text/event-stream") in start["headers"]
    assert (b"x-accel-buffering", b"no") in start["headers"]
    assert len(chunks) == 2, chunks  # dva samostatné bloky, ne jeden sloučený
    assert b'"n":1' in chunks[0] and b'"n":2' in chunks[1]
    assert seen_timeouts[0]["read"] == harness.settings.sse_idle_timeout_seconds == 300.0


async def test_regular_requests_keep_short_read_timeout(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        await client.get("/bff/api/cases", headers=result.cookie)
    (call,) = harness.core.calls("GET", "/api/v1/cases")
    assert "timeout" not in call.extensions or call.extensions["timeout"]["read"] != 300.0


async def test_gateway_app_has_no_jwt_secret(harness: Harness) -> None:
    assert not any("jwt" in f.name.lower() for f in dataclasses.fields(harness.settings))
    assert isinstance(harness.app, GatewayApp)
    assert harness.settings.public_origin == PUBLIC_ORIGIN
