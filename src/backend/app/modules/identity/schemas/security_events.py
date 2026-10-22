"""Bezpečnostní události z gateway (NC-007 etapa 1, kap. 6.4)."""

from __future__ import annotations

import json
from datetime import datetime
from ipaddress import ip_address
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_SECURITY_EVENTS_PER_BATCH = 50
MAX_SECURITY_EVENT_DETAIL_BYTES = 2048

SecurityEventType = Literal[
    "login_success",
    "login_failure",
    "logout",
    "logout_all",
    "session_expired",
    "session_revoked",
    "csrf_failure",
    "origin_failure",
    "allowlist_miss",
    "rate_limited",
    "upstream_unavailable",
]


class SecurityEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: SecurityEventType
    occurredAt: datetime
    clientIp: str = Field(min_length=1, max_length=64)
    userId: str | None = Field(default=None, max_length=64)
    organizationId: str | None = Field(default=None, max_length=64)
    # Prvních 16 hex znaků sha256(sid) – nikdy samotné sid.
    sessionRef: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    requestId: str | None = Field(default=None, max_length=128)
    detail: dict[str, Any] = Field(default_factory=dict)

    @field_validator("clientIp")
    @classmethod
    def _client_ip_is_an_address(cls, value: str) -> str:
        try:
            return str(ip_address(value.strip()))
        except ValueError as exc:
            raise ValueError("clientIp must be an IPv4 or IPv6 address.") from exc

    @field_validator("detail")
    @classmethod
    def _detail_is_small(cls, value: dict[str, Any]) -> dict[str, Any]:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(serialized.encode("utf-8")) > MAX_SECURITY_EVENT_DETAIL_BYTES:
            raise ValueError(f"detail exceeds {MAX_SECURITY_EVENT_DETAIL_BYTES} bytes when serialized.")
        return value


class SecurityEventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[SecurityEventIn] = Field(max_length=MAX_SECURITY_EVENTS_PER_BATCH)


class SecurityEventsAccepted(BaseModel):
    accepted: int
