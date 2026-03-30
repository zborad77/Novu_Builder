import logging
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_JWT_SECRET = "change-me-in-production"
_STARTUP_FAILURE_PREFIX = "Startup validation failed"
_NON_STRICT_ENVIRONMENTS: frozenset[str] = frozenset({"development", "test"})
_REDIS_URL_SCHEMES: frozenset[str] = frozenset({"redis", "rediss"})
_DATABASE_ASYNC_SCHEMES: frozenset[str] = frozenset({"postgresql+asyncpg"})
_DATABASE_SYNC_SCHEMES: frozenset[str] = frozenset({"postgresql+psycopg", "postgresql", "postgres"})
_PLACEHOLDER_HOST_SUFFIXES: frozenset[str] = frozenset({"example.com", "example.org", "example.net"})
_PLACEHOLDER_HOST_FRAGMENTS: frozenset[str] = frozenset({"yourdomain"})

# ---------------------------------------------------------------------------
# Insecure-placeholder detection
# ---------------------------------------------------------------------------

# Substring fragments that, when found in a secret/password value, indicate it
# was never replaced from a template.  Checked case-insensitively.
_PLACEHOLDER_FRAGMENTS: frozenset[str] = frozenset({
    "change-me",
    "changeme",
    "change_me",
    "placeholder",
})

# ---------------------------------------------------------------------------
# Worker DB pool model — separate pool, session lifecycle fix
# ---------------------------------------------------------------------------
# The backend uses TWO isolated DB engines that never share connections:
#
#   API engine  (engine / AsyncSessionFactory)
#       Sized by DB_POOL_SIZE + DB_MAX_OVERFLOW.
#       Session lifetime ≈ one HTTP request (~100 ms).
#
#   Worker engine  (worker_engine / WorkerAsyncSessionFactory)
#       Sized by effective_worker_db_pool_size, max_overflow = 0.
#       Session lifetime ≈ one DB unit-of-work (~50 ms).
#       Never held during AI analysis calls (up to 180 s).
#
# Session lifecycle inside execute_job (the key design constraint):
#   Phase 1  fetch job + mark running        → short session, then CLOSED
#   Phase 2  AI analysis                     → NO DB connection held
#   Phase 3  persist result or failure       → short session, then CLOSED
#
# This eliminates pool starvation entirely: workers never hold connections
# while waiting for the AI provider, so the pool is free for the API.
#
# Worker pool sizing:
#   WORKER_DB_POOL_SIZE = 0 (default) → auto-derived as WORKER_CONCURRENCY.
#   max_overflow is always 0: the worker pool is exactly sized, predictable,
#   and never thrashes with transient overflow connections.
#
# Multi-instance deployments (Kubernetes, multiple pods):
#   Total worker DB connections = WORKER_CONCURRENCY × WORKER_INSTANCE_COUNT.
#   Set WORKER_INSTANCE_COUNT so the guard can log the real total and warn
#   when it approaches PostgreSQL max_connections.

# Short tokens that are insecure only when they are the *entire* value
# (avoiding false positives inside legitimate longer strings like hostnames).
_PLACEHOLDER_EXACT: frozenset[str] = frozenset({
    "secret",
    "password",
    "default",
})


def _is_insecure_placeholder(value: str) -> bool:
    """Return True if *value* is a well-known insecure placeholder string.

    Designed for security-critical settings only.  Conservative by design:
    flags obvious 'change-me' fragments or exact short placeholder tokens.
    """
    lower = value.strip().lower()
    if _is_wrapped_placeholder(lower):
        return True
    if lower in _PLACEHOLDER_EXACT:
        return True
    return any(frag in lower for frag in _PLACEHOLDER_FRAGMENTS)


def _is_wrapped_placeholder(value: str) -> bool:
    stripped = value.strip()
    return len(stripped) > 2 and stripped.startswith("<") and stripped.endswith(">")


def _url_password(url: str) -> str | None:
    """Extract the password component from a URL string, or None if absent."""
    try:
        return urlparse(url).password
    except Exception:
        return None


def _url_hostname(url: str) -> str | None:
    """Extract the hostname component from a URL string, or None if absent."""
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def _url_path(url: str) -> str:
    """Extract the URL path component, or an empty string on parse failure."""
    try:
        return urlparse(url).path
    except Exception:
        return ""


def _url_scheme(url: str) -> str:
    """Extract the URL scheme component, or an empty string on parse failure."""
    try:
        return urlparse(url).scheme.lower()
    except Exception:
        return ""


