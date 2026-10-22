"""Opravy po Security Review / QA (M1, M2, F-1, F-3, L1, L4, L5, L6, L8)."""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import tracemalloc
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from nc_gateway.allowlist import Allowlist
from nc_gateway.app import GatewayApp
from nc_gateway.body import read_request_body
from nc_gateway.config import RateLimit
from nc_gateway.core_client import CoreClient
from nc_gateway.events import SecurityEvents
from nc_gateway.store import LOCK_PREFIX, SessionStore, sid_hash
from tests.conftest import (
    CLIENT_IP,
    HMAC_KID,
    HMAC_SECRET,
    PASSWORD,
    TEST_ALLOWLIST,
    USER,
    FakeClock,
    FakeCore,
    Harness,
    asgi_request,
    contract_signature,
    login,
    make_harness,
    origin_headers,
)

# ── M1: zesílení neautentizovaného provozu do auditu ───────────────────────


async def test_unauthenticated_miss_flood_is_rate_limited_and_aggregated(  # type: ignore[no-untyped-def]
    settings, redis_client, fake_core, clock
) -> None:
    h = await make_harness(dataclasses.replace(settings, rate_ip=RateLimit(20, 60)), redis_client, fake_core, clock)
    try:
        statuses = []
        for i in range(100):
            response = await asgi_request(h.app, "GET", f"/bff/api/unknown-{i}".encode())
            statuses.append(response.status)
    finally:
        await h.app.core.aclose()
        await h.app.redis.aclose()
    assert statuses[:20] == [404] * 20
    assert set(statuses[20:]) == {429}
    types = [e["type"] for e in h.app.events.pending]
    assert types.count("allowlist_miss") == 1
    assert types.count("rate_limited") == 1
    assert fake_core.requests == []


async def test_aggregated_event_reports_previous_window_count(harness: Harness) -> None:
    for _ in range(5):
        await asgi_request(harness.app, "GET", b"/bff/api/nope")
    harness.clock.advance(10)
    await asgi_request(harness.app, "GET", b"/bff/api/nope")
    misses = [e for e in harness.app.events.pending if e["type"] == "allowlist_miss"]
    assert len(misses) == 2
    assert misses[0]["detail"]["previousWindowCount"] == 0
    assert misses[1]["detail"]["previousWindowCount"] == 5


def _events(max_queue: int, handler: Any = None) -> SecurityEvents:
    from nc_gateway.config import Settings

    settings = Settings(
        env="test",
        public_origin="https://x.test",
        core_url="http://core.test",
        core_uds=None,
        hmac_key_id=HMAC_KID,
        hmac_secret=HMAC_SECRET.encode(),
        session_keys=(("k", b"k" * 32),),
        redis_url="redis://unused",
        allowlist_path=Path("unused"),
    )
    transport = httpx.MockTransport(handler or (lambda r: httpx.Response(202, json={"accepted": 1})))
    return SecurityEvents(CoreClient(settings, transport), clock=FakeClock(), max_queue=max_queue)


async def test_full_queue_drops_only_low_priority_events() -> None:
    events = _events(max_queue=5)
    for _ in range(5):
        events.emit("allowlist_miss", client_ip=CLIENT_IP)
    events.emit("login_failure", client_ip=CLIENT_IP)
    events.emit("csrf_failure", client_ip=CLIENT_IP)
    events.emit("rate_limited", client_ip=CLIENT_IP)  # fronta plná → nízká priorita se zahodí
    types = [e["type"] for e in events.pending]
    assert len(types) == 5
    assert "login_failure" in types and "csrf_failure" in types
    assert types.count("allowlist_miss") == 3
    assert "rate_limited" not in types
    for kind in ("session_expired", "logout", "origin_failure"):
        events.emit(kind, client_ip=CLIENT_IP)
    types = [e["type"] for e in events.pending]
    assert types == ["login_failure", "csrf_failure", "session_expired", "logout", "origin_failure"]
    assert events.dropped_high_priority == 0


async def test_core_429_backs_off_and_low_priority_is_not_retried_forever() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "30"})

    now = [1000.0]
    events = _events(max_queue=100, handler=handler)
    events._monotonic = lambda: now[0]
    events.emit("allowlist_miss", client_ip=CLIENT_IP)
    events.emit("login_failure", client_ip=CLIENT_IP)
    assert await events.flush() == 0
    assert await events.flush() == 0  # odklad podle Retry-After – core se znovu nevolá
    assert len(calls) == 1
    for _ in range(3):
        now[0] += 31
        await events.flush()
    # nízkoprioritní událost po 3 neúspěších zahozena, prioritní zůstává
    assert [e["type"] for e in events.pending] == ["login_failure"]


