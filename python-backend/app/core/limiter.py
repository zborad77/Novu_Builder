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
    """Per-tenant (or per-user) rate limit key for authenticated requests; falls back to IP.

    Priority:
      1. org:<org_id>  -- regular users; all users of the same tenant share one bucket,
                          which matches billing/enforcement semantics.
      2. user:<sub>    -- superadmins (no org claim); independent per-user bucket.
      3. <remote IP>   -- unauthenticated or unparseable token (login, health, etc.)

    The JWT signature is NOT validated here -- the function only reads claims to
    derive a stable bucket key.  An attacker who forges an org/sub claim merely
    isolates themselves to a bucket of their own choosing, which is harmless for
    rate-limiting purposes.  Full auth validation happens independently in
    get_current_user().
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

    limiter = _NoopLimiter()
else:
    # Single shared limiter instance - registered on app.state in main.py.
    # key_func: per-org for authenticated requests, per-user for superadmins,
    # per-IP for unauthenticated.
    limiter = Limiter(key_func=_rate_limit_key, default_limits=[])