def _is_sqlite_in_memory_url(url: str) -> bool:
    candidate = url.strip()
    if not _url_scheme(candidate).startswith("sqlite"):
        return False

    lower = candidate.lower()
    path = _url_path(candidate).lower()
    return path == "/:memory:" or ":memory:" in lower or "mode=memory" in lower


def _is_strict_environment(app_env: str) -> bool:
    return app_env.lower() not in _NON_STRICT_ENVIRONMENTS


def _looks_like_placeholder_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False

    normalized = hostname.strip().strip(".").lower()
    if not normalized:
        return False
    if normalized in _PLACEHOLDER_HOST_SUFFIXES:
        return True
    if any(normalized.endswith(f".{suffix}") for suffix in _PLACEHOLDER_HOST_SUFFIXES):
        return True
    return any(fragment in normalized for fragment in _PLACEHOLDER_HOST_FRAGMENTS)


def _looks_like_placeholder_url(url: str) -> bool:
    stripped = url.strip()
    if _is_wrapped_placeholder(stripped):
        return True
    return _looks_like_placeholder_hostname(_url_hostname(stripped))


def startup_failure_message(check: str, detail: str) -> str:
    return f"{_STARTUP_FAILURE_PREFIX} [{check}]: {detail}"


def _settings_validation_message(exc: ValidationError) -> str:
    details: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "__root__")
        message = error.get("msg", "Invalid configuration value.")
        details.append(f"{location}: {message}" if location else message)
    return startup_failure_message("config", "; ".join(details) if details else str(exc))