# ── M2: tělo až po session/CSRF, upload mimo paměť ─────────────────────────


async def test_upload_without_session_is_401_without_reading_body(harness: Harness) -> None:
    read_calls = 0

    async def receive() -> dict[str, Any]:
        nonlocal read_calls
        read_calls += 1
        raise AssertionError("tělo se nesmí číst před kontrolou session")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/bff/api/cases/c1/images",
        "raw_path": b"/bff/api/cases/c1/images",
        "query_string": b"",
        "headers": [
            (b"content-type", b"multipart/form-data; boundary=x"),
            (b"content-length", str(20 * 1024 * 1024).encode()),
            (b"origin", b"https://nc.example.test"),
        ],
        "client": (CLIENT_IP, 4000),
    }
    messages: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await harness.app(scope, receive, send)
    assert messages[0]["status"] == 401
    assert read_calls == 0


async def test_upload_with_bad_csrf_is_403_without_reading_body(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)

    async def receive() -> dict[str, Any]:
        raise AssertionError("tělo se nesmí číst před kontrolou CSRF")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/bff/api/cases/c1/images",
        "raw_path": b"/bff/api/cases/c1/images",
        "query_string": b"",
        "headers": [
            (b"cookie", f"__Host-nc_sid={result.sid}".encode()),
            (b"content-type", b"multipart/form-data; boundary=x"),
            (b"content-length", str(10 * 1024 * 1024).encode()),
            (b"origin", b"https://nc.example.test"),
            (b"x-csrf-token", b"wrong"),
        ],
        "client": (CLIENT_IP, 4000),
    }
    messages: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await harness.app(scope, receive, send)
    assert messages[0]["status"] == 403


async def test_declared_upload_over_25_mib_is_413_without_reading(harness: Harness) -> None:
    async def receive() -> dict[str, Any]:
        raise AssertionError("nečíst")

    response_messages: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        response_messages.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/bff/api/cases/c1/images",
        "raw_path": b"/bff/api/cases/c1/images",
        "query_string": b"",
        "headers": [
            (b"content-type", b"multipart/form-data; boundary=x"),
            (b"content-length", str(25 * 1024 * 1024 + 1).encode()),
        ],
        "client": (CLIENT_IP, 4000),
    }
    await harness.app(scope, receive, send)
    assert response_messages[0]["status"] == 413


async def test_request_body_spools_to_disk_and_hashes_incrementally() -> None:
    chunk = b"x" * 65536
    total = 48  # 3 MiB

    def messages() -> AsyncIterator[dict[str, Any]]:
        async def gen() -> AsyncIterator[dict[str, Any]]:
            for i in range(total):
                yield {"type": "http.request", "body": chunk, "more_body": i < total - 1}

        return gen()

    stream = messages()

    async def receive() -> dict[str, Any]:
        return await stream.__anext__()

    body = await read_request_body(receive, 25 * 1024 * 1024)
    try:
        assert body.on_disk  # nad 1 MiB už ne v paměti
        assert body.length == total * len(chunk)
        assert body.sha256 == hashlib.sha256(chunk * total).hexdigest()
        sizes = [len(c) async for c in body.chunks()]
        assert max(sizes) <= 64 * 1024 and sum(sizes) == body.length
        assert sum([len(c) async for c in body.chunks()]) == body.length  # opakovatelné (retry po 401)
    finally:
        body.close()

    small_stream = iter([{"type": "http.request", "body": b'{"a":1}', "more_body": False}])

    async def receive_small() -> dict[str, Any]:
        return next(small_stream)

    small = await read_request_body(receive_small, 1024)
    assert not small.on_disk and small.length == 7
    small.close()


class _StreamingCore(httpx.AsyncBaseTransport):
    """Core, které tělo jen průběžně hashuje (nedrží ho) a ověří podpis podle kontraktu."""

    def __init__(self, core: FakeCore) -> None:
        self.core = core
        self.upload_sizes: list[int] = []
        self.signature_ok: list[bool] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/v1/cases/c1/images":
            await request.aread()
            return await httpx.MockTransport(self.core.handler).handle_async_request(request)
        digest = hashlib.sha256()
        size = 0
        assert isinstance(request.stream, httpx.AsyncByteStream)
        async for part in request.stream:
            digest.update(part)
            size += len(part)
        path, _, query = request.url.raw_path.decode().partition("?")
        expected = contract_signature(
            HMAC_SECRET.encode(),
            [
                "NC-GW-1",
                request.headers["x-nc-gateway-key"],
                request.headers["x-nc-gateway-ts"],
                request.headers["x-nc-gateway-nonce"],
                request.method,
                path,
                query,
                request.headers["x-nc-client-ip"],
                digest.hexdigest(),
                hashlib.sha256(request.headers["authorization"].encode()).hexdigest(),
            ],
        )
        self.signature_ok.append(expected == request.headers["x-nc-gateway-sig"])
        self.upload_sizes.append(size)
        assert int(request.headers["content-length"]) == size
        return httpx.Response(201, json={"received": size})


