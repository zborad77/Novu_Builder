import base64
import json
import os

import structlog

from app.core.config import startup_failure_message

logger = structlog.get_logger(__name__)
_NON_STRICT_ENVIRONMENTS: frozenset[str] = frozenset({"development", "test"})


def _is_strict_environment() -> bool:
    app_env = os.environ.get("APP_ENV", "development").strip().lower() or "development"
    return app_env not in _NON_STRICT_ENVIRONMENTS


def _rate_limit_key(request) -> str:
    """Per-user rate limit key for authenticated requests; falls back to IP.

    For authenticated endpoints the JWT sub claim is used as the bucket key so
    that multiple users behind the same NAT/proxy have independent quotas.
    The JWT signature is NOT validated here — this function only reads the sub
    claim to derive a stable per-user bucket.  Full auth validation happens
    independently in get_current_user().  An attacker who forges a sub claim
    merely isolates themselves to a bucket of their own choosing, which is
    harmless for rate-limiting purposes.

    Unauthenticated requests (missing or malformed Authorization header) fall
    back to the remote IP address so that pre-auth endpoints (login, health)
    are still protected.
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
    from slowapi.util import get_remote_address
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

    limiter = _NoopLimiter()
else:
    # Single shared limiter instance - registered on app.state in main.py.
    # key_func: per-user for authenticated requests, per-IP for unauthenticated.
    limiter = Limiter(key_func=_rate_limit_key, default_limits=[])
