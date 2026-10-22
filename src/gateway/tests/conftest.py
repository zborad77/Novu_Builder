"""Společné fixtures: falešné core (ověřuje HMAC nezávislou implementací), Redis, hodiny.

Falešné core je ``httpx.MockTransport``. Podpis ověřuje vlastní implementací
napsanou přímo podle docs/security/GATEWAY_CORE_CONTRACT.md kap. 3 (záměrně
nepoužívá ``nc_gateway.signing``). Každý nepodepsaný nebo špatně podepsaný
požadavek se zaznamená do ``sig_failures`` a fixture na konci testu ověří,
že žádný nebyl.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from http.cookiejar import CookieJar, DefaultCookiePolicy
from pathlib import Path
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis

from nc_gateway.app import GatewayApp
from nc_gateway.config import Settings, load_settings

REDIS_URL = os.environ.get("NC_GATEWAY_TEST_REDIS_URL", "redis://localhost:56379/5")
PUBLIC_ORIGIN = "https://nc.example.test"
HMAC_KID = "gw-test"
HMAC_SECRET = "0123456789abcdef0123456789abcdef-gateway-test"
SESSION_KEY_A = base64.b64encode(b"A" * 32).decode()
SESSION_KEY_B = base64.b64encode(b"B" * 32).decode()
CLIENT_IP = "198.51.100.20"
TRUSTED_PROXY = "10.0.0.1"

TEST_ALLOWLIST: dict[str, Any] = {
    "generatedFrom": "tests",
    "zone": "gateway",
    "routes": [
        {"method": "GET", "path": "/api/v1/cases"},
        {"method": "POST", "path": "/api/v1/cases"},
        {"method": "GET", "path": "/api/v1/cases/{case_id}"},
        {"method": "PATCH", "path": "/api/v1/cases/{case_id}"},
        {"method": "DELETE", "path": "/api/v1/cases/{case_id}/images/{image_id}"},
        {"method": "POST", "path": "/api/v1/cases/{case_id}/images"},
        {"method": "GET", "path": "/api/v1/files/images/{image_id}/{variant}"},
        {"method": "GET", "path": "/api/v1/boom"},
        {"method": "POST", "path": "/api/v1/auth/login"},
        {"method": "POST", "path": "/api/v1/auth/logout"},
        {"method": "GET", "path": "/api/v1/auth/me"},
        {"method": "POST", "path": "/api/v1/auth/refresh"},
        {"method": "GET", "path": "/api/v1/auth/sessions"},
        {"method": "DELETE", "path": "/api/v1/auth/sessions/{session_id}"},
        {"method": "POST", "path": "/api/v1/auth/change-password"},
        {"method": "POST", "path": "/api/v1/internal/security-events"},
    ],
}

USER = {
    "id": "user-1",
    "email": "novak@firma.cz",
    "fullName": "Jan Novák",
    "role": "manager",
    "isActive": True,
    "organizationId": "org-1",
    "isSuperAdmin": False,
    "impersonatedBy": None,
}
PASSWORD = "Spravne-Heslo-123"


class FakeClock:
    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def fake_jwt(claims: dict[str, Any]) -> str:
    def enc(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{enc({'alg': 'HS256', 'typ': 'JWT'})}.{enc(claims)}.{secrets.token_urlsafe(16)}"


# ── nezávislé ověření podpisu podle kontraktu ───────────────────────────────

_SIG_HEADERS = ("x-nc-gateway-key", "x-nc-gateway-ts", "x-nc-gateway-nonce", "x-nc-client-ip", "x-nc-gateway-sig")


def contract_signature(secret: bytes, fields: list[str]) -> str:
    canonical = "\n".join(fields).encode("utf-8")
    return hmac.new(secret, canonical, hashlib.sha256).hexdigest()


def verify_contract_signature(request: httpx.Request, keys: dict[str, bytes], seen_nonces: set[str]) -> str | None:
    """Vrátí důvod odmítnutí, nebo ``None`` při platném podpisu."""
    for name in _SIG_HEADERS:
        if len(request.headers.get_list(name)) != 1:
            return f"header_{name}"
    if len(request.headers.get_list("authorization")) > 1:
        return "duplicate_authorization"
    kid = request.headers["x-nc-gateway-key"]
    if kid not in keys:
        return "unknown_key"
    nonce = request.headers["x-nc-gateway-nonce"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce):
        return "nonce_format"
    ts = request.headers["x-nc-gateway-ts"]
    if not ts.isdigit():
        return "ts_format"
    sig = request.headers["x-nc-gateway-sig"]
    if not re.fullmatch(r"[0-9a-f]{64}", sig):
        return "sig_format"
    target = request.url.raw_path.decode("ascii")
    path, _, query = target.partition("?")
    body = request.content
    authorization = request.headers.get("authorization", "")
    expected = contract_signature(
        keys[kid],
        [
            "NC-GW-1",
            kid,
            ts,
            nonce,
            request.method.upper(),
            path,
            query,
            request.headers["x-nc-client-ip"],
            hashlib.sha256(body).hexdigest(),
            hashlib.sha256(authorization.encode("latin-1")).hexdigest(),
        ],
    )
    if not hmac.compare_digest(expected, sig):
        return "bad_signature"
    if nonce in seen_nonces:
        return "replayed_nonce"
    seen_nonces.add(nonce)
    return None


@dataclass
class FakeCore:
    clock: FakeClock
    keys: dict[str, bytes] = field(default_factory=lambda: {HMAC_KID: HMAC_SECRET.encode()})
    down: bool = False
    access_ttl: int = 600
    requests: list[httpx.Request] = field(default_factory=list)
    sig_failures: list[str] = field(default_factory=list)
    nonces: set[str] = field(default_factory=set)
    access_tokens: dict[str, float] = field(default_factory=dict)  # token -> exp
    refresh_tokens: set[str] = field(default_factory=set)
    overrides: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = field(default_factory=dict)
    refresh_calls: int = 0
    logout_calls: list[dict[str, Any]] = field(default_factory=list)
    deleted_sessions: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    remote_sessions: list[dict[str, Any]] = field(default_factory=list)

    def issue(self) -> dict[str, Any]:
        exp = self.clock() + self.access_ttl
        access = fake_jwt({"sub": USER["id"], "exp": int(exp), "sid": "core-sess-1", "aud": "nc-web"})
        refresh = fake_jwt({"sub": USER["id"], "typ": "refresh", "jti": uuid.uuid4().hex})
        self.access_tokens[access] = exp
        self.refresh_tokens.add(refresh)
        return {
            "accessToken": access,
            "refreshToken": refresh,
            "tokenType": "bearer",
            "user": USER,
            "sessionId": "core-sess-1",
        }

    def revoke_all(self) -> None:
        self.access_tokens.clear()
        self.refresh_tokens.clear()

    def expire_access_tokens(self) -> None:
        self.access_tokens.clear()

    def _authorized(self, request: httpx.Request) -> bool:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return False
        exp = self.access_tokens.get(auth[7:])
        return exp is not None and exp > self.clock()

    def by_method_path(self, request: httpx.Request) -> list[httpx.Request]:
        return [r for r in self.requests if (r.method, r.url.path) == (request.method, request.url.path)]

    def calls(self, method: str, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and r.url.path == path]

    def handler(self, request: httpx.Request) -> httpx.Response:
        response = self._handle(request)
        if isinstance(response.stream, httpx.ByteStream):
            # Odpověď s předčteným tělem převést na stream jako ze sítě (gateway čte aiter_raw).
            body = response.content

            async def stream() -> AsyncIterator[bytes]:
                yield body

            return httpx.Response(response.status_code, headers=response.headers, content=stream())
        return response

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("core down", request=request)
        reason = verify_contract_signature(request, self.keys, self.nonces)
        if reason is not None:
            self.sig_failures.append(reason)
            return httpx.Response(401, json={"detail": "Invalid gateway signature."})
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key in self.overrides:
            return self.overrides[key](request)
        method, path = key
        leak_headers = {
            "Set-Cookie": "core_session=leak; Path=/",
            "X-Internal-Debug": "secret-internal",
            "Server": "uvicorn",
            "X-NC-Gateway-Sig": "f" * 64,
            "Access-Control-Allow-Origin": "*",
        }
        if (method, path) == ("POST", "/api/v1/auth/login"):
            data = json.loads(request.content)
            if data.get("email") == USER["email"] and data.get("password") == PASSWORD:
                return httpx.Response(200, json=self.issue(), headers=leak_headers)
            return httpx.Response(401, json={"detail": "Invalid credentials."})
        if (method, path) == ("POST", "/api/v1/auth/refresh"):
            self.refresh_calls += 1
            token = json.loads(request.content).get("refreshToken")
            if token not in self.refresh_tokens:
                return httpx.Response(401, json={"detail": "Invalid or expired refresh token."})
            self.refresh_tokens.discard(token)  # rotace, reuse = 401
            return httpx.Response(200, json=self.issue())
        if (method, path) == ("POST", "/api/v1/auth/logout"):
            self.logout_calls.append(
                {"body": json.loads(request.content), "authorization": request.headers.get("authorization")}
            )
            return httpx.Response(200, json={"message": "Logged out."})
        if (method, path) == ("POST", "/api/v1/internal/security-events"):
            if "authorization" in request.headers:
                return httpx.Response(404, json={"detail": "Not Found"})
            payload = json.loads(request.content)
            self.events.extend(payload["events"])
            return httpx.Response(202, json={"accepted": len(payload["events"])})
        if not self._authorized(request):
            return httpx.Response(401, json={"detail": "Not authenticated"})
        if (method, path) == ("GET", "/api/v1/auth/me"):
            return httpx.Response(200, json=USER)
        if (method, path) == ("GET", "/api/v1/auth/sessions"):
            items = [{"id": "core-sess-1", "isCurrent": True, "revokedAt": None}, *self.remote_sessions]
            return httpx.Response(200, json={"items": items})
        if method == "DELETE" and path.startswith("/api/v1/auth/sessions/"):
            self.deleted_sessions.append(path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={"message": "Session revoked."})
        if (method, path) == ("GET", "/api/v1/boom"):
            return httpx.Response(500, text="Traceback (most recent call last): secret stack", headers=leak_headers)
        echo = {
            "method": method,
            "path": path,
            "rawTarget": request.url.raw_path.decode("ascii"),
            "headers": {k.lower(): v for k, v in request.headers.multi_items()},
            "bodyLength": len(request.content),
        }
        return httpx.Response(
            200,
            json=echo,
            headers={**leak_headers, "ETag": '"v1"', "Cache-Control": "private, max-age=0"},
        )


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def allowlist_file(tmp_path: Path) -> Path:
    path = tmp_path / "gateway-allowlist.json"
    path.write_text(json.dumps(TEST_ALLOWLIST), encoding="utf-8")
    return path


def base_env(allowlist_file: Path, **overrides: str) -> dict[str, str]:
    env = {
        "NC_ENV": "production",
        "NC_BFF_PUBLIC_ORIGIN": PUBLIC_ORIGIN,
        "NC_BFF_CORE_URL": "http://core.test:8101",
        "NC_GATEWAY_HMAC_KEY": f"{HMAC_KID}:{HMAC_SECRET}",
        "NC_BFF_SESSION_KEYS": f"k1:{SESSION_KEY_A}",
        "NC_BFF_REDIS_URL": REDIS_URL,
        "NC_BFF_ALLOWLIST_PATH": str(allowlist_file),
        "NC_BFF_TRUSTED_PROXY": TRUSTED_PROXY,
    }
    env.update(overrides)
    return env


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(allowlist_file: Path) -> Settings:
    return load_settings(base_env(allowlist_file))


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(REDIS_URL, socket_connect_timeout=1, socket_timeout=2)
    try:
        await client.ping()
    except Exception as exc:  # noqa: BLE001
        await client.aclose()
        pytest.skip(f"Testovací Redis {REDIS_URL} není dostupný ({type(exc).__name__}); test vyžaduje skutečný Redis.")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def fake_core(clock: FakeClock) -> FakeCore:
    return FakeCore(clock=clock)


@dataclass
class Harness:
    app: GatewayApp
    core: FakeCore
    clock: FakeClock
    redis: Redis
    settings: Settings

    def client(self, ip: str = CLIENT_IP) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, client=(ip, 51515)),
            base_url=PUBLIC_ORIGIN,
            # cookies posílají testy explicitně v hlavičce Cookie
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
        )


async def make_harness(settings: Settings, redis: Redis, core: FakeCore, clock: FakeClock) -> Harness:
    gateway_redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=2)
    app = GatewayApp(settings, redis=gateway_redis, core_transport=httpx.MockTransport(core.handler), clock=clock)
    return Harness(app=app, core=core, clock=clock, redis=redis, settings=settings)


@pytest.fixture
async def harness(
    settings: Settings, redis_client: Redis, fake_core: FakeCore, clock: FakeClock
) -> AsyncIterator[Harness]:
    h = await make_harness(settings, redis_client, fake_core, clock)
    yield h
    await h.app.core.aclose()
    await h.app.redis.aclose()
    assert fake_core.sig_failures == [], f"core odmítl podpis: {fake_core.sig_failures}"


def origin_headers(csrf: str | None = None, origin: str | None = PUBLIC_ORIGIN) -> dict[str, str]:
    headers: dict[str, str] = {}
    if origin is not None:
        headers["Origin"] = origin
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    return headers


def cookie_from(response: httpx.Response, name: str = "__Host-nc_sid") -> str | None:
    for header in response.headers.get_list("set-cookie"):
        first = header.split(";", 1)[0]
        key, _, value = first.partition("=")
        if key == name:
            return value
    return None


@dataclass
class LoggedIn:
    sid: str
    csrf: str
    response: httpx.Response

    @property
    def cookie(self) -> dict[str, str]:
        return {"Cookie": f"__Host-nc_sid={self.sid}"}

    def mutation(self, **extra: str) -> dict[str, str]:
        return {**self.cookie, **origin_headers(self.csrf), **extra}


async def login(client: httpx.AsyncClient, headers: dict[str, str] | None = None) -> LoggedIn:
    response = await client.post(
        "/bff/auth/login",
        json={"email": USER["email"], "password": PASSWORD},
        headers={**origin_headers(), **(headers or {})},
    )
    assert response.status_code == 200, response.text
    sid = cookie_from(response)
    assert sid
    return LoggedIn(sid=sid, csrf=response.json()["csrfToken"], response=response)


# ── přímé ASGI volání (surová cesta bez normalizace klientem) ───────────────


@dataclass
class RawResponse:
    status: int
    headers: list[tuple[bytes, bytes]]
    body: bytes

    def header(self, name: str) -> str | None:
        for key, value in self.headers:
            if key.decode().lower() == name.lower():
                return value.decode("latin-1")
        return None

    def json(self) -> Any:
        return json.loads(self.body)


async def asgi_request(
    app: Any,
    method: str,
    raw_path: bytes,
    *,
    headers: list[tuple[str, str]] | None = None,
    body: bytes = b"",
    client: tuple[str, int] = (CLIENT_IP, 5000),
    query: bytes = b"",
) -> RawResponse:
    from urllib.parse import unquote_to_bytes

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": unquote_to_bytes(raw_path).decode("latin-1"),
        "raw_path": raw_path,
        "query_string": query,
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or [])],
        "client": client,
        "server": ("nc.example.test", 443),
        "root_path": "",
    }
    messages: list[dict[str, Any]] = []
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = messages[0]
    return RawResponse(
        status=start["status"],
        headers=list(start["headers"]),
        body=b"".join(m.get("body", b"") for m in messages[1:]),
    )


DEAD_REDIS_URL = "redis://127.0.0.1:1/5"


@pytest.fixture
async def offline_harness(allowlist_file: Path, fake_core: FakeCore, clock: FakeClock) -> AsyncIterator[Harness]:
    """Gateway s nedostupným Redisem (port 1) – pro routy, které Redis nepotřebují, a pro 503."""
    settings = load_settings(base_env(allowlist_file, NC_BFF_REDIS_URL=DEAD_REDIS_URL))
    redis = Redis.from_url(DEAD_REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
    app = GatewayApp(settings, redis=redis, core_transport=httpx.MockTransport(fake_core.handler), clock=clock)
    yield Harness(app=app, core=fake_core, clock=clock, redis=redis, settings=settings)
    await app.core.aclose()
    await redis.aclose()
