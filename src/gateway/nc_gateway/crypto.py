"""Šifrování záznamů session (AES-256-GCM, rotace klíčů, AAD = klíč záznamu).

Formát uložené hodnoty: ``v1.<kid>.<base64url(nonce12 || ciphertext+tag)>``.
První klíč z ``NC_BFF_SESSION_KEYS`` šifruje, ostatní jen dešifrují (rotace).
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Sequence
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION: Final = "v1"
_NONCE_BYTES: Final = 12


class DecryptionError(Exception):
    """Záznam nejde dešifrovat (neznámý klíč, změněná data nebo jiné AAD)."""


class SessionCipher:
    def __init__(self, keys: Sequence[tuple[str, bytes]]) -> None:
        if not keys:
            raise ValueError("SessionCipher potřebuje aspoň jeden klíč.")
        self._primary_kid = keys[0][0]
        self._keys: dict[str, AESGCM] = {kid: AESGCM(key) for kid, key in keys}

    @property
    def primary_kid(self) -> str:
        return self._primary_kid

    def encrypt(self, plaintext: bytes, aad: bytes) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        sealed = self._keys[self._primary_kid].encrypt(nonce, plaintext, aad)
        payload = base64.urlsafe_b64encode(nonce + sealed).decode("ascii")
        return f"{_VERSION}.{self._primary_kid}.{payload}"

    def decrypt(self, token: str, aad: bytes) -> tuple[bytes, str]:
        """Vrátí (plaintext, kid použitého klíče)."""
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != _VERSION:
            raise DecryptionError("format")
        kid, payload = parts[1], parts[2]
        aead = self._keys.get(kid)
        if aead is None:
            raise DecryptionError("unknown_key")
        try:
            raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        except (binascii.Error, ValueError) as exc:
            raise DecryptionError("encoding") from exc
        if len(raw) <= _NONCE_BYTES:
            raise DecryptionError("length")
        try:
            return aead.decrypt(raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], aad), kid
        except InvalidTag as exc:
            raise DecryptionError("tag") from exc