async def test_large_upload_is_streamed_with_bounded_memory(  # type: ignore[no-untyped-def]
    settings, redis_client, fake_core, clock
) -> None:
    transport = _StreamingCore(fake_core)
    gateway_redis = type(redis_client).from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=2)
    app = GatewayApp(settings, redis=gateway_redis, core_transport=transport, clock=clock)
    h = Harness(app=app, core=fake_core, clock=clock, redis=redis_client, settings=settings)
    try:
        async with h.client() as client:
            result = await login(client)
        chunk = b"y" * 65536
        total = 192  # 12 MiB
        sent = 0

        async def receive() -> dict[str, Any]:
            nonlocal sent
            sent += 1
            return {"type": "http.request", "body": chunk, "more_body": sent < total}

        messages: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/bff/api/cases/c1/images",
            "raw_path": b"/bff/api/cases/c1/images",
            "query_string": b"",
            "headers": [
                (b"cookie", f"__Host-nc_sid={result.sid}".encode()),
                (b"content-type", b"multipart/form-data; boundary=x"),
                (b"content-length", str(total * len(chunk)).encode()),
                (b"origin", b"https://nc.example.test"),
                (b"x-csrf-token", result.csrf.encode()),
            ],
            "client": (CLIENT_IP, 4000),
        }
        tracemalloc.start()
        try:
            await app(scope, receive, send)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    finally:
        await app.core.aclose()
        await gateway_redis.aclose()
    assert messages[0]["status"] == 201
    assert transport.upload_sizes == [total * len(chunk)]
    assert transport.signature_ok == [True]
    # 12 MiB upload: špička paměti zůstává řádově u limitu spooled souboru (1 MiB), ne u velikosti těla
    assert peak < 4 * 1024 * 1024, peak


# ── F-1: Last-Event-ID u SSE ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "forwarded"),
    [("evt-41:abc.def_1", True), ("x" * 64, True), ("x" * 65, False), ("bad value", False), ("a\\b", False)],
)
async def test_last_event_id_forwarded_only_for_sse_and_valid(harness: Harness, value: str, forwarded: bool) -> None:
    routes = [(r["method"], r["path"]) for r in TEST_ALLOWLIST["routes"]]
    routes.append(("GET", "/api/v1/cases/{case_id}/activity/stream"))
    harness.app.allowlist = Allowlist(routes)
    seen: list[str | None] = []

    def sse(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("last-event-id"))
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=b"data: 1\n\n")

    harness.core.overrides[("GET", "/api/v1/cases/c1/activity/stream")] = sse
    async with harness.client() as client:
        result = await login(client)
        await client.get(
            "/bff/api/cases/c1/activity/stream",
            headers={**result.cookie, "Accept": "text/event-stream", "Last-Event-ID": value},
        )
        plain = await client.get("/bff/api/cases", headers={**result.cookie, "Last-Event-ID": "evt-1"})
    assert seen == [value if forwarded else None]
    assert "last-event-id" not in plain.json()["headers"]  # mimo SSE se nepřeposílá


# ── L1: CSP na odpovědích /bff/api ──────────────────────────────────────────


async def test_proxy_response_gets_default_csp_or_core_csp(harness: Harness) -> None:
    harness.core.overrides[("GET", "/api/v1/cases/withcsp")] = lambda r: httpx.Response(
        200, content=b"\x89PNG", headers={"Content-Type": "image/png", "Content-Security-Policy": "default-src 'none'"}
    )
    async with harness.client() as client:
        result = await login(client)
        plain = await client.get("/bff/api/cases", headers=result.cookie)
        own = await client.get("/bff/api/cases/withcsp", headers=result.cookie)
    assert plain.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'; sandbox"
    assert own.headers.get_list("content-security-policy") == ["default-src 'none'"]


# ── L4: čekání na zámek obnovy bez změny tokenu → 503 ──────────────────────


