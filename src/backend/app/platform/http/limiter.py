import base64
import json
import os
from typing import Any

import structlog

from app.platform.config import startup_failure_message

logger = structlog.get_logger(__name__)
_NON_STRICT_ENVIRONMENTS: frozenset[str] = frozenset({"development", "test"})


def _is_strict_environment() -> bool:
    app_env = os.environ.get("APP_ENV", "development").strip().lower() or "development"
    return app_env not in _NON_STRICT_ENVIRONMENTS


def client_ip_rate_limit_key(request) -> str:
    """Bucket by client address only, ignoring any Authorization header.

    Mandatory for routes that do not authenticate the caller (login, refresh,
    logout, password reset): there the bearer token is never verified, so keying
    on its claims would let a forged header pick a fresh bucket per request and
    bypass the per-IP limit (SA-03).
    """
    if request.client:
        return request.client.host
    return "unknown"


def gateway_key_rate_limit_key(request) -> str:
    """Bucket per ověřený klíč gateway (interní routy zóny gateway, NC-007 kap. 6.4).

    Id klíče nastaví ``GatewaySignatureMiddleware`` až po platném podpisu, takže
    ho volající nemůže podvrhnout. Mimo zónu gateway (dev/testy) adresa klienta.
    """
    from app.platform.http.gateway_auth import GATEWAY_KEY_ID_STATE

    key_id = getattr(request.state, GATEWAY_KEY_ID_STATE, None)
    if isinstance(key_id, str) and key_id:
        return f"gateway:{key_id}"
    return client_ip_rate_limit_key(request)


def _rate_limit_key(request) -> str:
    """Per-tenant (or per-user) rate limit key for authenticated requests; falls back to IP.

    Priority:
      1. org:<org_id>  -- regular users; all users of the same tenant share one bucket,
                          which matches billing/enforcement semantics.
      2. user:<sub>    -- superadmins (no org claim); independent per-user bucket.
      3. <remote IP>   -- unauthenticated or unparseable token.

    The JWT signature is NOT validated here -- the function only reads claims to
    derive a stable bucket key. That is acceptable only on routes whose
    dependencies reject a forged token before the handler does any work. Routes
    that accept unauthenticated callers must use client_ip_rate_limit_key.
    """
    try:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization[7:]
            parts = token.split(".")
            if len(parts) == 3:
                payload_b64 = parts[1]
                # Restore standard base64 padding
                padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
                payload = json.loads(base64.urlsafe_b64decode(padded))
                # Prefer org claim (per-tenant bucket) -- present for all non-superadmin users.
                org = payload.get("org")
                if org and isinstance(org, str) and org.strip():
                    return f"org:{org.strip()}"
                # Superadmins have no org: fall back to per-user bucket.
                sub = payload.get("sub")
                if sub and isinstance(sub, str) and sub.strip():
                    return f"user:{sub.strip()}"
    except Exception:
        pass
    # Fallback: use remote address (unauthenticated, or JWT parse failed)
    if request.client:
        return request.client.host
    return "unknown"


try:
    from slowapi import Limiter
except ModuleNotFoundError as exc:
    if _is_strict_environment():
        raise RuntimeError(
            startup_failure_message(
                "rate_limiter",
                "slowapi must be installed so auth and admin rate limiting cannot be silently disabled.",
            )
        ) from exc
    logger.warning("rate_limiter.disabled", reason="slowapi_not_installed", error=str(exc))

    class _NoopLimiter:
        def limit(self, *_args, **_kwargs):
            def decorator(func):
                return func
            return decorator

    limiter: Any = _NoopLimiter()
else:
    from app.platform.config import get_settings

    # Single shared limiter instance - registered on app.state in main.py.
    # key_func: per-org for authenticated requests, per-user for superadmins,
    # per-IP for unauthenticated.
    # Counters live in Redis outside development/test so every worker process
    # shares them (SA-05). No in-memory fallback: if Redis is unreachable the
    # check raises and the request fails closed (503 via main.py).
    limiter = Limiter(
        key_func=_rate_limit_key,
        default_limits=[],
        storage_uri=get_settings().effective_rate_limit_storage_uri,
        in_memory_fallback_enabled=False,
        swallow_errors=False,
    )
