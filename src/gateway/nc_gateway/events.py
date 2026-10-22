"""Bezpečnostní události gateway (kontrakt NC-007 kap. 5 a 6.4).

Každá událost se okamžitě zapíše do strukturovaného logu (JSON na stdout)
a zařadí do omezené fronty. Fronta se dávkově (max 50) odesílá na
``POST /api/v1/internal/security-events`` – podepsaně, **bez** hlavičky
``Authorization``. Selhání odeslání se jen zaloguje; požadavek uživatele
nikdy neblokuje (odesílá se na pozadí, ne v cestě požadavku).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Final

from nc_gateway.core_client import CoreClient, CoreUnavailableError

logger = logging.getLogger("nc_gateway.security")

EVENT_TYPES: Final = frozenset(
    {
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
    }
)
EVENTS_PATH: Final = "/api/v1/internal/security-events"
MAX_DETAIL_BYTES: Final = 2048
_SELF_IP: Final = "127.0.0.1"  # X-NC-Client-IP dávky = gateway sama; adresa klienta je v události


def _bounded_detail(detail: dict[str, Any] | None) -> dict[str, Any]:
    if not detail:
        return {}
    encoded = json.dumps(detail, ensure_ascii=False, default=str)
    if len(encoded.encode("utf-8")) <= MAX_DETAIL_BYTES:
        return dict(detail)
    return {"truncated": True}


class SecurityEvents:
    def __init__(
        self,
        core: CoreClient,
        *,
        clock: Callable[[], float],
        batch_size: int = 50,
        max_queue: int = 10_000,
    ) -> None:
        self._core = core
        self._clock = clock
        self._batch_size = min(batch_size, 50)
        self._queue: deque[dict[str, Any]] = deque(maxlen=max_queue)
        self._lock = asyncio.Lock()
        self.dropped = 0
        self.sent = 0
        self.failed_batches = 0

    @property
    def pending(self) -> list[dict[str, Any]]:
        return list(self._queue)

    def emit(
        self,
        event_type: str,
        *,
        client_ip: str | None,
        user_id: str | None = None,
        organization_id: str | None = None,
        session_ref: str | None = None,
        request_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Neznámý typ bezpečnostní události {event_type!r}.")
        event = {
            "type": event_type,
            "occurredAt": datetime.fromtimestamp(self._clock(), tz=UTC).isoformat(),
            "clientIp": client_ip,
            "userId": user_id,
            "organizationId": organization_id,
            "sessionRef": session_ref,
            "requestId": request_id,
            "detail": _bounded_detail(detail),
        }
        level = logging.INFO if event_type in ("login_success", "logout", "logout_all") else logging.WARNING
        logger.log(level, "SECURITY_EVENT", extra={"security_event": event})
        if len(self._queue) == self._queue.maxlen:
            self.dropped += 1
        self._queue.append(event)

    async def flush(self) -> int:
        """Odešle frontu po dávkách. Vrátí počet odeslaných událostí."""
        sent = 0
        async with self._lock:
            while self._queue:
                batch = [self._queue.popleft() for _ in range(min(self._batch_size, len(self._queue)))]
                body = json.dumps({"events": batch}, separators=(",", ":")).encode("utf-8")
                try:
                    response = await self._core.call(
                        "POST",
                        EVENTS_PATH,
                        json_body=body,
                        access_token=None,
                        client_ip=_SELF_IP,
                        request_id=uuid.uuid4().hex,
                    )
                except CoreUnavailableError as exc:
                    self.failed_batches += 1
                    logger.warning(
                        "security_events_delivery_failed",
                        extra={"reason": str(exc), "events": len(batch), "requeued": True},
                    )
                    self._requeue(batch)
                    return sent
                if response.status_code != 202:
                    self.failed_batches += 1
                    # 5xx/429/401(podpis)/503 = přechodná chyba → zkusit znovu příště;
                    # ostatní 4xx (např. 422) by se opakovaly donekonečna → zahodit (jsou v logu).
                    retriable = response.status_code >= 500 or response.status_code in (401, 429)
                    logger.warning(
                        "security_events_delivery_failed",
                        extra={"status": response.status_code, "events": len(batch), "requeued": retriable},
                    )
                    if retriable:
                        self._requeue(batch)
                    return sent
                sent += len(batch)
                self.sent += len(batch)
        return sent

    def _requeue(self, batch: list[dict[str, Any]]) -> None:
        """Vrátí dávku na začátek fronty; při plné frontě se zahodí nejnovější (počítá ``dropped``)."""
        maxlen = self._queue.maxlen or 0
        for event in reversed(batch):
            if len(self._queue) >= maxlen:
                self.dropped += 1
                continue
            self._queue.appendleft(event)

    async def run(self, interval: float) -> None:
        """Smyčka na pozadí (spouští lifespan aplikace)."""
        while True:
            await asyncio.sleep(interval)
            try:
                await self.flush()
            except Exception:
                logger.exception("security_events_flush_crashed")