async def test_refresh_lock_timeout_returns_503_without_revocation(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        hashed = sid_hash(result.sid)
        await harness.redis.set(f"{LOCK_PREFIX}{hashed}", "other-worker", px=60_000)
        harness.app.lock_wait_seconds = 0.3
        harness.core.expire_access_tokens()
        response = await client.get("/bff/api/cases", headers=result.cookie)
    assert response.status_code == 503
    assert harness.core.refresh_calls == 0
    assert await harness.redis.exists(SessionStore.record_key(hashed)) == 1  # session nerevokována
    assert not any(e["type"] == "session_revoked" for e in harness.app.events.pending)
    assert harness.app.lock_ttl_ms >= harness.settings.core_timeout_seconds * 1000


# ── L5: atomický limit neúspěšných loginů na e-mail ─────────────────────────


async def test_email_failure_limit_holds_under_concurrency(harness: Harness) -> None:
    async with harness.client() as client:
        responses = await asyncio.gather(
            *(
                client.post(
                    "/bff/auth/login", json={"email": USER["email"], "password": "spatne"}, headers=origin_headers()
                )
                for _ in range(15)
            )
        )
    statuses = sorted(r.status_code for r in responses)
    assert statuses.count(401) <= 10
    assert statuses.count(429) >= 5
    assert len(harness.core.calls("POST", "/api/v1/auth/login")) <= 10


async def test_successful_login_does_not_consume_failure_budget(harness: Harness) -> None:
    async with harness.client() as client:
        for _ in range(9):
            r = await client.post(
                "/bff/auth/login", json={"email": USER["email"], "password": "spatne"}, headers=origin_headers()
            )
            assert r.status_code == 401
        ok = await client.post(
            "/bff/auth/login", json={"email": USER["email"], "password": PASSWORD}, headers=origin_headers()
        )
        tenth = await client.post(
            "/bff/auth/login", json={"email": USER["email"], "password": "spatne"}, headers=origin_headers()
        )
        blocked = await client.post(
            "/bff/auth/login", json={"email": USER["email"], "password": PASSWORD}, headers=origin_headers()
        )
    assert ok.status_code == 200
    assert tenth.status_code == 401
    assert blocked.status_code == 429


# ── L6: expirace → odhlášení v core na pozadí ───────────────────────────────


async def test_idle_expiry_logs_out_core_session_in_background(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        refresh_token = next(iter(harness.core.refresh_tokens))
        harness.clock.advance(harness.settings.idle_timeout_seconds + 1)
        response = await client.get("/bff/session", headers=result.cookie)
    assert response.json() == {"authenticated": False}
    await harness.app.drain_background()
    (call,) = harness.core.logout_calls
    assert call["body"] == {"refreshToken": refresh_token}
    assert call["authorization"].startswith("Bearer ")


async def test_expiry_core_logout_failure_does_not_block(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        harness.core.down = True
        harness.clock.advance(harness.settings.absolute_timeout_seconds + 1)
        response = await client.get("/bff/api/cases", headers=result.cookie)
    assert response.status_code == 401
    await harness.app.drain_background()


# ── L8: login-ip se počítá až po validaci těla ──────────────────────────────


async def test_malformed_login_bodies_do_not_consume_ip_limit(harness: Harness) -> None:
    async with harness.client() as client:
        for body in ([1, 2], {"email": 5}, "x" * 10, {"email": "a@b.cz"}) * 7:
            r = await client.post(
                "/bff/auth/login",
                content=json.dumps(body),
                headers={**origin_headers(), "Content-Type": "application/json"},
            )
            assert r.status_code == 400
        # 28 nevalidních těl (> limit 20/5 min) nespotřebovalo IP limit – login projde
        await login(client)
    keys = [k.decode() for k in await harness.redis.keys("nc:bff:rl:login-ip:*")]
    assert len(keys) == 1
    assert int(await harness.redis.get(keys[0])) == 1


# ── F-3: logout-all při částečném selhání core ──────────────────────────────


async def test_logout_all_partial_failure_returns_502_code_and_clears_everything(harness: Harness) -> None:
    harness.core.remote_sessions = [{"id": "desktop-sess-9", "isCurrent": False, "revokedAt": None}]
    harness.core.overrides[("DELETE", "/api/v1/auth/sessions/desktop-sess-9")] = lambda r: httpx.Response(500)
    async with harness.client() as client:
        a = await login(client)
        b = await login(client)
        response = await client.post("/bff/auth/logout-all", headers=a.mutation())
        after_b = await client.get("/bff/session", headers=b.cookie)
    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "LOGOUT_ALL_PARTIAL"
    assert set(body) == {"detail", "code", "requestId"}
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert after_b.json() == {"authenticated": False}
    assert await harness.redis.exists(SessionStore.user_key(USER["id"])) == 0
