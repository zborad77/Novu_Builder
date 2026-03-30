import os

import structlog

from app.core.config import startup_failure_message

logger = structlog.get_logger(__name__)
_NON_STRICT_ENVIRONMENTS: frozenset[str] = frozenset({"development", "test"})


def _is_strict_environment() -> bool:
    app_env = os.environ.get("APP_ENV", "development").strip().lower() or "development"
    return app_env not in _NON_STRICT_ENVIRONMENTS

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
    # Single shared limiter instance - registered on app.state in main.py
    limiter = Limiter(key_func=get_remote_address, default_limits=[])
