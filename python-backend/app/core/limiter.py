import structlog

logger = structlog.get_logger(__name__)

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
except ModuleNotFoundError as exc:
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
