"""HMAC podpis požadavků gateway → core.

Kontrakt: docs/security/GATEWAY_CORE_CONTRACT.md kap. 2 a 3. Implementace je
napsaná nezávisle na core (D-02: žádný import z ``src/backend``); shodu
ověřuje testovací vektor z kap. 5 kontraktu.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Final

SIGNATURE_VERSION: Final = "NC-GW-1"
EMPTY_SHA256: Final = hashlib.sha256(b"").hexdigest()

HEADER_KEY_ID: Final = "X-NC-Gateway-Key"
HEADER_TIMESTAMP: Final = "X-NC-Gateway-Ts"
HEADER_NONCE: Final = "X-NC-Gateway-Nonce"
HEADER_CLIENT_IP: Final = "X-NC-Client-IP"
HEADER_SIGNATURE: Final = "X-NC-Gateway-Sig"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def new_nonce() -> str:
    """24 B náhodných dat v base64url (32 znaků, ``[A-Za-z0-9_-]``)."""
    return secrets.token_urlsafe(24)


def canonical_string(
    *,
    key_id: str,
    timestamp: str,
    nonce: str,
    method: str,
    raw_path: str,
    query_string: str,
    client_ip: str,
    body: bytes,
    authorization: str | None,
    body_sha256: str | None = None,
) -> bytes:
    """Deset polí oddělených ``\\n`` bez koncového ``\\n`` (kap. 3).

    ``body_sha256`` = předem spočítaný hash těla (streamovaný upload), jinak se hashuje ``body``.
    """
    fields = (
        SIGNATURE_VERSION,
        key_id,
        timestamp,
        nonce,
        method.upper(),
        raw_path,
        query_string,
        client_ip,
        body_sha256 if body_sha256 is not None else sha256_hex(body),
        sha256_hex((authorization or "").encode("latin-1")),
    )
    return "\n".join(fields).encode("utf-8")


def sign(
    *,
    key_id: str,
    secret: bytes,
    method: str,
    raw_path: str,
    query_string: str,
    client_ip: str,
    body: bytes,
    authorization: str | None,
    timestamp: int | None = None,
    nonce: str | None = None,
    body_sha256: str | None = None,
) -> dict[str, str]:
    """Vrátí hlavičky ``X-NC-*`` pro jeden požadavek (vždy nové nonce, pokud není dáno)."""
    ts = str(int(time.time()) if timestamp is None else timestamp)
    used_nonce = nonce if nonce is not None else new_nonce()
    message = canonical_string(
        key_id=key_id,
        timestamp=ts,
        nonce=used_nonce,
        method=method,
        raw_path=raw_path,
        query_string=query_string,
        client_ip=client_ip,
        body=body,
        authorization=authorization,
        body_sha256=body_sha256,
    )
    signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return {
        HEADER_KEY_ID: key_id,
        HEADER_TIMESTAMP: ts,
        HEADER_NONCE: used_nonce,
        HEADER_CLIENT_IP: client_ip,
        HEADER_SIGNATURE: signature,
    }
