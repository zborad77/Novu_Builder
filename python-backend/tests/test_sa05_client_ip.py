"""SA-05 regression suite: client address behind trusted proxies, shared rate limits."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.client_ip import (
    TrustedProxyConfigError,
    TrustedProxyMiddleware,
    parse_ip,
    parse_trusted_proxies,
    resolve_client_ip,
)

NGINX = parse_trusted_proxies("172.30.250.2")
LOCAL = parse_trusted_proxies("127.0.0.1,::1")


# ── Configuration ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw", ["*", "0.0.0.0/0", "::/0", "nginx", "10.0.0.300", "127.0.0.1,*"])
def test_unsafe_or_invalid_trusted_proxy_lists_are_rejected(raw):
    with pytest.raises(TrustedProxyConfigError):
        parse_trusted_proxies(raw)


def test_trusted_proxy_list_accepts_addresses_and_networks():
    networks = parse_trusted_proxies(" 127.0.0.1 , ::1, 10.20.0.0/24 ,fd00::/64,")
    assert [str(n) for n in networks] == ["127.0.0.1/32", "::1/128", "10.20.0.0/24", "fd00::/64"]
    assert parse_trusted_proxies("") == ()


def test_settings_reject_wildcard_trusted_proxies(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("TRUSTED_PROXY_IPS", "*")
    with pytest.raises(ValidationError, match="TRUSTED_PROXY_IPS"):
        Settings()


def test_strict_settings_reject_uvicorn_wildcard_forwarded_allow_ips(monkeypatch):
    from app.core.config import Settings
    from tests.test_config_production_hardening import _set_valid_prod_env

    _set_valid_prod_env(monkeypatch)
    Settings()  # valid baseline
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    with pytest.raises(ValidationError, match="FORWARDED_ALLOW_IPS"):
        Settings()


def test_rate_limit_storage_is_redis_in_production_and_memory_in_development(monkeypatch):
    from app.core.config import Settings
    from tests.test_config_production_hardening import _set_valid_prod_env

    assert Settings().effective_rate_limit_storage_uri == "memory://"
    _set_valid_prod_env(monkeypatch)
    production = Settings()
    assert production.effective_rate_limit_storage_uri == production.redis_url
    assert production.effective_rate_limit_storage_uri.startswith(("redis://", "rediss://"))


# ── Address parsing and resolution ────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("203.0.113.7", "203.0.113.7"),
        ("203.0.113.7:51234", "203.0.113.7"),
        (" 2001:db8::7 ", "2001:db8::7"),
        ("[2001:db8::7]", "2001:db8::7"),
        ("[2001:db8::7]:443", "2001:db8::7"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
        ("unknown", None),
        ("", None),
        ("[2001:db8::7", None),
        ("203.0.113.7, 10.0.0.1", None),
    ],
)
def test_parse_ip(raw, expected):
    parsed = parse_ip(raw)
    assert (str(parsed) if parsed else None) == expected


def test_forwarded_header_from_untrusted_peer_is_ignored():
    assert resolve_client_ip("198.51.100.9", ["1.2.3.4"], NGINX) == "198.51.100.9"
    assert resolve_client_ip("198.51.100.9", ["1.2.3.4"], ()) == "198.51.100.9"


def test_trusted_proxy_forwards_real_client():
    assert resolve_client_ip("172.30.250.2", ["203.0.113.7"], NGINX) == "203.0.113.7"
    assert resolve_client_ip("::1", ["2001:db8::7"], LOCAL) == "2001:db8::7"
    assert resolve_client_ip("127.0.0.1", ["[2001:db8::7]:443"], LOCAL) == "2001:db8::7"


def test_client_supplied_prefix_cannot_be_chosen():
    # The client sends "X-Forwarded-For: 6.6.6.6"; an appending proxy adds the real peer.
    assert resolve_client_ip("172.30.250.2", ["6.6.6.6, 203.0.113.7"], NGINX) == "203.0.113.7"
    assert resolve_client_ip("172.30.250.2", ["6.6.6.6", "203.0.113.7"], NGINX) == "203.0.113.7"


def test_chain_of_trusted_proxies_is_walked_right_to_left():
    trusted = parse_trusted_proxies("10.0.0.0/24")
    assert resolve_client_ip("10.0.0.2", ["6.6.6.6, 203.0.113.7, 10.0.0.1"], trusted) == "203.0.113.7"


@pytest.mark.parametrize("header", ["garbage", "203.0.113.7, not-an-ip", ", ", ",".join(["203.0.113.7"] * 21)])
def test_malformed_or_oversized_chain_falls_back_to_proxy(header):
    assert resolve_client_ip("172.30.250.2", [header], NGINX) == "172.30.250.2"


def test_all_trusted_hops_resolve_to_the_proxy_itself():
    assert resolve_client_ip("127.0.0.1", ["127.0.0.1"], LOCAL) == "127.0.0.1"
    assert resolve_client_ip("127.0.0.1", [], LOCAL) == "127.0.0.1"


# ── Middleware ────────────────────────────────────────────────────────────────


def _echo_app(trusted):
    async def echo(request: Request) -> JSONResponse:
        return JSONResponse({"client": request.client.host if request.client else None, "scheme": request.url.scheme})

    return TrustedProxyMiddleware(Starlette(routes=[Route("/", echo)]), trusted_proxies=trusted)


async def _echo(app, peer: str, headers: dict[str, str]) -> dict:
    transport = ASGITransport(app=app, client=(peer, 40000))
    async with AsyncClient(transport=transport, base_url="http://backend") as client:
        return (await client.get("/", headers=headers)).json()


async def test_middleware_rewrites_client_and_scheme_only_for_trusted_proxy():
    app = _echo_app(NGINX)
    spoof = {"X-Forwarded-For": "6.6.6.6", "X-Forwarded-Proto": "https"}

    assert await _echo(app, "198.51.100.9", spoof) == {"client": "198.51.100.9", "scheme": "http"}
    assert await _echo(app, "172.30.250.2", {"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"}) == {
        "client": "203.0.113.7",
        "scheme": "https",
    }
    # Unknown protocol values are ignored.
    assert (await _echo(app, "172.30.250.2", {"X-Forwarded-Proto": "javascript"}))["scheme"] == "http"


async def test_application_resolves_client_before_rate_limiting_and_audit():
    """create_app() resolves the client before rate limiting and audit.

    Outermost is the gateway signature check (F3.4): in zone gateway it replaces
    the address with the signed X-NC-Client-IP and drops X-Forwarded-For; in the
    other zones it only drops X-NC-* headers. TrustedProxyMiddleware comes next.
    """
    from app.core.gateway_auth import GatewaySignatureMiddleware
    from app.main import app

    assert app.user_middleware[0].cls is GatewaySignatureMiddleware
    assert app.user_middleware[1].cls is TrustedProxyMiddleware


# ── Shared rate limits across processes (Redis) ───────────────────────────────


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _redis_available() -> bool:
    try:
        import redis

        redis.Redis.from_url(_redis_url(), socket_connect_timeout=0.5).ping()
        return True
    except Exception:
        return False


async def _limited_app(storage_uri: str):
    from fastapi import FastAPI
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.extension import _rate_limit_exceeded_handler

    from app.core.limiter import client_ip_rate_limit_key

    limiter = Limiter(key_func=client_ip_rate_limit_key, storage_uri=storage_uri, in_memory_fallback_enabled=False)
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.post("/login")
    @limiter.limit("3/minute")
    async def login(request: Request) -> dict:
        return {"ok": True}

    return app


@pytest.mark.skipif(not _redis_available(), reason="requires Redis (REDIS_URL); runs in CI and the PG+Redis suite")
async def test_rate_limit_is_shared_between_worker_processes():
    # Two independent Limiter instances stand in for two uvicorn workers.
    peer = f"203.0.113.{uuid.uuid4().int % 200 + 1}"
    statuses = []
    for _ in range(2):
        app = await _limited_app(_redis_url())
        transport = ASGITransport(app=app, client=(peer, 1234))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(3):
                statuses.append((await client.post("/login")).status_code)
    assert statuses == [200, 200, 200, 429, 429, 429]


async def test_unreachable_rate_limit_storage_fails_closed():
    from redis.exceptions import RedisError

    app = await _limited_app("redis://127.0.0.1:1/0")
    transport = ASGITransport(app=app, client=("203.0.113.9", 1234), raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with pytest.raises(RedisError):
            await client.post("/login")


def test_application_maps_redis_outage_to_503():
    from redis.exceptions import RedisError

    from app.main import app

    assert RedisError in app.exception_handlers


def test_uvicorn_proxy_header_handling_is_disabled_in_the_image():
    from pathlib import Path

    entrypoint = (Path(__file__).resolve().parents[1] / "docker-entrypoint.sh").read_text(encoding="utf-8")
    command = next(line for line in entrypoint.splitlines() if line.startswith("exec uvicorn"))
    assert "--no-proxy-headers" in command


# ── Unix-domain socket behind nginx (deploy/linux, F6) ────────────────────────


def test_unix_token_is_accepted_and_not_a_network():
    from app.core.client_ip import trusts_unix_socket

    assert trusts_unix_socket("unix") and trusts_unix_socket("127.0.0.1, UNIX")
    assert not trusts_unix_socket("127.0.0.1,::1")
    assert parse_trusted_proxies("unix") == ()


def test_unix_socket_peer_uses_forwarded_chain_only_when_trusted():
    assert resolve_client_ip(None, ["203.0.113.7"], (), trust_unix_socket=True) == "203.0.113.7"
    assert resolve_client_ip(None, ["6.6.6.6, 203.0.113.7"], (), trust_unix_socket=True) == "203.0.113.7"
    assert resolve_client_ip(None, ["garbage"], (), trust_unix_socket=True) is None
    assert resolve_client_ip(None, ["203.0.113.7"], (), trust_unix_socket=False) is None


async def test_middleware_resolves_client_for_unix_socket_requests():
    seen = {}

    async def app(scope, receive, send):
        seen["client"], seen["scheme"] = scope.get("client"), scope.get("scheme")
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        return None

    def scope():
        return {
            "type": "http",
            "method": "GET",
            "path": "/",
            "scheme": "http",
            "client": None,  # uvicorn --uds
            "headers": [(b"x-forwarded-for", b"203.0.113.7"), (b"x-forwarded-proto", b"https")],
        }

    await TrustedProxyMiddleware(app, trusted_proxies=(), trust_unix_socket=True)(scope(), receive, send)
    assert seen == {"client": ("203.0.113.7", 0), "scheme": "https"}

    await TrustedProxyMiddleware(app, trusted_proxies=(), trust_unix_socket=False)(scope(), receive, send)
    assert seen == {"client": None, "scheme": "http"}