def _env_files() -> list[Path]:
    """
    Load .env first (dev defaults), then overlay .env.<APP_ENV> if it exists.
    Real environment variables always win over both files (pydantic-settings default).
    Example: APP_ENV=production → loads .env then .env.production
    """
    base = _BACKEND_ROOT / ".env"
    app_env = os.environ.get("APP_ENV", "")
    override = _BACKEND_ROOT / f".env.{app_env}" if app_env else None
    files: list[Path] = []
    if base.exists():
        files.append(base)
    if override and override.exists():
        files.append(override)
    return files


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    app_name: str = Field(default="FotoNabidka API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    database_url: str = Field(default="sqlite+aiosqlite:///./python-backend.db", alias="DATABASE_URL")
    database_url_sync_override: str | None = Field(default=None, alias="DATABASE_URL_SYNC")
    db_auto_create_schema: bool = Field(default=True, alias="DB_AUTO_CREATE_SCHEMA")
    db_seed_on_startup: bool = Field(default=True, alias="DB_SEED_ON_STARTUP")
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=1800, alias="DB_POOL_RECYCLE")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_socket_connect_timeout: float = Field(default=1.0, alias="REDIS_SOCKET_CONNECT_TIMEOUT")
    redis_socket_timeout: float = Field(default=1.0, alias="REDIS_SOCKET_TIMEOUT")
    redis_health_check_interval: int = Field(default=30, alias="REDIS_HEALTH_CHECK_INTERVAL")
    redis_retry_attempts: int = Field(default=3, alias="REDIS_RETRY_ATTEMPTS")
    redis_retry_backoff_base: float = Field(default=0.05, alias="REDIS_RETRY_BACKOFF_BASE")
    redis_retry_backoff_cap: float = Field(default=0.5, alias="REDIS_RETRY_BACKOFF_CAP")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="", alias="LOG_FILE")
    log_error_file: str = Field(default="", alias="LOG_ERROR_FILE")
    storage_root: str = Field(default="", alias="STORAGE_ROOT")
    ai_analysis_provider: str = Field(default="mock", alias="AI_ANALYSIS_PROVIDER")
    worker_concurrency: int = Field(default=1, alias="WORKER_CONCURRENCY")
    # Worker-specific DB pool (separate engine, isolated from API pool).
    # 0 = auto-derive pool size from WORKER_CONCURRENCY (recommended default).
    worker_db_pool_size: int = Field(default=0, alias="WORKER_DB_POOL_SIZE")
    worker_db_pool_timeout: int = Field(default=30, alias="WORKER_DB_POOL_TIMEOUT")
    # Total number of worker processes pointing at the same DB server.
    # Used by the capacity guard to compute total DB connection consumption.
    # Example: 3 Kubernetes pods x WORKER_CONCURRENCY=4 → WORKER_INSTANCE_COUNT=3
    worker_instance_count: int = Field(default=1, alias="WORKER_INSTANCE_COUNT")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    max_upload_size_mb: int = Field(default=20, alias="MAX_UPLOAD_SIZE_MB")
    jwt_secret: str = Field(default=_DEFAULT_JWT_SECRET, alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=60, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    jwt_refresh_token_expire_days: int = Field(default=30, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS")

    # CORS — comma-separated list of allowed origins.
    # Dev default allows local backend origin; production must set this explicitly.
    cors_allowed_origins: str = Field(
        default="http://localhost:8000,http://127.0.0.1:8000",
        alias="CORS_ALLOWED_ORIGINS",
    )

    # Security hardening
    require_https: bool = Field(default=False, alias="REQUIRE_HTTPS")
    hsts_max_age: int = Field(default=31536000, alias="HSTS_MAX_AGE")  # 1 year

    # Rate limiting (requests / window per IP)
    rate_limit_login: str = Field(default="10/minute", alias="RATE_LIMIT_LOGIN")
    rate_limit_admin: str = Field(default="60/minute", alias="RATE_LIMIT_ADMIN")
    rate_limit_admin_write: str = Field(default="10/minute", alias="RATE_LIMIT_ADMIN_WRITE")
    rate_limit_admin_sensitive: str = Field(default="5/minute", alias="RATE_LIMIT_ADMIN_SENSITIVE")
    rate_limit_upload: str = Field(default="30/minute", alias="RATE_LIMIT_UPLOAD")

    # Email — password reset and transactional emails (C7)
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="noreply@example.com", alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    password_reset_expire_minutes: int = Field(default=60, alias="PASSWORD_RESET_EXPIRE_MINUTES")
    # Base URL of the web client that handles /reset-password?token=…
    # Must be set to the deployed frontend URL in any environment where email reset is used.
    app_base_url: str = Field(default="http://localhost:8000", alias="APP_BASE_URL")

    # Storage backend — "local" (default) or "s3"
    storage_backend: str = Field(default="local", alias="STORAGE_BACKEND")
    s3_bucket: str = Field(default="", alias="S3_BUCKET")
    s3_endpoint_url: str = Field(default="", alias="S3_ENDPOINT_URL")  # leave empty for AWS S3
    s3_access_key_id: str = Field(default="", alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str = Field(default="", alias="S3_SECRET_ACCESS_KEY")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    s3_cdn_base_url: str = Field(default="", alias="S3_CDN_BASE_URL")  # deprecated: incompatible with signed URL policy
    s3_connect_timeout_seconds: float = Field(default=3.0, alias="S3_CONNECT_TIMEOUT_SECONDS")
    s3_read_timeout_seconds: float = Field(default=10.0, alias="S3_READ_TIMEOUT_SECONDS")
    storage_signed_url_ttl_seconds: int = Field(default=3600, alias="STORAGE_SIGNED_URL_TTL_SECONDS")
    storage_authoritative: bool | None = Field(default=None, alias="STORAGE_AUTHORITATIVE")
    export_ttl_days: int = Field(default=7, alias="EXPORT_TTL_DAYS")

    # Prometheus /metrics auth guard (R-SEC-01)
    # Set METRICS_AUTH_ENABLED=true and a strong METRICS_AUTH_TOKEN in production.
    # Configure Prometheus scrape_configs with bearer_token to match.
    metrics_auth_enabled: bool = Field(default=True, alias="METRICS_AUTH_ENABLED")
    metrics_auth_token: str | None = Field(default=None, alias="METRICS_AUTH_TOKEN")

    # Error monitoring — leave empty to disable Sentry (default: off)
    sentry_dsn: str | None = Field(default=None, alias="SENTRY_DSN")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def database_url_sync(self) -> str:
        if self.database_url_sync_override:
            return self.database_url_sync_override

        if self.database_url.startswith("sqlite+aiosqlite:///"):
            return self.database_url.replace("sqlite+aiosqlite:///", "sqlite:///")

        if self.database_url.startswith("postgresql+asyncpg://"):
            return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)

        return self.database_url

    @property
    def database_engine_kwargs(self) -> dict[str, bool | int]:
        kwargs: dict[str, bool | int] = {"pool_pre_ping": True}

        # SQLite in-memory URLs rely on StaticPool, which rejects queue-pool tuning kwargs.
        if _is_sqlite_in_memory_url(self.database_url):
            return kwargs

        kwargs.update(
            pool_size=self.db_pool_size,
            max_overflow=self.db_max_overflow,
            pool_timeout=self.db_pool_timeout,
            pool_recycle=self.db_pool_recycle,
        )
        return kwargs

    @property
    def effective_worker_db_pool_size(self) -> int:
        """Pool size for the worker-dedicated DB engine.

        When WORKER_DB_POOL_SIZE=0 (default), auto-derived as WORKER_CONCURRENCY
        so that every concurrent worker slot has exactly one pooled connection.
        The worker pool always uses max_overflow=0: it is exactly sized,
        predictable, and avoids transient overflow connection churn.
        """
        if self.worker_db_pool_size > 0:
            return self.worker_db_pool_size
        return self.worker_concurrency

    @property
    def worker_database_engine_kwargs(self) -> dict[str, bool | int]:
        """Engine kwargs for the worker-dedicated DB pool.

        max_overflow=0 is intentional: the worker pool is exactly sized.
        If all slots are occupied, the next acquire blocks for pool_timeout
        seconds, then raises — which is the correct fail-fast behaviour.
        SQLite in-memory uses StaticPool and ignores these kwargs.
        """
        kwargs: dict[str, bool | int] = {"pool_pre_ping": True}
        if _is_sqlite_in_memory_url(self.database_url):
            return kwargs
        kwargs.update(
            pool_size=self.effective_worker_db_pool_size,
            max_overflow=0,
            pool_timeout=self.worker_db_pool_timeout,
            pool_recycle=self.db_pool_recycle,
        )
        return kwargs

    @model_validator(mode="after")
    def _check_debug_in_production(self) -> "Settings":
        if self.app_debug and _is_strict_environment(self.app_env):
            raise ValueError(
                f"APP_DEBUG=True is not allowed outside development. "
                f"Set APP_DEBUG=False (current APP_ENV={self.app_env!r})."
            )
        return self

    @model_validator(mode="after")
    def _check_jwt_secret(self) -> "Settings":
        if not _is_strict_environment(self.app_env):
            return self

        errors: list[str] = []
        if self.jwt_secret == _DEFAULT_JWT_SECRET:
            errors.append(
                "JWT_SECRET must be changed from the built-in default value. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        elif _is_insecure_placeholder(self.jwt_secret):
            errors.append(
                f"JWT_SECRET looks like an unfilled placeholder ({self.jwt_secret!r}). "
                "Set a strong, unique secret."
            )
        elif len(self.jwt_secret) < 32:
            errors.append(
                f"JWT_SECRET is too short ({len(self.jwt_secret)} chars); "
                "minimum 32 characters required in production."
            )
        if errors:
            raise ValueError(
                f"Invalid JWT_SECRET for APP_ENV={self.app_env!r}: "
                + "; ".join(errors)
            )
        return self

    @model_validator(mode="after")
    def _check_metrics_auth_token(self) -> "Settings":
        """Fail-fast in production when the metrics guard is on but has no valid token."""
        if not _is_strict_environment(self.app_env):
            return self
        if not self.metrics_auth_enabled:
            raise ValueError(
                f"METRICS_AUTH_ENABLED must remain true in APP_ENV={self.app_env!r}. "
                "/metrics must not be exposed without authentication outside development/test."
            )

        token = (self.metrics_auth_token or "").strip()
        if not token:
            raise ValueError(
                f"METRICS_AUTH_TOKEN must be set when METRICS_AUTH_ENABLED=true "
                f"in APP_ENV={self.app_env!r}. "
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if _is_insecure_placeholder(self.metrics_auth_token):
            raise ValueError(
                f"METRICS_AUTH_TOKEN contains an insecure placeholder value "
                f"in APP_ENV={self.app_env!r}. Set a strong, unique token."
            )
        if len(token) < 32:
            raise ValueError(
                f"METRICS_AUTH_TOKEN is too short ({len(token)} chars); "
                "minimum 32 characters required outside development/test."
            )
        return self

    @model_validator(mode="after")
    def _check_redis_url(self) -> "Settings":
        """Require an authenticated Redis URL in production."""
        if not _is_strict_environment(self.app_env):
            return self

        candidate = self.redis_url.strip()
        if not candidate:
            raise ValueError(
                f"REDIS_URL must be set in APP_ENV={self.app_env!r}. "
                "Set REDIS_URL=redis://:yourpassword@host:port/db"
            )
        scheme = _url_scheme(candidate)
        if scheme not in _REDIS_URL_SCHEMES:
            raise ValueError(
                f"REDIS_URL must use redis:// or rediss:// in APP_ENV={self.app_env!r}. "
                "Set REDIS_URL=redis://:yourpassword@host:port/db"
            )
        if not _url_hostname(candidate):
            raise ValueError(
                f"REDIS_URL must include a Redis host in APP_ENV={self.app_env!r}. "
                "Set REDIS_URL=redis://:yourpassword@host:port/db"
            )

        password = _url_password(candidate)
        if password is None or password == "":
            raise ValueError(
                f"REDIS_URL must include a password in APP_ENV={self.app_env!r}. "
                "Set REDIS_URL=redis://:yourpassword@host:port/db"
            )
        if _is_insecure_placeholder(password):
            raise ValueError(
                f"REDIS_URL contains an insecure placeholder password "
                f"in APP_ENV={self.app_env!r}. Set a strong Redis password."
            )
        if len(password) < 16:
            raise ValueError(
                f"REDIS_URL password is too short ({len(password)} chars); "
                "minimum 16 characters required outside development/test."
            )
        return self

    @model_validator(mode="after")
    def _check_redis_client_tuning(self) -> "Settings":
        if self.redis_socket_connect_timeout <= 0:
            raise ValueError(
                "REDIS_SOCKET_CONNECT_TIMEOUT must be > 0 so Redis connection attempts "
                "fail fast instead of hanging indefinitely."
            )
        if self.redis_socket_timeout <= 0:
            raise ValueError(
                "REDIS_SOCKET_TIMEOUT must be > 0 so backend Redis calls have a real I/O timeout."
            )
        if self.redis_health_check_interval < 0:
            raise ValueError(
                "REDIS_HEALTH_CHECK_INTERVAL must be >= 0."
            )
        if self.redis_retry_attempts < 0:
            raise ValueError(
                "REDIS_RETRY_ATTEMPTS must be >= 0."
            )
        if self.redis_retry_backoff_base <= 0:
            raise ValueError(
                "REDIS_RETRY_BACKOFF_BASE must be > 0."
            )
        if self.redis_retry_backoff_cap <= 0:
            raise ValueError(
                "REDIS_RETRY_BACKOFF_CAP must be > 0."
            )
        if self.redis_retry_backoff_cap < self.redis_retry_backoff_base:
            raise ValueError(
                "REDIS_RETRY_BACKOFF_CAP must be >= REDIS_RETRY_BACKOFF_BASE."
            )
        return self

    @model_validator(mode="after")
    def _check_database_url(self) -> "Settings":
        """Reject unsafe DB URLs outside development/test."""
        if not _is_strict_environment(self.app_env):
            return self

        def _validate_database_url(label: str, url: str, *, require_async: bool) -> None:
            candidate = url.strip()
            if not candidate:
                raise ValueError(
                    f"{label} must be set in APP_ENV={self.app_env!r}. "
                    "Configure an explicit PostgreSQL connection string."
                )

            scheme = _url_scheme(candidate)
            if scheme.startswith("sqlite"):
                raise ValueError(
                    f"{label} must not use SQLite in APP_ENV={self.app_env!r}. "
                    "Configure PostgreSQL explicitly and run Alembic before startup."
                )
            if require_async:
                if scheme not in _DATABASE_ASYNC_SCHEMES:
                    raise ValueError(
                        f"{label} must use a PostgreSQL async driver "
                        f"(postgresql+asyncpg://...) in APP_ENV={self.app_env!r}."
                    )
            elif scheme not in _DATABASE_SYNC_SCHEMES:
                raise ValueError(
                    f"{label} must use a PostgreSQL sync driver "
                    f"(postgresql+psycopg://... or postgresql://...) in APP_ENV={self.app_env!r}."
                )
            if not _url_hostname(candidate):
                raise ValueError(
                    f"{label} must include a database host in APP_ENV={self.app_env!r}."
                )
            if not _url_path(candidate).lstrip("/"):
                raise ValueError(
                    f"{label} must include a database name in APP_ENV={self.app_env!r}."
                )

            password = _url_password(candidate)
            if password == "":
                raise ValueError(
                    f"{label} must not use an empty password in APP_ENV={self.app_env!r}. "
                    "Set real database credentials or omit the password entirely for external auth."
                )
            if password is not None and _is_insecure_placeholder(password):
                raise ValueError(
                    f"{label} contains an insecure placeholder password "
                    f"in APP_ENV={self.app_env!r}. Set real database credentials."
                )

        _validate_database_url("DATABASE_URL", self.database_url, require_async=True)
        if self.database_url_sync_override is not None:
            _validate_database_url("DATABASE_URL_SYNC", self.database_url_sync_override, require_async=False)

        return self

    @model_validator(mode="after")
    def _check_database_pool_tuning(self) -> "Settings":
        if self.db_pool_size <= 0:
            raise ValueError("DB_POOL_SIZE must be > 0.")
        if self.db_max_overflow < 0:
            raise ValueError("DB_MAX_OVERFLOW must be >= 0.")
        if self.db_pool_timeout <= 0:
            raise ValueError("DB_POOL_TIMEOUT must be > 0.")
        if self.db_pool_recycle != -1 and self.db_pool_recycle <= 0:
            raise ValueError("DB_POOL_RECYCLE must be -1 or > 0.")
        return self

    @model_validator(mode="after")
    def _check_upload_limits(self) -> "Settings":
        if self.max_upload_size_mb <= 0:
            raise ValueError(
                "MAX_UPLOAD_SIZE_MB must be a positive integer so backend upload "
                "validation can enforce a real size limit."
            )
        return self

    @model_validator(mode="after")
    def _check_export_ttl_days(self) -> "Settings":
        if self.export_ttl_days <= 0:
            raise ValueError(
                "EXPORT_TTL_DAYS must be > 0 so expired exports have a deterministic cleanup window."
            )
        return self

    @model_validator(mode="after")
    def _check_worker_concurrency(self) -> "Settings":
        if self.worker_concurrency <= 0:
            raise ValueError(
                "WORKER_CONCURRENCY must be > 0."
            )
        return self

    @model_validator(mode="after")
    def _check_worker_db_params(self) -> "Settings":
        """Validate worker-specific DB pool parameters."""
        if self.worker_db_pool_size < 0:
            raise ValueError(
                "WORKER_DB_POOL_SIZE must be >= 0. "
                "Use 0 (default) to auto-derive from WORKER_CONCURRENCY, "
                "or set an explicit positive value."
            )
        if self.worker_db_pool_timeout <= 0:
            raise ValueError(
                "WORKER_DB_POOL_TIMEOUT must be > 0 so worker DB acquire "
                "attempts fail fast instead of hanging indefinitely."
            )
        if self.worker_instance_count < 1:
            raise ValueError(
                "WORKER_INSTANCE_COUNT must be >= 1. "
                "Set to the number of worker processes that share this DB server "
                "(e.g. number of Kubernetes pods running the worker)."
            )
        return self

    @model_validator(mode="after")
    def _check_worker_db_capacity(self) -> "Settings":
        """Guard WORKER_CONCURRENCY against worker pool misconfiguration.

        The worker engine uses a dedicated pool (isolated from the API pool)
        with max_overflow=0. If WORKER_DB_POOL_SIZE is set explicitly and is
        smaller than WORKER_CONCURRENCY, worker slots would block waiting for
        a connection and eventually time out — startup FAILS.

        For multi-instance deployments (WORKER_INSTANCE_COUNT > 1), logs the
        total DB connection count so operators can verify it fits within
        PostgreSQL max_connections.

        SQLite in-memory uses StaticPool and is exempt from this guard.
        """
        if _is_sqlite_in_memory_url(self.database_url):
            return self

        effective = self.effective_worker_db_pool_size

        # Hard fail: explicit pool size smaller than concurrency slots needed.
        # With auto-derive (WORKER_DB_POOL_SIZE=0), effective == WORKER_CONCURRENCY
        # always, so this branch is only reachable with an explicit override.
        if effective < self.worker_concurrency:
            raise ValueError(
                f"WORKER_DB_POOL_SIZE={self.worker_db_pool_size} is insufficient: "
                f"WORKER_CONCURRENCY={self.worker_concurrency} requires at least "
                f"{self.worker_concurrency} connections in the worker pool "
                f"(max_overflow is always 0 for the worker pool — no overflow safety net). "
                f"Fix: set WORKER_DB_POOL_SIZE >= {self.worker_concurrency}, "
                f"or remove WORKER_DB_POOL_SIZE to auto-derive from WORKER_CONCURRENCY."
            )

        # Multi-instance: log total connection footprint for operator visibility.
        if self.worker_instance_count > 1:
            total_worker = effective * self.worker_instance_count
            api_capacity = self.db_pool_size + self.db_max_overflow
            total_db = total_worker + api_capacity
            _logger.warning(
                "Multi-instance worker deployment: WORKER_INSTANCE_COUNT=%d x "
                "worker_pool=%d = %d worker connections; "
                "API pool = %d connections; estimated total = %d. "
                "Ensure PostgreSQL max_connections > %d.",
                self.worker_instance_count,
                effective,
                total_worker,
                api_capacity,
                total_db,
                total_db,
            )

        return self

    @model_validator(mode="after")
    def _check_storage_backend(self) -> "Settings":
        """Reject unsafe or ambiguous storage backend config.

        Unknown backends must never silently fall back to local disk storage.
        Outside development/test, only explicitly configured S3 is allowed.
        """
        backend = self.storage_backend.strip().lower()
        valid_backends = frozenset({"local", "s3"})

        if backend not in valid_backends:
            raise ValueError(
                f"STORAGE_BACKEND={self.storage_backend!r} is not supported. "
                "Use one of: local, s3."
            )

        if self.storage_authoritative is None:
            self.storage_authoritative = backend == "s3"

        if backend == "local" and self.storage_authoritative:
            raise ValueError(
                "STORAGE_AUTHORITATIVE=true requires STORAGE_BACKEND='s3'. "
                "Local storage is allowed only for development/test workflows."
            )

        if _is_strict_environment(self.app_env) and backend == "local":
            raise ValueError(
                "Local storage is not allowed in production. "
                "Set STORAGE_BACKEND=s3."
            )

        if backend == "s3":
            bucket = self.s3_bucket.strip()
            region = self.s3_region.strip()
            access_key = self.s3_access_key_id.strip()
            secret_key = self.s3_secret_access_key.strip()
            signed_url_ttl = self.storage_signed_url_ttl_seconds
            connect_timeout = self.s3_connect_timeout_seconds
            read_timeout = self.s3_read_timeout_seconds

            if not bucket:
                raise ValueError(
                    f"S3_BUCKET must be set when STORAGE_BACKEND='s3' "
                    f"in APP_ENV={self.app_env!r}."
                )
            if _is_insecure_placeholder(bucket):
                raise ValueError(
                    f"S3_BUCKET looks like an unfilled placeholder in APP_ENV={self.app_env!r}. "
                    "Set the real bucket name."
                )
            if "s3_region" not in self.model_fields_set or not region:
                raise ValueError(
                    f"S3_REGION must be set when STORAGE_BACKEND='s3' "
                    f"in APP_ENV={self.app_env!r}."
                )
            if _is_insecure_placeholder(region):
                raise ValueError(
                    f"S3_REGION looks like an unfilled placeholder in APP_ENV={self.app_env!r}. "
                    "Set the real object-storage region."
                )
            if bool(access_key) != bool(secret_key):
                raise ValueError(
                    "S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be set together "
                    "or both omitted (for IAM/instance-role auth)."
                )
            if access_key and _is_insecure_placeholder(access_key):
                raise ValueError(
                    f"S3_ACCESS_KEY_ID looks like an unfilled placeholder in APP_ENV={self.app_env!r}."
                )
            if secret_key and _is_insecure_placeholder(secret_key):
                raise ValueError(
                    f"S3_SECRET_ACCESS_KEY looks like an unfilled placeholder in APP_ENV={self.app_env!r}."
                )
            if self.s3_endpoint_url.strip() and _looks_like_placeholder_url(self.s3_endpoint_url):
                raise ValueError(
                    f"S3_ENDPOINT_URL looks like an unfilled placeholder in APP_ENV={self.app_env!r}."
                )
            if self.s3_cdn_base_url.strip():
                raise ValueError(
                    "S3_CDN_BASE_URL is not supported with signed URL policy. "
                    "Remove S3_CDN_BASE_URL and use STORAGE_SIGNED_URL_TTL_SECONDS instead."
                )
            if connect_timeout <= 0:
                raise ValueError(
                    "S3_CONNECT_TIMEOUT_SECONDS must be > 0 so S3 connection attempts fail fast."
                )
            if read_timeout <= 0:
                raise ValueError(
                    "S3_READ_TIMEOUT_SECONDS must be > 0 so S3 reads/writes cannot hang indefinitely."
                )
            if signed_url_ttl < 1 or signed_url_ttl > 3600:
                raise ValueError(
                    "STORAGE_SIGNED_URL_TTL_SECONDS must be between 1 and 3600 seconds. "
                    "Signed storage URLs may not exceed 1 hour."
                )
            if _is_strict_environment(self.app_env) and not self.storage_authoritative:
                raise ValueError(
                    f"STORAGE_AUTHORITATIVE must remain true in APP_ENV={self.app_env!r}. "
                    "S3 is the authoritative production source of truth."
                )
        return self

    @model_validator(mode="after")
    def _check_cors_origins(self) -> "Settings":
        """Warn in development, fail in production when CORS origins still point to localhost.

        Having localhost/127.0.0.1 in a production CORS whitelist is not a security
        hole (the whitelist is too restrictive, not too permissive) but it means the
        real frontend will be refused and the app is silently misconfigured.
        Consistent with APP_BASE_URL, JWT_SECRET, and REDIS_URL fail-fast guards.
        """
        _LOCAL_FRAGMENTS = ("localhost", "127.0.0.1")
        origins = self.cors_allowed_origins.strip()

        if not _is_strict_environment(self.app_env):
            lower = origins.lower()
            if any(frag in lower for frag in _LOCAL_FRAGMENTS):
                _logger.debug(
                    "CORS_ALLOWED_ORIGINS contains localhost (expected in development): %r",
                    origins,
                )
            return self

        # Non-dev/test: fail fast if every origin is a localhost address, which
        # would lock out all browser clients in production.
        non_local = [
            o.strip()
            for o in origins.split(",")
            if o.strip() and not any(frag in o.lower() for frag in _LOCAL_FRAGMENTS)
        ]
        if not non_local:
            raise ValueError(
                f"CORS_ALLOWED_ORIGINS contains only localhost/127.0.0.1 addresses "
                f"in APP_ENV={self.app_env!r}. "
                "Set CORS_ALLOWED_ORIGINS to your deployed frontend URL(s) "
                "(e.g. https://app.example.com)."
            )
        placeholder_origins = [origin for origin in non_local if _looks_like_placeholder_url(origin)]
        if placeholder_origins:
            raise ValueError(
                f"CORS_ALLOWED_ORIGINS contains placeholder/example origin(s) "
                f"in APP_ENV={self.app_env!r}: {', '.join(placeholder_origins)}. "
                "Replace them with deployed frontend URL(s)."
            )
        return self

    @model_validator(mode="after")
    def _check_app_base_url(self) -> "Settings":
        """Guard APP_BASE_URL against localhost placeholders.

        In development/test: warn when still on the default localhost value.
        In all other environments (production, staging, ...): fail-fast if the
        value is empty or points to localhost - it must be the deployed client
        URL (needed if self-service reset is re-enabled).
        """
        _LOCAL_FRAGMENTS = ("localhost", "127.0.0.1")
        url = self.app_base_url.strip()

        if not _is_strict_environment(self.app_env):
            lower = url.lower()
            if not url or any(frag in lower for frag in _LOCAL_FRAGMENTS):
                _logger.debug(
                    "APP_BASE_URL remains on local/default value in %s "
                    "(current: %r). Self-service reset is retired in the current architecture.",
                    self.app_env,
                    url,
                )
            return self

        # Non-dev/test environments (production, staging, ...): strict fail.
        # Consistent with _check_jwt_secret, _check_redis_url, and other guards.
        if not url:
            raise ValueError(
                f"APP_BASE_URL must be set to the deployed client URL in "
                f"APP_ENV={self.app_env!r} (e.g. https://app.example.com). "
                "Current value is empty."
            )
        lower = url.lower()
        if any(frag in lower for frag in _LOCAL_FRAGMENTS):
            raise ValueError(
                f"APP_BASE_URL={url!r} points to localhost, which is not allowed "
                f"in APP_ENV={self.app_env!r}. Set it to the deployed client URL "
                "(e.g. https://app.example.com)."
            )
        if _url_scheme(url) not in {"http", "https"} or not _url_hostname(url):
            raise ValueError(
                f"APP_BASE_URL must be a valid http(s) URL in APP_ENV={self.app_env!r}. "
                "Set it to the deployed client URL (e.g. https://app.example.com)."
            )
        if _looks_like_placeholder_url(url):
            raise ValueError(
                f"APP_BASE_URL={url!r} looks like an example/template placeholder, "
                f"which is not allowed in APP_ENV={self.app_env!r}. "
                "Set it to the deployed client URL."
            )
        return self

    @property
    def worker_db_pool_capacity(self) -> int:
        """Total connections in the worker-dedicated DB pool.

        Equal to effective_worker_db_pool_size because max_overflow=0 for the
        worker pool. This is the hard ceiling on simultaneous worker DB sessions.
        """
        return self.effective_worker_db_pool_size

    @property
    def worker_db_safe_concurrency_limit(self) -> int:
        """Maximum safe WORKER_CONCURRENCY for the current worker pool.

        Equal to effective_worker_db_pool_size. The worker pool uses max_overflow=0,
        so its capacity equals its configured (or auto-derived) pool size.
        """
        return self.effective_worker_db_pool_size

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def should_auto_create_schema(self) -> bool:
        return self.app_env.lower() == "development" and self.db_auto_create_schema

    @property
    def should_seed_on_startup(self) -> bool:
        return self.app_env.lower() == "development" and self.db_seed_on_startup


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise RuntimeError(_settings_validation_message(exc)) from exc
