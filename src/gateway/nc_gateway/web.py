"""Pomocné funkce pro ASGI: kontext požadavku, klientská IP, cookies, odpovědi."""

from __future__ import annotations

import base64
import ipaddress
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Final

from starlette.types import Receive, Scope, Send

from nc_gateway.config import TRUSTED_PROXY_UNIX, Settings

SID_RE: Final = re.compile(r"^[A-Za-z0-9_-]{43}$")

# Hlavičky z prohlížeče, které smějí do core (kontrakt kap. 4 bod 7).
FORWARD_REQUEST_HEADERS: Final = ("content-type", "accept", "if-none-match", "range", "if-range")
# Hlavičky z core, které smějí do prohlížeče (kontrakt kap. 4 bod 8).
FORWARD_RESPONSE_HEADERS: Final = frozenset(
    {
        b"content-type",
        b"content-length",
        b"content-disposition",
        b"content-range",
        b"accept-ranges",
        b"etag",
        b"last-modified",
        b"cache-control",
        b"retry-after",
        b"x-request-id",
        b"content-security-policy",
    }
)
SECURITY_HEADERS: Final = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
)


def canonical_ip(value: str) -> str | None:
    """Kanonický tvar IP (IPv4-mapped IPv6 jako IPv4), jinak ``None``."""
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        return str(mapped)
    if isinstance(address, ipaddress.IPv6Address) and address.scope_id:
        return None
    return str(address)


def resolve_client_ip(scope: Scope, headers: dict[str, list[str]], trusted_proxy: str | None) -> str:
    """Adresa klienta **jen** ze spojení.

    ``X-Forwarded-For`` se čte výhradně tehdy, když spojení přichází z
    ``NC_BFF_TRUSTED_PROXY`` (přesně jedna adresa lokálního nginx, nebo
    ``unix`` pro unixový socket), a použije se jeho **poslední** hodnota –
    tu připsal nginx sám, předchozí mohl podvrhnout klient.
    """
    client = scope.get("client")
    peer = canonical_ip(client[0]) if client and client[0] else None
    peer_key = peer if peer is not None else TRUSTED_PROXY_UNIX
    if trusted_proxy is not None and peer_key == trusted_proxy:
        forwarded = ",".join(headers.get("x-forwarded-for", []))
        if forwarded:
            candidate = canonical_ip(forwarded.split(",")[-1])
            if candidate is not None:
                return candidate
    # Unixový socket bez důvěryhodné proxy = lokální spojení.
    return peer if peer is not None else "127.0.0.1"


@dataclass
class RequestContext:
    method: str
    raw_path: str
    query: str
    headers: dict[str, list[str]]
    client_ip: str
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def from_scope(cls, scope: Scope, settings: Settings) -> RequestContext:
        headers: dict[str, list[str]] = {}
        for name, value in scope.get("headers", []):
            headers.setdefault(name.decode("latin-1").lower(), []).append(value.decode("latin-1"))
        raw_path_bytes = scope.get("raw_path") or scope.get("path", "/").encode("utf-8")
        raw_path = raw_path_bytes.decode("latin-1").split("?", 1)[0]
        return cls(
            method=str(scope.get("method", "GET")).upper(),
            raw_path=raw_path,
            query=scope.get("query_string", b"").decode("latin-1"),
            headers=headers,
            client_ip=resolve_client_ip(scope, headers, settings.trusted_proxy),
        )

    def header(self, name: str) -> str | None:
        values = self.headers.get(name)
        return values[0] if values else None

    def header_count(self, name: str) -> int:
        return len(self.headers.get(name, []))

    def media_type(self) -> str | None:
        value = self.header("content-type")
        if value is None:
            return None
        return value.split(";", 1)[0].strip().lower() or None

    def cookie(self, name: str) -> str | None:
        for header in self.headers.get("cookie", []):
            for part in header.split(";"):
                key, sep, value = part.strip().partition("=")
                if sep and key == name:
                    return value.strip()
        return None


def build_cookie(settings: Settings, sid: str) -> str:
    parts = [f"{settings.cookie_name}={sid}", "Path=/", "HttpOnly", "SameSite=Strict"]
    if settings.cookie_secure:
        parts.append("Secure")
    return "; ".join(parts)


def clear_cookie(settings: Settings) -> str:
    parts = [
        f"{settings.cookie_name}=",
        "Path=/",
        "Max-Age=0",
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
        "HttpOnly",
        "SameSite=Strict",
    ]
    if settings.cookie_secure:
        parts.append("Secure")
    return "; ".join(parts)


def jwt_claims_hint(token: str) -> dict[str, Any]:
    """Payload JWT **bez ověření podpisu** – jen nápověda (``exp`` pro obnovu, ``sid``).

    Nikdy se nepoužívá pro autorizaci; o platnosti tokenu rozhoduje jen core.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, UnicodeError):
        return {}
    return data if isinstance(data, dict) else {}


def jwt_exp_hint(token: str) -> float | None:
    exp = jwt_claims_hint(token).get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        return None
    return float(exp)


class ResponseTracker:
    """Obal ``send``, který si pamatuje, zda už odešel začátek odpovědi."""

    def __init__(self, send: Send) -> None:
        self._send = send
        self.started = False

    async def __call__(self, message: Any) -> None:
        if message["type"] == "http.response.start":
            self.started = True
        await self._send(message)


async def send_json(
    send: Send,
    status: int,
    body: dict[str, Any] | None,
    *,
    request_id: str,
    no_store: bool = True,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    payload = b"" if body is None else json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers: list[tuple[bytes, bytes]] = list(SECURITY_HEADERS)
    headers.append((b"x-request-id", request_id.encode("ascii")))
    if no_store:
        headers.append((b"cache-control", b"no-store"))
    if body is not None:
        headers.append((b"content-type", b"application/json"))
    if status != 204:
        headers.append((b"content-length", str(len(payload)).encode("ascii")))
    headers.extend(extra_headers or [])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload, "more_body": False})


async def send_error(
    send: Send,
    status: int,
    detail: str,
    *,
    request_id: str,
    code: str | None = None,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    body: dict[str, Any] = {"detail": detail}
    if code is not None:
        body["code"] = code
    body["requestId"] = request_id
    await send_json(
        send,
        status,
        body,
        request_id=request_id,
        extra_headers=extra_headers,
    )


class BodyTooLargeError(Exception):
    pass


class ClientDisconnectedError(Exception):
    pass


async def read_body(receive: Receive, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            raise ClientDisconnectedError
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > limit:
            raise BodyTooLargeError
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)
