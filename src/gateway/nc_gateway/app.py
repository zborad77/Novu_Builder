"""NovuConstruct Web Gateway / BFF (kontrakt NC-007 etapa 1).

Čisté ASGI kvůli úplné kontrole nad surovou cestou (``raw_path``), metodami
(žádné automatické ``HEAD``/``OPTIONS``) a hlavičkami v obou směrech.

Veřejné endpointy:

* ``GET  /bff/health``
* ``POST /bff/auth/login``
* ``POST /bff/auth/logout``
* ``POST /bff/auth/logout-all``
* ``GET  /bff/session``
* ``*    /bff/api/<cesta>`` → ``/api/v1/<cesta>`` (allowlist)

Vše ostatní vrací 404. Gateway nikdy neověřuje ani nevyrábí JWT; tokeny
z core zůstávají v šifrované session v Redisu a do prohlížeče nejdou.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import httpx
from redis.asyncio import Redis
from starlette.types import Receive, Scope, Send

from nc_gateway.allowlist import BFF_API_PREFIX, SEGMENT_RE, Allowlist
from nc_gateway.body import RequestBody, read_request_body
from nc_gateway.config import Settings
from nc_gateway.core_client import CoreClient, CoreUnavailableError
from nc_gateway.crypto import SessionCipher
from nc_gateway.events import SecurityEvents
from nc_gateway.store import (
    LoadResult,
    RateLimiter,
    SessionRecord,
    SessionStore,
    StoreUnavailableError,
    session_ref,
    sid_hash,
)
from nc_gateway.web import (
    FORWARD_REQUEST_HEADERS,
    FORWARD_RESPONSE_HEADERS,
    SECURITY_HEADERS,
    SID_RE,
    BodyTooLargeError,
    ClientDisconnectedError,
    RequestContext,
    ResponseTracker,
    build_cookie,
    clear_cookie,
    jwt_claims_hint,
    jwt_exp_hint,
    read_body,
    send_error,
    send_json,
)

logger = logging.getLogger("nc_gateway")

MUTATING_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CORE_API_PREFIX: Final = "/api/v1/"

DETAIL_NOT_FOUND: Final = "Not found."
DETAIL_UNAUTHENTICATED: Final = "Not authenticated."
DETAIL_INVALID_CREDENTIALS: Final = "Invalid credentials."
DETAIL_CSRF: Final = "CSRF validation failed."
CODE_CSRF: Final = "CSRF_FAILED"
DETAIL_ORIGIN: Final = "Origin not allowed."
CODE_ORIGIN: Final = "ORIGIN_REJECTED"
DETAIL_TOO_LARGE: Final = "Request body too large."
DETAIL_MEDIA_TYPE: Final = "Unsupported media type."
DETAIL_BAD_REQUEST: Final = "Bad request."
DETAIL_RATE_LIMITED: Final = "Too many requests."
DETAIL_UPSTREAM_ERROR: Final = "Upstream error."
DETAIL_UPSTREAM_UNAVAILABLE: Final = "Upstream unavailable."
DETAIL_STORE_UNAVAILABLE: Final = "Service temporarily unavailable."
DETAIL_LOGOUT_ALL_PARTIAL: Final = "Logout on other devices was not confirmed."
CODE_LOGOUT_ALL_PARTIAL: Final = "LOGOUT_ALL_PARTIAL"
# Content-Security-Policy pro odpovědi z /bff/api, když ji core neposlal (review L1)
DEFAULT_PROXY_CSP: Final = b"default-src 'none'; frame-ancestors 'none'; sandbox"
LAST_EVENT_ID_RE: Final = re.compile(r"^[0-9A-Za-z:._-]{1,64}$")
EVENT_AGGREGATION_SECONDS: Final = 10

_LOCK_WAIT_INTERVAL: Final = 0.05


class SessionRevokedError(Exception):
    """Core odmítl access i refresh token – session byla smazána."""


class RefreshPendingError(Exception):
    """Na zámek obnovy se čekalo, ale token se nezměnil – 503, bez revokace (review L4)."""


@dataclass
class ActiveSession:
    sid: str
    hashed: str
    record: SessionRecord

    @property
    def ref(self) -> str:
        return session_ref(self.hashed)


def _sha256_short(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


class GatewayApp:
    def __init__(
        self,
        settings: Settings,
        *,
        redis: Redis | None = None,
        core_transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.time,
        allowlist: Allowlist | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.allowlist = allowlist or Allowlist.load(settings.allowlist_path, settings.upload_routes)
        self.redis: Redis = redis or Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        self.core = CoreClient(settings, core_transport)
        self.sessions = SessionStore(
            self.redis,
            SessionCipher(settings.session_keys),
            idle_timeout=settings.idle_timeout_seconds,
            absolute_timeout=settings.absolute_timeout_seconds,
            clock=clock,
        )
        self.limiter = RateLimiter(self.redis, clock)
        self.events = SecurityEvents(self.core, clock=clock, batch_size=settings.events_batch_size)
        self._flusher: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[None]] = set()
        # Zámek obnovy musí přežít celé volání core (timeout + rezerva), čekání stejně dlouho.
        self.lock_ttl_ms = int((settings.core_timeout_seconds + 5) * 1000)
        self.lock_wait_seconds = self.lock_ttl_ms / 1000

    # ── ASGI ────────────────────────────────────────────────────────────────

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        ctx = RequestContext.from_scope(scope, self.settings)
        tracker = ResponseTracker(send)
        try:
            await self._dispatch(ctx, receive, tracker)
        except StoreUnavailableError as exc:
            logger.error("session_store_unavailable", extra={"reason": str(exc), "request_id": ctx.request_id})
            if not tracker.started:
                await send_error(tracker, 503, DETAIL_STORE_UNAVAILABLE, request_id=ctx.request_id)
        except RefreshPendingError:
            logger.warning("refresh_lock_timeout", extra={"request_id": ctx.request_id})
            if not tracker.started:
                await send_error(tracker, 503, DETAIL_STORE_UNAVAILABLE, request_id=ctx.request_id)
        except CoreUnavailableError as exc:
            self._upstream_unavailable(ctx, str(exc))
            if not tracker.started:
                await send_error(tracker, 502, DETAIL_UPSTREAM_UNAVAILABLE, request_id=ctx.request_id)
        except ClientDisconnectedError:
            return
        except Exception:
            logger.exception("unhandled_error", extra={"request_id": ctx.request_id})
            if not tracker.started:
                await send_error(tracker, 500, "Internal error.", request_id=ctx.request_id)

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                self._flusher = asyncio.create_task(self.events.run(self.settings.events_flush_seconds))
                logger.info(
                    "gateway_started",
                    extra={
                        "env": self.settings.env,
                        "public_origin": self.settings.public_origin,
                        "routes": len(self.allowlist.routes),
                        "cookie": self.settings.cookie_name,
                    },
                )
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self.aclose()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def aclose(self) -> None:
        if self._flusher is not None:
            self._flusher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flusher
            self._flusher = None
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.drain_background(), timeout=5)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.events.flush(), timeout=5)
        await self.core.aclose()
        with contextlib.suppress(Exception):
            await self.redis.aclose()

    async def _dispatch(self, ctx: RequestContext, receive: Receive, send: Send) -> None:
        path = ctx.raw_path
        if path.startswith(BFF_API_PREFIX):
            await self._proxy(ctx, receive, send)
            return
        route = (ctx.method, path)
        if route == ("GET", "/bff/health"):
            await send_json(send, 200, {"status": "ok"}, request_id=ctx.request_id)
        elif route == ("POST", "/bff/auth/login"):
            await self._login(ctx, receive, send)
        elif route == ("POST", "/bff/auth/logout"):
            await self._logout(ctx, send)
        elif route == ("POST", "/bff/auth/logout-all"):
            await self._logout_all(ctx, send)
        elif route == ("GET", "/bff/session"):
            await self._session(ctx, send)
        else:
            await send_error(send, 404, DETAIL_NOT_FOUND, request_id=ctx.request_id)

    # ── společné kontroly ───────────────────────────────────────────────────

    def _emit(
        self,
        ctx: RequestContext,
        event_type: str,
        *,
        session: ActiveSession | None = None,
        record: SessionRecord | None = None,
        hashed: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        rec = session.record if session is not None else record
        ref = session.ref if session is not None else (session_ref(hashed) if hashed else None)
        self.events.emit(
            event_type,
            client_ip=ctx.client_ip,
            user_id=rec.userId if rec else None,
            organization_id=rec.organizationId if rec else None,
            session_ref=ref,
            request_id=ctx.request_id,
            detail=detail,
        )

    def _upstream_unavailable(self, ctx: RequestContext, reason: str) -> None:
        logger.error("core_unavailable", extra={"reason": reason, "request_id": ctx.request_id})
        self._emit(ctx, "upstream_unavailable", detail={"reason": reason[:64]})

    async def _emit_aggregated(
        self,
        ctx: RequestContext,
        event_type: str,
        scope: str,
        *,
        session: ActiveSession | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Nejvýš 1 událost na (typ, scope, IP) za 10 s; počet za předchozí okno jde do ``detail``.

        Neautentizovaný provoz tak nejde zesílit do audit_logs core (review M1).
        """
        index = int(self.clock() // EVENT_AGGREGATION_SECONDS)
        base = f"nc:bff:evagg:{event_type}:{scope}:{ctx.client_ip}"
        hits = await self.limiter.counter(f"{base}:{index}", EVENT_AGGREGATION_SECONDS * 3)
        if hits != 1:
            return
        previous = await self.limiter.read(f"{base}:{index - 1}")
        self._emit(
            ctx,
            event_type,
            session=session,
            detail={**(detail or {}), "windowSeconds": EVENT_AGGREGATION_SECONDS, "previousWindowCount": previous},
        )

    def _spawn(self, coro: Any) -> None:
        task: asyncio.Task[None] = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def drain_background(self) -> None:
        """Počká na úlohy na pozadí (testy, ukončení procesu)."""
        while self._background:
            await asyncio.gather(*list(self._background), return_exceptions=True)

    async def _core_logout_best_effort(self, record: SessionRecord, client_ip: str, request_id: str) -> None:
        """Odhlášení session v core po expiraci v gateway (review L6) – chyby jen do logu."""
        body = json.dumps({"refreshToken": record.refreshToken}).encode("utf-8")
        try:
            response = await self.core.call(
                "POST",
                "/api/v1/auth/logout",
                json_body=body,
                access_token=record.accessToken,
                client_ip=client_ip,
                request_id=request_id,
            )
            if response.status_code != 200:
                logger.warning("core_logout_after_expiry_failed", extra={"status": response.status_code})
        except CoreUnavailableError as exc:
            logger.warning("core_logout_after_expiry_failed", extra={"reason": str(exc)})

    def _origin_ok(self, ctx: RequestContext) -> bool:
        if ctx.header_count("origin") > 1:
            return False
        origin = ctx.header("origin")
        if origin is not None:
            return origin == self.settings.public_origin
        return ctx.header("sec-fetch-site") == "same-origin"

    def _csrf_ok(self, ctx: RequestContext, session: ActiveSession) -> bool:
        if ctx.header_count("x-csrf-token") != 1:
            return False
        token = ctx.header("x-csrf-token") or ""
        return hmac.compare_digest(token.encode("utf-8"), session.record.csrfSecret.encode("utf-8"))

    def _session_cookie(self, ctx: RequestContext) -> str | None:
        value = ctx.cookie(self.settings.cookie_name)
        if value is None:
            return None
        return value if SID_RE.match(value) else ""

    async def _load_session(self, ctx: RequestContext) -> tuple[ActiveSession | None, bool]:
        """(session, cookie_present). Expirovaná session se smaže a zapíše událost."""
        sid = self._session_cookie(ctx)
        if sid is None:
            return None, False
        if sid == "":
            return None, True
        result: LoadResult = await self.sessions.load(sid)
        if result.status == "expired":
            self._emit(
                ctx,
                "session_expired",
                record=result.record,
                hashed=result.hashed,
                detail={"reason": result.expiry_reason},
            )
            if result.record is not None:
                self._spawn(self._core_logout_best_effort(result.record, ctx.client_ip, ctx.request_id))
            return None, True
        if result.status != "ok" or result.record is None:
            return None, True
        return ActiveSession(sid=sid, hashed=result.hashed, record=result.record), True

    async def _touch(self, session: ActiveSession) -> bool:
        record = await self.sessions.touch(session.hashed)
        if record is None:
            return False
        session.record = record
        return True

    async def _rate_limit(
        self, ctx: RequestContext, send: Send, session: ActiveSession | None, *, include_ip: bool = True
    ) -> bool:
        """Session 300/min, IP 600/min. Vrátí ``False``, pokud už odešla 429."""
        checks: list[tuple[str, str, int, int]] = []
        if include_ip:
            checks.append(("ip", ctx.client_ip, self.settings.rate_ip.limit, self.settings.rate_ip.window_seconds))
        if session is not None:
            checks.insert(
                0,
                ("sess", session.hashed, self.settings.rate_session.limit, self.settings.rate_session.window_seconds),
            )
        for scope_name, ident, limit, window in checks:
            decision = await self.limiter.hit(scope_name, ident, limit, window)
            if not decision.allowed:
                await self._emit_aggregated(
                    ctx, "rate_limited", scope_name, session=session, detail={"scope": scope_name}
                )
                await send_error(
                    send,
                    429,
                    DETAIL_RATE_LIMITED,
                    request_id=ctx.request_id,
                    extra_headers=[(b"retry-after", str(decision.retry_after).encode("ascii"))],
                )
                return False
        return True

    async def _unauthenticated(self, ctx: RequestContext, send: Send, *, clear: bool) -> None:
        extra = [(b"set-cookie", clear_cookie(self.settings).encode("latin-1"))] if clear else None
        await send_error(send, 401, DETAIL_UNAUTHENTICATED, request_id=ctx.request_id, extra_headers=extra)

    # ── obnova tokenu a revokace ────────────────────────────────────────────

    async def _revoke(self, ctx: RequestContext, session: ActiveSession, reason: str) -> None:
        await self.sessions.delete(session.hashed, session.record.userId)
        self._emit(ctx, "session_revoked", session=session, detail={"reason": reason})

    async def _reload(self, session: ActiveSession) -> bool:
        result = await self.sessions.load(session.sid)
        if result.status != "ok" or result.record is None:
            return False
        session.record = result.record
        return True

    async def _refresh(self, ctx: RequestContext, session: ActiveSession, stale_access: str) -> None:
        """Obnoví access token (jednou, se zámkem ``nc:bff:lock:<hash>``).

        * Jiný požadavek už obnovil → použije se jeho token.
        * Core odmítne refresh (400/401/403) → session smazána, ``SessionRevokedError``.
        * Core nedostupný / 5xx → ``CoreUnavailableError`` (502, session zůstává).
        """
        lock = await self.sessions.acquire_lock(session.hashed, ttl_ms=self.lock_ttl_ms)
        if lock is None:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.lock_wait_seconds
            while loop.time() < deadline:
                await asyncio.sleep(_LOCK_WAIT_INTERVAL)
                if not await self.sessions.lock_held(session.hashed):
                    break
            if not await self._reload(session):
                raise SessionRevokedError
            if session.record.accessToken == stale_access:
                # Obnova jiného požadavku nedoběhla: neopakovat se starým tokenem, nerevokovat.
                raise RefreshPendingError
            return
        try:
            if not await self._reload(session):
                raise SessionRevokedError
            if session.record.accessToken != stale_access:
                return  # mezitím obnovil jiný požadavek
            body = json.dumps({"refreshToken": session.record.refreshToken}).encode("utf-8")
            response = await self.core.call(
                "POST",
                "/api/v1/auth/refresh",
                json_body=body,
                client_ip=ctx.client_ip,
                request_id=ctx.request_id,
            )
            if response.status_code in (400, 401, 403):
                await self._revoke(ctx, session, "refresh_rejected")
                raise SessionRevokedError
            if response.status_code != 200:
                raise CoreUnavailableError(f"refresh_status_{response.status_code}")
            try:
                data = response.json()
                access = str(data["accessToken"])
                refresh = str(data["refreshToken"])
                user = data.get("user") or {}
            except (ValueError, KeyError, TypeError) as exc:
                raise CoreUnavailableError("refresh_malformed") from exc
            core_sid = data.get("sessionId") or jwt_claims_hint(access).get("sid")

            def mutate(record: SessionRecord) -> None:
                record.accessToken = access
                record.refreshToken = refresh
                if isinstance(user, dict) and isinstance(user.get("role"), str):
                    record.role = user["role"]
                if isinstance(core_sid, str):
                    record.coreSessionId = core_sid

            updated = await self.sessions.update(session.hashed, mutate)
            if updated is None:
                raise SessionRevokedError
            session.record = updated
        finally:
            await self.sessions.release_lock(session.hashed, lock)

    async def _ensure_fresh(self, ctx: RequestContext, session: ActiveSession) -> None:
        exp = jwt_exp_hint(session.record.accessToken)
        if exp is not None and exp - self.clock() < self.settings.refresh_leeway_seconds:
            await self._refresh(ctx, session, session.record.accessToken)

    async def _core_authenticated(
        self,
        ctx: RequestContext,
        session: ActiveSession,
        method: str,
        path: str,
        json_body: bytes | None = None,
    ) -> httpx.Response:
        """Volání core jménem session s obnovou před expirací i po 401 (jednou)."""
        await self._ensure_fresh(ctx, session)
        used = session.record.accessToken
        response = await self.core.call(
            method, path, json_body=json_body, access_token=used, client_ip=ctx.client_ip, request_id=ctx.request_id
        )
        if response.status_code != 401:
            return response
        await self._refresh(ctx, session, used)
        response = await self.core.call(
            method,
            path,
            json_body=json_body,
            access_token=session.record.accessToken,
            client_ip=ctx.client_ip,
            request_id=ctx.request_id,
        )
        if response.status_code == 401:
            await self._revoke(ctx, session, "access_rejected")
            raise SessionRevokedError
        return response

    # ── /bff/auth/login ─────────────────────────────────────────────────────

    async def _login(self, ctx: RequestContext, receive: Receive, send: Send) -> None:
        if not self._origin_ok(ctx):
            self._emit(ctx, "origin_failure", detail={"endpoint": "login"})
            await send_error(send, 403, DETAIL_ORIGIN, code=CODE_ORIGIN, request_id=ctx.request_id)
            return
        if ctx.media_type() != "application/json":
            await send_error(send, 415, DETAIL_MEDIA_TYPE, request_id=ctx.request_id)
            return
        if not await self._check_declared_length(ctx, send, self.settings.login_body_limit):
            return
        try:
            raw = await read_body(receive, self.settings.login_body_limit)
        except BodyTooLargeError:
            await send_error(send, 413, DETAIL_TOO_LARGE, request_id=ctx.request_id)
            return

        try:
            payload = json.loads(raw)
            email = payload["email"]
            password = payload["password"]
            if not isinstance(email, str) or not isinstance(password, str) or not email or not password:
                raise TypeError
        except (ValueError, KeyError, TypeError):
            await send_error(send, 400, DETAIL_BAD_REQUEST, request_id=ctx.request_id)
            return
        if len(email) > 320 or len(password) > 1024:
            await send_error(send, 400, DETAIL_BAD_REQUEST, request_id=ctx.request_id)
            return

        # Klíč login-ip vzniká až po základní validaci těla (review L8).
        ip_limit = self.settings.rate_login_ip
        decision = await self.limiter.hit("login-ip", ctx.client_ip, ip_limit.limit, ip_limit.window_seconds)
        if not decision.allowed:
            await self._emit_aggregated(ctx, "rate_limited", "login-ip", detail={"scope": "login-ip"})
            await send_error(
                send,
                429,
                DETAIL_RATE_LIMITED,
                request_id=ctx.request_id,
                extra_headers=[(b"retry-after", str(decision.retry_after).encode("ascii"))],
            )
            return

        # Limit neúspěchů na e-mail atomicky (review L5): pokus se započítá PŘED voláním
        # core, takže souběžné pokusy limit nepřeskočí. Neskončí-li špatnými údaji, odečte se.
        email_key = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
        email_limit = self.settings.rate_login_email_failures
        email_decision = await self.limiter.hit("login-email", email_key, email_limit.limit, email_limit.window_seconds)
        if not email_decision.allowed:
            await self.limiter.undo("login-email", email_key, email_limit.window_seconds)
            await self._emit_aggregated(ctx, "rate_limited", "login-email", detail={"scope": "login-email"})
            await send_error(
                send,
                429,
                DETAIL_RATE_LIMITED,
                request_id=ctx.request_id,
                extra_headers=[(b"retry-after", str(email_decision.retry_after).encode("ascii"))],
            )
            return

        body = json.dumps({"email": email, "password": password}).encode("utf-8")
        try:
            response = await self.core.call(
                "POST", "/api/v1/auth/login", json_body=body, client_ip=ctx.client_ip, request_id=ctx.request_id
            )
        except CoreUnavailableError:
            await self.limiter.undo("login-email", email_key, email_limit.window_seconds)
            raise
        if response.status_code not in (400, 401, 403, 404, 422):
            await self.limiter.undo("login-email", email_key, email_limit.window_seconds)
        else:
            self._emit(ctx, "login_failure", detail={"coreStatus": response.status_code})
            await send_error(send, 401, DETAIL_INVALID_CREDENTIALS, request_id=ctx.request_id)
            return
        if response.status_code == 429:
            retry = response.headers.get("retry-after", "60")
            await self._emit_aggregated(ctx, "rate_limited", "core-login", detail={"scope": "core-login"})
            await send_error(
                send,
                429,
                DETAIL_RATE_LIMITED,
                request_id=ctx.request_id,
                extra_headers=[(b"retry-after", retry.encode("latin-1") if retry.isdigit() else b"60")],
            )
            return
        if response.status_code != 200:
            status = response.status_code if response.status_code >= 500 else 502
            await send_error(send, status, DETAIL_UPSTREAM_ERROR, request_id=ctx.request_id)
            return
        try:
            data = response.json()
            access = str(data["accessToken"])
            refresh = str(data["refreshToken"])
            user = data["user"]
            user_id = str(user["id"])
            organization_id = str(user.get("organizationId") or "")
            role = str(user.get("role") or "")
        except (ValueError, KeyError, TypeError):
            logger.error("core_login_malformed", extra={"request_id": ctx.request_id})
            await send_error(send, 502, DETAIL_UPSTREAM_ERROR, request_id=ctx.request_id)
            return

        # Fixation: příchozí cookie se ignoruje a její záznam se smaže.
        old_sid = self._session_cookie(ctx)
        if old_sid:
            old = await self.sessions.load(old_sid)
            await self.sessions.delete(old.hashed, old.record.userId if old.record else None)

        now = self.clock()
        core_sid = data.get("sessionId") or jwt_claims_hint(access).get("sid")
        csrf_secret = secrets.token_urlsafe(32)
        record = SessionRecord(
            accessToken=access,
            refreshToken=refresh,
            userId=user_id,
            organizationId=organization_id,
            role=role,
            csrfSecret=csrf_secret,
            createdAt=now,
            lastSeenAt=now,
            ipHash=_sha256_short(ctx.client_ip),
            uaHash=_sha256_short(ctx.header("user-agent") or ""),
            coreSessionId=core_sid if isinstance(core_sid, str) else None,
        )
        sid, hashed = await self.sessions.create(record)
        self._emit(ctx, "login_success", record=record, hashed=hashed)
        await send_json(
            send,
            200,
            {"user": user, "csrfToken": csrf_secret},
            request_id=ctx.request_id,
            extra_headers=[(b"set-cookie", build_cookie(self.settings, sid).encode("latin-1"))],
        )

    async def _check_declared_length(self, ctx: RequestContext, send: Send, limit: int) -> bool:
        declared = ctx.header("content-length")
        if declared is None:
            return True
        if not declared.isdigit() or ctx.header_count("content-length") > 1:
            await send_error(send, 400, DETAIL_BAD_REQUEST, request_id=ctx.request_id)
            return False
        if int(declared) > limit:
            await send_error(send, 413, DETAIL_TOO_LARGE, request_id=ctx.request_id)
            return False
        return True

    # ── /bff/auth/logout, /bff/auth/logout-all ──────────────────────────────

    async def _authenticated_mutation(self, ctx: RequestContext, send: Send) -> ActiveSession | None:
        """Session + Origin + CSRF + rate limit pro mutace na /bff/auth/*."""
        session, cookie_present = await self._load_session(ctx)
        if session is None:
            await self._unauthenticated(ctx, send, clear=cookie_present)
            return None
        if not self._origin_ok(ctx):
            self._emit(ctx, "origin_failure", session=session)
            await send_error(send, 403, DETAIL_ORIGIN, code=CODE_ORIGIN, request_id=ctx.request_id)
            return None
        if not self._csrf_ok(ctx, session):
            self._emit(ctx, "csrf_failure", session=session)
            await send_error(send, 403, DETAIL_CSRF, code=CODE_CSRF, request_id=ctx.request_id)
            return None
        if not await self._rate_limit(ctx, send, session):
            return None
        return session

    async def _logout(self, ctx: RequestContext, send: Send) -> None:
        session = await self._authenticated_mutation(ctx, send)
        if session is None:
            return
        body = json.dumps({"refreshToken": session.record.refreshToken}).encode("utf-8")
        try:
            response = await self.core.call(
                "POST",
                "/api/v1/auth/logout",
                json_body=body,
                access_token=session.record.accessToken,
                client_ip=ctx.client_ip,
                request_id=ctx.request_id,
            )
            if response.status_code != 200:
                logger.warning("core_logout_failed", extra={"status": response.status_code})
        except CoreUnavailableError as exc:
            self._upstream_unavailable(ctx, str(exc))
        await self.sessions.delete(session.hashed, session.record.userId)
        self._emit(ctx, "logout", session=session)
        await send_json(
            send,
            204,
            None,
            request_id=ctx.request_id,
            extra_headers=[(b"set-cookie", clear_cookie(self.settings).encode("latin-1"))],
        )

    async def _logout_all(self, ctx: RequestContext, send: Send) -> None:
        session = await self._authenticated_mutation(ctx, send)
        if session is None:
            return
        clear = [(b"set-cookie", clear_cookie(self.settings).encode("latin-1"))]
        core_ok = True
        revoked_remote = 0
        try:
            listing = await self._core_authenticated(ctx, session, "GET", "/api/v1/auth/sessions")
            if listing.status_code != 200:
                core_ok = False
                logger.warning("core_list_sessions_failed", extra={"status": listing.status_code})
            else:
                items = listing.json().get("items", [])
                for item in items if isinstance(items, list) else []:
                    remote_id = item.get("id") if isinstance(item, dict) else None
                    if not isinstance(remote_id, str) or not SEGMENT_RE.match(remote_id):
                        continue
                    if item.get("revokedAt") or item.get("isCurrent"):
                        continue
                    deleted = await self.core.call(
                        "DELETE",
                        f"/api/v1/auth/sessions/{remote_id}",
                        access_token=session.record.accessToken,
                        client_ip=ctx.client_ip,
                        request_id=ctx.request_id,
                    )
                    if deleted.status_code in (200, 404):
                        revoked_remote += 1
                    else:
                        core_ok = False
            body = json.dumps({"refreshToken": session.record.refreshToken}).encode("utf-8")
            logout = await self.core.call(
                "POST",
                "/api/v1/auth/logout",
                json_body=body,
                access_token=session.record.accessToken,
                client_ip=ctx.client_ip,
                request_id=ctx.request_id,
            )
            core_ok = core_ok and logout.status_code == 200
        except SessionRevokedError:
            core_ok = True  # core session už neplatí
        except CoreUnavailableError as exc:
            core_ok = False
            self._upstream_unavailable(ctx, str(exc))
        except ValueError:
            core_ok = False
        removed = await self.sessions.delete_all_for_user(session.record.userId)
        self._emit(
            ctx,
            "logout_all",
            session=session,
            detail={"gatewaySessions": removed, "coreSessions": revoked_remote, "coreOk": core_ok},
        )
        if not core_ok:
            # Lokální sessions jsou pryč, ale core se nepodařilo odhlásit všude.
            await send_error(
                send,
                502,
                DETAIL_LOGOUT_ALL_PARTIAL,
                code=CODE_LOGOUT_ALL_PARTIAL,
                request_id=ctx.request_id,
                extra_headers=clear,
            )
            return
        await send_json(send, 204, None, request_id=ctx.request_id, extra_headers=clear)

    # ── /bff/session ────────────────────────────────────────────────────────

    async def _session(self, ctx: RequestContext, send: Send) -> None:
        session, cookie_present = await self._load_session(ctx)
        clear = [(b"set-cookie", clear_cookie(self.settings).encode("latin-1"))]
        if session is None:
            await send_json(
                send,
                200,
                {"authenticated": False},
                request_id=ctx.request_id,
                extra_headers=clear if cookie_present else None,
            )
            return
        if not await self._rate_limit(ctx, send, session):
            return
        if not await self._touch(session):
            await send_json(send, 200, {"authenticated": False}, request_id=ctx.request_id, extra_headers=clear)
            return
        try:
            response = await self._core_authenticated(ctx, session, "GET", "/api/v1/auth/me")
        except SessionRevokedError:
            await send_json(send, 200, {"authenticated": False}, request_id=ctx.request_id, extra_headers=clear)
            return
        if response.status_code != 200:
            status = response.status_code if response.status_code >= 500 else 502
            await send_error(send, status, DETAIL_UPSTREAM_ERROR, request_id=ctx.request_id)
            return
        try:
            user = response.json()
        except ValueError:
            await send_error(send, 502, DETAIL_UPSTREAM_ERROR, request_id=ctx.request_id)
            return
        await send_json(
            send,
            200,
            {
                "authenticated": True,
                "user": user,
                "csrfToken": session.record.csrfSecret,
                "expiresAt": _iso(self.sessions.expires_at(session.record)),
                "idleExpiresAt": _iso(self.sessions.idle_expires_at(session.record)),
            },
            request_id=ctx.request_id,
        )

    # ── /bff/api/* ──────────────────────────────────────────────────────────

    async def _proxy(self, ctx: RequestContext, receive: Receive, send: Send) -> None:
        rid = ctx.request_id
        core_path = CORE_API_PREFIX + ctx.raw_path[len(BFF_API_PREFIX) :]

        # 0. IP rate limit před allowlistem – neautentizovaný flood nejde zesílit (review M1)
        if not await self._rate_limit(ctx, send, None):
            return

        # 1. allowlist
        route = self.allowlist.match(ctx.method, core_path)
        if route is None:
            await self._emit_aggregated(
                ctx, "allowlist_miss", "api", detail={"method": ctx.method[:16], "path": ctx.raw_path[:256]}
            )
            await send_error(send, 404, DETAIL_NOT_FOUND, request_id=rid)
            return
        if not _query_ok(ctx.query):
            await send_error(send, 400, DETAIL_BAD_REQUEST, request_id=rid)
            return

        # 2. velikost těla jen z deklarované Content-Length (tělo se zatím nečte)
        media = ctx.media_type()
        is_upload = self.allowlist.is_upload(route)
        multipart = media == "multipart/form-data"
        limit = self.settings.multipart_body_limit if (multipart and is_upload) else self.settings.json_body_limit
        if not await self._check_declared_length(ctx, send, limit):
            return

        # 3. Content-Type těla (tělo = nenulová Content-Length nebo Transfer-Encoding)
        declared = ctx.header("content-length")
        has_body = (declared is not None and declared != "0") or ctx.header("transfer-encoding") is not None
        if has_body and not (media == "application/json" or (multipart and is_upload)):
            await send_error(send, 415, DETAIL_MEDIA_TYPE, request_id=rid)
            return

        # 4. session
        session, cookie_present = await self._load_session(ctx)
        if session is None:
            await self._unauthenticated(ctx, send, clear=cookie_present)
            return

        # 5. Origin + CSRF u mutací
        if ctx.method in MUTATING_METHODS:
            if not self._origin_ok(ctx):
                self._emit(ctx, "origin_failure", session=session, detail={"path": route.path})
                await send_error(send, 403, DETAIL_ORIGIN, code=CODE_ORIGIN, request_id=rid)
                return
            if not self._csrf_ok(ctx, session):
                self._emit(ctx, "csrf_failure", session=session, detail={"path": route.path})
                await send_error(send, 403, DETAIL_CSRF, code=CODE_CSRF, request_id=rid)
                return

        # 6. rate limit na session (IP už v kroku 0)
        if not await self._rate_limit(ctx, send, session, include_ip=False):
            return

        if not await self._touch(session):
            await self._unauthenticated(ctx, send, clear=True)
            return

        # Tělo až teď: po session a CSRF, s průběžným limitem (chunked) a mimo paměť (review M2).
        try:
            body = await read_request_body(receive, limit)
        except BodyTooLargeError:
            await send_error(send, 413, DETAIL_TOO_LARGE, request_id=rid)
            return
        try:
            await self._forward(ctx, session, route.path, core_path, body, send)
        finally:
            body.close()

    async def _forward(
        self,
        ctx: RequestContext,
        session: ActiveSession,
        template: str,
        core_path: str,
        body: RequestBody,
        send: Send,
    ) -> None:
        # 7. hlavičky do core + podpis, obnova tokenu
        forward: dict[str, str] = {}
        for name in FORWARD_REQUEST_HEADERS:
            value = ctx.header(name)
            if value is not None:
                forward[name] = value
        sse = template.endswith("/activity/stream") or "text/event-stream" in (ctx.header("accept") or "")
        if sse:
            last_event_id = ctx.header("last-event-id")
            if last_event_id is not None and LAST_EVENT_ID_RE.match(last_event_id):
                forward["last-event-id"] = last_event_id  # SSE reconnect (QA F-1); jinak zahodit
        read_timeout = self.settings.sse_idle_timeout_seconds if sse else None
        try:
            await self._ensure_fresh(ctx, session)
            response = await self._send_proxied(ctx, session, core_path, body, forward, read_timeout)
            if response.status_code == 401:
                await response.aclose()
                await self._refresh(ctx, session, session.record.accessToken)
                response = await self._send_proxied(ctx, session, core_path, body, forward, read_timeout)
                if response.status_code == 401:
                    await response.aclose()
                    await self._revoke(ctx, session, "access_rejected")
                    raise SessionRevokedError
        except SessionRevokedError:
            await self._unauthenticated(ctx, send, clear=True)
            return

        # 8. odpověď
        await self._stream_response(ctx, response, send)

    async def _send_proxied(
        self,
        ctx: RequestContext,
        session: ActiveSession,
        core_path: str,
        body: RequestBody,
        headers: dict[str, str],
        read_timeout: float | None,
    ) -> httpx.Response:
        request = self.core.build(
            ctx.method,
            core_path,
            query=ctx.query,
            stream_body=body if body.length else None,
            headers=headers,
            access_token=session.record.accessToken,
            client_ip=ctx.client_ip,
            request_id=ctx.request_id,
            read_timeout=read_timeout,
        )
        return await self.core.send(request, stream=True)

    async def _stream_response(self, ctx: RequestContext, response: httpx.Response, send: Send) -> None:
        try:
            if response.status_code >= 500:
                retry_after = response.headers.get("retry-after")
                extra = (
                    [(b"retry-after", retry_after.encode("latin-1"))] if retry_after and retry_after.isdigit() else None
                )
                logger.warning(
                    "core_error_masked", extra={"status": response.status_code, "request_id": ctx.request_id}
                )
                await send_error(
                    send, response.status_code, DETAIL_UPSTREAM_ERROR, request_id=ctx.request_id, extra_headers=extra
                )
                return
            headers: list[tuple[bytes, bytes]] = list(SECURITY_HEADERS)
            has_request_id = False
            has_cache_control = False
            has_csp = False
            for name, value in response.headers.raw:
                lname = name.lower()
                if lname not in FORWARD_RESPONSE_HEADERS:
                    continue
                if lname == b"x-request-id":
                    has_request_id = True
                elif lname == b"cache-control":
                    has_cache_control = True
                elif lname == b"content-security-policy":
                    has_csp = True
                headers.append((lname, value))
            if not has_csp:
                headers.append((b"content-security-policy", DEFAULT_PROXY_CSP))
            if not has_request_id:
                headers.append((b"x-request-id", ctx.request_id.encode("ascii")))
            if not has_cache_control:
                headers.append((b"cache-control", b"no-store"))
            if response.headers.get("content-type", "").startswith("text/event-stream"):
                headers.append((b"x-accel-buffering", b"no"))  # nginx edge nesmí SSE bufferovat
            await send({"type": "http.response.start", "status": response.status_code, "headers": headers})
            try:
                async for chunk in response.aiter_raw():
                    if chunk:
                        await send({"type": "http.response.body", "body": chunk, "more_body": True})
            except httpx.TransportError as exc:
                # Hlavička už odešla – spojení se jen ukončí (klient uvidí useknutou odpověď).
                logger.warning("core_stream_interrupted", extra={"reason": type(exc).__name__})
                return
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            await response.aclose()


_QUERY_SAFE: Final = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~!$&'()*+,;=:@/?%")


def _query_ok(query: str) -> bool:
    """Query se předává beze změny, ale jen ze znaků RFC 3986 (jinak by ho httpx překódoval)."""
    return len(query) <= 4096 and all(ch in _QUERY_SAFE for ch in query)


def create_app(
    settings: Settings,
    *,
    redis: Redis | None = None,
    core_transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.time,
) -> GatewayApp:
    return GatewayApp(settings, redis=redis, core_transport=core_transport, clock=clock)


__all__ = ["GatewayApp", "create_app", "sid_hash"]
