"""FastAPI DI providery sdílené infrastruktury (fronta jobů, Redis)."""

from fastapi import Request


def _request_app_state(request: Request):
    """Best-effort access to ASGI app state.

    Route adapter dependencies may run in direct-call tests or narrow harnesses
    where the Request has no bound ``app``. In that case return ``None`` rather
    than failing on framework wiring.
    """
    app = None
    scope = getattr(request, "scope", None)
    if not isinstance(scope, dict):
        try:
            app = request.app
        except Exception:
            app = None
    else:
        app = scope.get("app")
        if app is None:
            try:
                app = request.app
            except Exception:
                app = None
    return getattr(app, "state", None)


def get_job_queue(request: Request):
    """Return the Redis job queue from app state, or None if unavailable."""
    state = _request_app_state(request)
    return getattr(state, "job_queue", None)


def get_redis(request: Request):
    """Return the shared Redis client for caching (R-32), or None if unavailable.

    Reuses the same connection as the job queue; key prefixes keep them isolated:
      job queue: analysis:jobs
      cache:     cache:*
    """
    state = _request_app_state(request)
    return getattr(state, "job_queue", None)


def get_auth_redis(request: Request):
    """Return the shared Redis client for auth token-state caching."""
    state = _request_app_state(request)
    auth_store = getattr(state, "auth_token_store", None)
    if auth_store is not None:
        return auth_store
    return getattr(state, "job_queue", None)
