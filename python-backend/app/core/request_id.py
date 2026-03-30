from __future__ import annotations

from uuid import uuid4

REQUEST_ID_MAX_LENGTH = 64


def generate_request_id() -> str:
    return uuid4().hex


def sanitize_request_id(value: str | None) -> str:
    if not value:
        return generate_request_id()

    if len(value) > REQUEST_ID_MAX_LENGTH:
        return generate_request_id()

    if not value.isascii():
        return generate_request_id()

    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        return generate_request_id()

    return value
