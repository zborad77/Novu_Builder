"""Login, session, logout, logout-all, expirace, fixation, rate limit loginu (vyžaduje Redis)."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime

from nc_gateway.store import SessionStore, sid_hash
from tests.conftest import (
    CLIENT_IP,
    PASSWORD,
    PUBLIC_ORIGIN,
    USER,
    Harness,
    cookie_from,
    login,
    make_harness,
    origin_headers,
)

# ── login ───────────────────────────────────────────────────────────────────


async def test_login_sets_host_cookie_with_strict_attributes(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
    set_cookies = result.response.headers.get_list("set-cookie")
    assert len(set_cookies) == 1  # Set-Cookie z core se nevrací
    header = set_cookies[0]
    name_value, *attrs = [part.strip() for part in header.split(";")]
    assert name_value.startswith("__Host-nc_sid=")
    attr_names = {a.split("=", 1)[0].lower() for a in attrs}
    assert {"httponly", "secure", "samesite", "path"} <= attr_names
    assert "SameSite=Strict" in attrs
    assert "Path=/" in attrs
    assert "domain" not in attr_names
    assert "max-age" not in attr_names and "expires" not in attr_names  # session cookie
    assert len(result.sid) == 43


async def test_login_body_contains_only_user_and_csrf_never_tokens(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
    body = result.response.json()
    assert set(body) == {"user", "csrfToken"}
    assert body["user"] == USER
    everything = result.response.text + json.dumps(dict(result.response.headers))
    for token in list(harness.core.access_tokens) + list(harness.core.refresh_tokens):
        assert token not in everything
    assert "accessToken" not in everything and "refreshToken" not in everything
    assert result.response.headers["cache-control"] == "no-store"
    assert result.response.headers["x-content-type-options"] == "nosniff"
    assert result.response.headers["referrer-policy"] == "no-referrer"
    assert "x-internal-debug" not in result.response.headers
    assert result.response.headers.get("server") is None


async def test_login_core_call_is_signed_and_has_no_authorization(harness: Harness) -> None:
    async with harness.client() as client:
        await login(client)
    (call,) = harness.core.calls("POST", "/api/v1/auth/login")
    assert "authorization" not in call.headers
    assert call.headers["x-nc-client-ip"] == CLIENT_IP
    assert json.loads(call.content) == {"email": USER["email"], "password": PASSWORD}


async def test_login_invalid_credentials_is_uniform_401(harness: Harness) -> None:
    async with harness.client() as client:
        wrong_password = await client.post(
            "/bff/auth/login", json={"email": USER["email"], "password": "spatne"}, headers=origin_headers()
        )
        unknown_user = await client.post(
            "/bff/auth/login", json={"email": "nikdo@firma.cz", "password": "x"}, headers=origin_headers()
        )
    for response in (wrong_password, unknown_user):
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials."
        assert set(response.json()) == {"detail", "requestId"}
        assert cookie_from(response) is None
    failures = [e for e in harness.app.events.pending if e["type"] == "login_failure"]
    assert len(failures) == 2


async def test_login_origin_rules(harness: Harness) -> None:
    body = {"email": USER["email"], "password": PASSWORD}
    async with harness.client() as client:
        foreign = await client.post("/bff/auth/login", json=body, headers={"Origin": "https://evil.example"})
        missing = await client.post("/bff/auth/login", json=body)
        cross_site = await client.post("/bff/auth/login", json=body, headers={"Sec-Fetch-Site": "cross-site"})
        same_origin = await client.post("/bff/auth/login", json=body, headers={"Sec-Fetch-Site": "same-origin"})
    assert foreign.status_code == 403
    assert missing.status_code == 403
    assert cross_site.status_code == 403
    assert same_origin.status_code == 200
    assert any(e["type"] == "origin_failure" for e in harness.app.events.pending)


async def test_login_requires_json(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.post(
            "/bff/auth/login",
            content=f"email={USER['email']}&password={PASSWORD}",
            headers={**origin_headers(), "Content-Type": "application/x-www-form-urlencoded"},
        )
    assert response.status_code == 415
    assert harness.core.requests == []


async def test_login_fixation_new_sid_and_old_cookie_invalid(harness: Harness) -> None:
    async with harness.client() as client:
        first = await login(client)
        second = await login(client, headers=first.cookie)
        assert second.sid != first.sid
        assert await harness.redis.exists(SessionStore.record_key(sid_hash(first.sid))) == 0
        old = await client.get("/bff/session", headers=first.cookie)
        new = await client.get("/bff/session", headers=second.cookie)
    assert old.json() == {"authenticated": False}
    assert new.json()["authenticated"] is True


async def test_login_attacker_planted_cookie_is_ignored(harness: Harness) -> None:
    planted = "P" * 43
    async with harness.client() as client:
        result = await login(client, headers={"Cookie": f"__Host-nc_sid={planted}"})
    assert result.sid != planted


async def test_login_ip_rate_limit_429(harness: Harness) -> None:
    async with harness.client() as client:
        statuses = []
        for i in range(21):
            response = await client.post(
                "/bff/auth/login", json={"email": f"u{i}@firma.cz", "password": "x"}, headers=origin_headers()
            )
            statuses.append(response.status_code)
    assert statuses[:20] == [401] * 20
    assert statuses[20] == 429
    assert int(response.headers["retry-after"]) > 0
    assert any(e["type"] == "rate_limited" for e in harness.app.events.pending)


async def test_login_email_failure_limit_429_even_with_correct_password(harness: Harness) -> None:
    async with harness.client() as client:
        for _ in range(10):
            failed = await client.post(
                "/bff/auth/login", json={"email": USER["email"], "password": "spatne"}, headers=origin_headers()
            )
            assert failed.status_code == 401
        blocked = await client.post(
            "/bff/auth/login", json={"email": USER["email"].upper(), "password": PASSWORD}, headers=origin_headers()
        )
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers
    assert len(harness.core.calls("POST", "/api/v1/auth/login")) == 10


async def test_login_core_unavailable_502(harness: Harness) -> None:
    harness.core.down = True
    async with harness.client() as client:
        response = await client.post(
            "/bff/auth/login", json={"email": USER["email"], "password": PASSWORD}, headers=origin_headers()
        )
    assert response.status_code == 502
    assert cookie_from(response) is None
    assert any(e["type"] == "upstream_unavailable" for e in harness.app.events.pending)


# ── /bff/session ────────────────────────────────────────────────────────────


async def test_session_without_cookie(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.get("/bff/session")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
    assert response.headers["cache-control"] == "no-store"


async def test_session_with_valid_cookie(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        response = await client.get("/bff/session", headers=result.cookie)
    body = response.json()
    assert body["authenticated"] is True
    assert body["user"] == USER
    assert body["csrfToken"] == result.csrf
    start = harness.clock()
    assert body["expiresAt"] == datetime.fromtimestamp(start + 43200, tz=UTC).isoformat()
    assert body["idleExpiresAt"] == datetime.fromtimestamp(start + 1800, tz=UTC).isoformat()
    assert response.headers["cache-control"] == "no-store"
    assert "accessToken" not in response.text


async def test_session_with_garbage_cookie_clears_it(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.get("/bff/session", headers={"Cookie": "__Host-nc_sid=../../etc"})
    assert response.json() == {"authenticated": False}
    assert "Max-Age=0" in response.headers["set-cookie"]


# ── jednotná 401 ────────────────────────────────────────────────────────────


async def test_unified_401_on_api(harness: Harness) -> None:
    async with harness.client() as client:
        no_cookie = await client.get("/bff/api/cases")
        unknown = await client.get("/bff/api/cases", headers={"Cookie": "__Host-nc_sid=" + "u" * 43})
        garbage = await client.get("/bff/api/cases", headers={"Cookie": "__Host-nc_sid=x"})
    for response in (no_cookie, unknown, garbage):
        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated."
        assert set(response.json()) == {"detail", "requestId"}
    assert harness.core.requests == []


# ── logout ──────────────────────────────────────────────────────────────────


async def test_logout_clears_cookie_deletes_record_and_calls_core(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        refresh_token = next(iter(harness.core.refresh_tokens))
        response = await client.post("/bff/auth/logout", headers=result.mutation())
        after = await client.get("/bff/api/cases", headers=result.cookie)
    assert response.status_code == 204
    assert response.content == b""
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-nc_sid=;") and "Max-Age=0" in cookie and "Secure" in cookie
    assert await harness.redis.exists(SessionStore.record_key(sid_hash(result.sid))) == 0
    (call,) = harness.core.logout_calls
    assert call["body"] == {"refreshToken": refresh_token}
    assert call["authorization"].startswith("Bearer ")
    assert after.status_code == 401
    assert any(e["type"] == "logout" for e in harness.app.events.pending)


async def test_logout_requires_csrf(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        missing = await client.post("/bff/auth/logout", headers={**result.cookie, **origin_headers()})
        wrong = await client.post("/bff/auth/logout", headers={**result.cookie, **origin_headers("x" * 43)})
        still = await client.get("/bff/session", headers=result.cookie)
    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert still.json()["authenticated"] is True
    assert harness.core.logout_calls == []


async def test_logout_succeeds_even_if_core_down(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        harness.core.down = True
        response = await client.post("/bff/auth/logout", headers=result.mutation())
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert await harness.redis.exists(SessionStore.record_key(sid_hash(result.sid))) == 0


async def test_logout_without_session_is_401(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.post("/bff/auth/logout", headers=origin_headers("x"))
    assert response.status_code == 401


# ── logout-all ──────────────────────────────────────────────────────────────


async def test_logout_all_removes_every_gateway_session_of_user(harness: Harness) -> None:
    harness.core.remote_sessions = [
        {"id": "desktop-sess-9", "isCurrent": False, "revokedAt": None},
        {"id": "old-sess", "isCurrent": False, "revokedAt": "2026-01-01T00:00:00Z"},
        {"id": "../evil", "isCurrent": False, "revokedAt": None},
    ]
    async with harness.client() as client:
        a = await login(client)
        b = await login(client)  # druhý prohlížeč téhož uživatele
        response = await client.post("/bff/auth/logout-all", headers=a.mutation())
        after_a = await client.get("/bff/session", headers=a.cookie)
        after_b = await client.get("/bff/session", headers=b.cookie)
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert after_a.json() == {"authenticated": False}
    assert after_b.json() == {"authenticated": False}
    assert await harness.redis.exists(SessionStore.user_key(USER["id"])) == 0
    assert harness.core.deleted_sessions == ["desktop-sess-9"]  # revokovaná a nevalidní id se přeskočí
    assert len(harness.core.logout_calls) == 1
    assert any(e["type"] == "logout_all" for e in harness.app.events.pending)


async def test_logout_all_requires_csrf(harness: Harness) -> None:
    async with harness.client() as client:
        a = await login(client)
        response = await client.post("/bff/auth/logout-all", headers={**a.cookie, **origin_headers()})
    assert response.status_code == 403


# ── expirace ────────────────────────────────────────────────────────────────


async def test_idle_timeout_expires_session(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        harness.clock.advance(harness.settings.idle_timeout_seconds + 1)
        response = await client.get("/bff/session", headers=result.cookie)
        api = await client.get("/bff/api/cases", headers=result.cookie)
    assert response.json() == {"authenticated": False}
    assert api.status_code == 401
    assert await harness.redis.exists(SessionStore.record_key(sid_hash(result.sid))) == 0
    expired = [e for e in harness.app.events.pending if e["type"] == "session_expired"]
    assert expired and expired[0]["detail"]["reason"] == "idle"


async def test_activity_extends_idle_but_not_absolute(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
        step = harness.settings.idle_timeout_seconds - 60
        elapsed = 0
        while elapsed + step < harness.settings.absolute_timeout_seconds:
            harness.clock.advance(step)
            elapsed += step
            response = await client.get("/bff/api/cases", headers=result.cookie)
            assert response.status_code == 200, elapsed
        harness.clock.advance(harness.settings.absolute_timeout_seconds - elapsed + 1)
        response = await client.get("/bff/api/cases", headers=result.cookie)
    assert response.status_code == 401
    expired = [e for e in harness.app.events.pending if e["type"] == "session_expired"]
    assert expired[-1]["detail"]["reason"] == "absolute"


async def test_absolute_timeout_with_short_settings(settings, redis_client, fake_core, clock) -> None:  # type: ignore[no-untyped-def]
    short = dataclasses.replace(settings, idle_timeout_seconds=600, absolute_timeout_seconds=900)
    h = await make_harness(short, redis_client, fake_core, clock)
    try:
        async with h.client() as client:
            result = await login(client)
            clock.advance(500)
            assert (await client.get("/bff/session", headers=result.cookie)).json()["authenticated"] is True
            clock.advance(401)
            assert (await client.get("/bff/session", headers=result.cookie)).json() == {"authenticated": False}
    finally:
        await h.app.core.aclose()
        await h.app.redis.aclose()


async def test_redis_ttl_is_bounded_by_idle_timeout(harness: Harness) -> None:
    async with harness.client() as client:
        result = await login(client)
    ttl = await harness.redis.ttl(SessionStore.record_key(sid_hash(result.sid)))
    assert 0 < ttl <= harness.settings.idle_timeout_seconds


async def test_dev_insecure_cookie_name_and_no_secure(settings, redis_client, fake_core, clock) -> None:  # type: ignore[no-untyped-def]
    dev = dataclasses.replace(
        settings, env="development", dev_insecure_cookie=True, public_origin="http://localhost:5173"
    )
    h = await make_harness(dev, redis_client, fake_core, clock)
    try:
        async with h.client() as client:
            response = await client.post(
                "/bff/auth/login",
                json={"email": USER["email"], "password": PASSWORD},
                headers={"Origin": "http://localhost:5173"},
            )
    finally:
        await h.app.core.aclose()
        await h.app.redis.aclose()
    header = response.headers["set-cookie"]
    assert header.startswith("nc_sid_dev=")
    assert "Secure" not in header
    assert "HttpOnly" in header and "SameSite=Strict" in header


async def test_public_origin_constant_matches_settings(harness: Harness) -> None:
    assert harness.settings.public_origin == PUBLIC_ORIGIN
