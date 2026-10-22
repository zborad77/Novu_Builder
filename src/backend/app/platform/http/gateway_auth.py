"""Gateway → Private Core service authentication (F3.4).

Kontrakt: docs/security/GATEWAY_CORE_CONTRACT.md. Shrnutí:

* Instance ``nc-api@gateway`` přijme požadavek jen s platným podpisem
  ``X-NC-Gateway-Sig`` (HMAC-SHA256). Bez něj vrací 401 na všechno, ještě před
  exposure guardem, takže nepodepsaný volající nezjistí ani to, které routy
  existují.
* Podpis váže identitu gateway (``X-NC-Gateway-Key`` – id klíče, rotace bez
  výpadku), čas (``X-NC-Gateway-Ts``, okno ±``NC_GATEWAY_SIG_MAX_SKEW_SECONDS``),
  jednorázový ``X-NC-Gateway-Nonce`` (replay), metodu, cestu, query, adresu
  klienta (``X-NC-Client-IP``), SHA-256 těla a SHA-256 hlavičky
  ``Authorization``. Žádnou z těchto hodnot nejde po podpisu změnit.
* Instance gateway nikdy nečte ``X-Forwarded-For``: adresa klienta pro audit
  a rate limit pochází jen z podepsané ``X-NC-Client-IP``. O oprávnění dál
  rozhoduje jen JWT (``aud`` nc-web), RBAC a exposure matrix – podpis
  potvrzuje původ požadavku, ne práva uživatele.
* Ostatní zóny hlavičky ``X-NC-*`` od klienta zahazují (týž middleware),
  takže podvržená ``X-NC-Client-IP`` nikde nic neovlivní.

``sign_request`` je referenční implementace podepisující strany; gateway (F4,
samostatný adresář ``gateway/``) ji podle D-02 neimportuje, ale musí dávat stejný
výsledek pro testovací vektor v kontraktu.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Final

import structlog
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.platform.http.client_ip import parse_ip

logger = structlog.get_logger(__name__)

SIGNATURE_VERSION: Final = "NC-GW-1"

HEADER_KEY_ID: Final = b"x-nc-gateway-key"
HEADER_TIMESTAMP: Final = b"x-nc-gateway-ts"
HEADER_NONCE: Final = b"x-nc-gateway-nonce"
HEADER_SIGNATURE: Final = b"x-nc-gateway-sig"
HEADER_CLIENT_IP: Final = b"x-nc-client-ip"

GATEWAY_HEADERS: Final = frozenset(
    {HEADER_KEY_ID, HEADER_TIMESTAMP, HEADER_NONCE, HEADER_SIGNATURE, HEADER_CLIENT_IP}
)
# Hlavičky, které by mohly přenášet adresu klienta mimo podepsaný kanál.
_FORWARDING_HEADERS: Final = frozenset(
    {b"x-forwarded-for", b"x-forwarded-proto", b"x-forwarded-host", b"x-real-ip", b"forwarded"}
)

# Klíč v ``scope["state"]``, pod kterým je id ověřeného klíče gateway (jen zóna gateway).
GATEWAY_KEY_ID_STATE: Final = "nc_gateway_key_id"

_KEY_ID_RE: Final = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_NONCE_RE: Final = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SIGNATURE_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_MIN_SECRET_LENGTH: Final = 32

_UNAUTHORIZED_BODY: Final = {"detail": "Invalid gateway signature."}


class GatewayKeyConfigError(ValueError):
    pass


def parse_gateway_keys(raw: str) -> dict[str, bytes]:
    """``NC_GATEWAY_HMAC_KEYS``: ``kid:secret[,kid:secret]`` (víc klíčů = rotace)."""
    keys: dict[str, bytes] = {}
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        key_id, sep, secret = entry.partition(":")
        key_id, secret = key_id.strip(), secret.strip()
        if not sep or not _KEY_ID_RE.match(key_id):
            raise GatewayKeyConfigError(
                "NC_GATEWAY_HMAC_KEYS entries must look like 'kid:secret' with kid [A-Za-z0-9._-]{1,32}."
            )
        if len(secret) < _MIN_SECRET_LENGTH:
            raise GatewayKeyConfigError(
                f"NC_GATEWAY_HMAC_KEYS secret for {key_id!r} is shorter than {_MIN_SECRET_LENGTH} characters."
            )
        if key_id in keys:
            raise GatewayKeyConfigError(f"NC_GATEWAY_HMAC_KEYS lists key id {key_id!r} twice.")
        keys[key_id] = secret.encode("utf-8")
    return keys


def canonical_string(
    *,
    key_id: str,
    timestamp: str,
    nonce: str,
    method: str,
    raw_path: str,
    query_string: str,
    client_ip: str,
    body_sha256: str,
    authorization_sha256: str,
) -> bytes:
    return "\n".join(
        (
            SIGNATURE_VERSION,
            key_id,
            timestamp,
            nonce,
            method.upper(),
            raw_path,
            query_string,
            client_ip,
            body_sha256,
            authorization_sha256,
        )
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sign_request(
    *,
    key_id: str,
    secret: bytes,
    method: str,
    raw_path: str,
    query_string: str = "",
    client_ip: str,
    body: bytes = b"",
    authorization: str | None = None,
    timestamp: int | None = None,
    nonce: str,
) -> dict[str, str]:
    """Hlavičky, které gateway přidá k požadavku na core (referenční implementace)."""
    ts = str(int(time.time()) if timestamp is None else timestamp)
    message = canonical_string(
        key_id=key_id,
        timestamp=ts,
        nonce=nonce,
        method=method,
        raw_path=raw_path,
        query_string=query_string,
        client_ip=client_ip,
        body_sha256=_sha256_hex(body),
        authorization_sha256=_sha256_hex((authorization or "").encode("latin-1")),
    )
    signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return {
        "X-NC-Gateway-Key": key_id,
        "X-NC-Gateway-Ts": ts,
        "X-NC-Gateway-Nonce": nonce,
        "X-NC-Client-IP": client_ip,
        "X-NC-Gateway-Sig": signature,
    }


# ── Replay ochrana ───────────────────────────────────────────────────────────


class NonceStoreUnavailableError(RuntimeError):
    pass


class InMemoryNonceStore:
    """Jednorázové nonce v rámci jednoho procesu (development/test)."""

    def __init__(self, max_entries: int = 100_000) -> None:
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._max = max_entries

    async def claim(self, key: str, ttl_seconds: int) -> bool:
        now = time.monotonic()
        while self._seen:
            oldest_key, expires = next(iter(self._seen.items()))
            if expires > now and len(self._seen) < self._max:
                break
            self._seen.popitem(last=False)
        if key in self._seen:
            return False
        self._seen[key] = now + ttl_seconds
        return True


class RedisNonceStore:
    """Sdílené mezi workery a instancemi: ``SET key 1 NX EX ttl``."""

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def claim(self, key: str, ttl_seconds: int) -> bool:
        try:
            result = await self._redis.set(f"nc:gw:nonce:{key}", "1", nx=True, ex=ttl_seconds)
        except Exception as exc:  # fail closed: bez úložiště nonce nejde vyloučit replay
            raise NonceStoreUnavailableError(type(exc).__name__) from exc
        return bool(result)


# ── Middleware ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Rejection:
    status: int
    reason: str


def _reject(rejection: _Rejection) -> JSONResponse:
    detail = {413: "Request body too large.", 503: "Service temporarily unavailable.", 400: "Bad request."}
    body = {"detail": detail[rejection.status]} if rejection.status in detail else _UNAUTHORIZED_BODY
    return JSONResponse(body, status_code=rejection.status)


class GatewaySignatureMiddleware:
    """Nejvnější vrstva API. V zóně ``gateway`` ověří podpis, jinde hlavičky zahodí.

    Zóna i klíče pocházejí z konfigurace procesu (``NC_ZONE``,
    ``NC_GATEWAY_HMAC_KEYS``), nikdy z požadavku. Po úspěšném ověření nastaví
    ``scope["client"]`` na podepsanou adresu klienta, odstraní z požadavku
    ``X-NC-*`` i forwarding hlavičky (``TrustedProxyMiddleware`` za ní pak
    žádné ``X-Forwarded-For`` nevidí) a předá aplikaci přesně to tělo, jehož
    hash byl podepsán. Mimo zónu gateway jen odstraní ``X-NC-*`` hlavičky
    kontraktu, takže podvržená ``X-NC-Client-IP`` nic neovlivní.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._local_nonces = InMemoryNonceStore()
        self._keys_raw: str | None = None
        self._keys: dict[str, bytes] = {}

    def _settings(self) -> Any:
        from app.platform.config import get_settings

        return get_settings()

    def _current_keys(self, raw: str) -> dict[str, bytes]:
        if raw != self._keys_raw:
            self._keys = parse_gateway_keys(raw)
            self._keys_raw = raw
        return self._keys

    def _nonce_store(self, scope: Scope, strict: bool) -> InMemoryNonceStore | RedisNonceStore | None:
        app = scope.get("app")
        state = getattr(app, "state", None)
        # An explicitly provided store wins (test harnesses whose Redis client was
        # created on another event loop); otherwise the shared Redis client.
        explicit = getattr(state, "gateway_nonce_store", None) if state is not None else None
        if explicit is not None:
            return explicit
        redis = getattr(state, "job_queue", None) if state is not None else None
        if redis is not None:
            return RedisNonceStore(redis)
        if strict:
            return None
        return self._local_nonces

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        from app.platform.http.exposure import ZONE_GATEWAY

        settings = self._settings()
        if settings.effective_nc_zone != ZONE_GATEWAY:
            scope["headers"] = [
                (name, value) for name, value in scope.get("headers", []) if name not in GATEWAY_HEADERS
            ]
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            # Gateway zóna nemá websocket routy; nepodepsatelné spojení odmítnout.
            await send({"type": "websocket.close", "code": 1008})
            return

        self.keys = self._current_keys(settings.nc_gateway_hmac_keys)
        self.max_skew = settings.nc_gateway_sig_max_skew_seconds
        self.max_body = settings.nc_gateway_max_body_bytes
        strict = not settings.is_development

        headers: dict[bytes, list[bytes]] = {}
        for name, value in scope.get("headers", []):
            headers.setdefault(name, []).append(value)

        rejection, verified = await self._verify_headers(scope, headers)
        body = b""
        if rejection is None and verified is not None:
            body, rejection = await self._read_body(receive)
        if rejection is None and verified is not None:
            rejection = await self._verify_signature(scope, headers, verified, body, strict)
        if rejection is not None or verified is None:
            rejection = rejection or _Rejection(401, "unsigned")
            self._log_rejection(scope, rejection)
            await _reject(rejection)(scope, receive, send)
            return

        scope["client"] = (verified["client_ip"], 0)
        # Ověřená identita gateway pro rate limit interních rout (NC-007 kap. 6.4).
        scope.setdefault("state", {})[GATEWAY_KEY_ID_STATE] = verified["key_id"]
        scope["headers"] = [
            (name, value)
            for name, value in scope.get("headers", [])
            if name not in GATEWAY_HEADERS and name not in _FORWARDING_HEADERS
        ]

        delivered = False

        async def replay_body() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_body, send)

    async def _verify_headers(
        self, scope: Scope, headers: dict[bytes, list[bytes]]
    ) -> tuple[_Rejection | None, dict[str, str] | None]:
        values: dict[str, str] = {}
        for name in GATEWAY_HEADERS:
            found = headers.get(name, [])
            if len(found) != 1:
                return _Rejection(401, "missing_or_duplicate_header" if found else "unsigned"), None
            try:
                values[name.decode()] = found[0].decode("ascii").strip()
            except UnicodeDecodeError:
                return _Rejection(401, "non_ascii_header"), None

        key_id = values["x-nc-gateway-key"]
        if key_id not in self.keys:
            return _Rejection(401, "unknown_key"), None
        if not _SIGNATURE_RE.match(values["x-nc-gateway-sig"]):
            return _Rejection(401, "malformed_signature"), None
        if not _NONCE_RE.match(values["x-nc-gateway-nonce"]):
            return _Rejection(401, "malformed_nonce"), None
        ts_raw = values["x-nc-gateway-ts"]
        if not ts_raw.isdigit() or len(ts_raw) > 12:
            return _Rejection(401, "malformed_timestamp"), None
        if abs(int(time.time()) - int(ts_raw)) > self.max_skew:
            return _Rejection(401, "stale_timestamp"), None
        address = parse_ip(values["x-nc-client-ip"])
        if address is None or str(address) != values["x-nc-client-ip"]:
            # Jen kanonický tvar: jinak by šla stejná adresa podepsat víc způsoby.
            return _Rejection(401, "malformed_client_ip"), None
        if len(headers.get(b"authorization", [])) > 1:
            return _Rejection(401, "duplicate_authorization"), None
        return None, {
            "key_id": key_id,
            "timestamp": ts_raw,
            "nonce": values["x-nc-gateway-nonce"],
            "signature": values["x-nc-gateway-sig"],
            "client_ip": values["x-nc-client-ip"],
        }

    async def _read_body(self, receive: Receive) -> tuple[bytes, _Rejection | None]:
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return b"", _Rejection(400, "client_disconnected")
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_body:
                return b"", _Rejection(413, "body_too_large")
            chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks), None

    async def _verify_signature(
        self,
        scope: Scope,
        headers: dict[bytes, list[bytes]],
        verified: dict[str, str],
        body: bytes,
        strict: bool,
    ) -> _Rejection | None:
        raw_path = scope.get("raw_path") or scope.get("path", "").encode("utf-8")
        authorization = headers.get(b"authorization", [b""])[0]
        message = canonical_string(
            key_id=verified["key_id"],
            timestamp=verified["timestamp"],
            nonce=verified["nonce"],
            method=scope.get("method", "GET"),
            raw_path=raw_path.decode("latin-1"),
            query_string=scope.get("query_string", b"").decode("latin-1"),
            client_ip=verified["client_ip"],
            body_sha256=_sha256_hex(body),
            authorization_sha256=_sha256_hex(authorization),
        )
        expected = hmac.new(self.keys[verified["key_id"]], message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, verified["signature"]):
            return _Rejection(401, "bad_signature")

        # Nonce se spotřebuje až po platném podpisu: nepodepsané požadavky ho
        # nemohou "vyčerpat" a zablokovat skutečný požadavek gateway.
        store = self._nonce_store(scope, strict)
        if store is None:
            return _Rejection(503, "nonce_store_unavailable")
        try:
            fresh = await store.claim(
                f"{verified['key_id']}:{verified['nonce']}", ttl_seconds=2 * self.max_skew + 5
            )
        except NonceStoreUnavailableError:
            return _Rejection(503, "nonce_store_unavailable")
        if not fresh:
            return _Rejection(401, "replayed_nonce")
        return None

    @staticmethod
    def _log_rejection(scope: Scope, rejection: _Rejection) -> None:
        log = logger.error if rejection.status == 503 else logger.warning
        log(
            "SECURITY_EVENT: gateway_signature_rejected",
            reason=rejection.reason,
            status=rejection.status,
            method=scope.get("method"),
            path=scope.get("path"),
        )
