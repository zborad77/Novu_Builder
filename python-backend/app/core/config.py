import logging
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_JWT_SECRET = "change-me-in-production"

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
    if lower in _PLACEHOLDER_EXACT:
        return True
    return any(frag in lower for frag in _PLACEHOLDER_FRAGMENTS)


def _url_password(url: str) -> str | None:
    """Extract the password component from a URL string, or None if absent."""
    try:
        return urlparse(url).password
    except Exception:
        return None


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
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="", alias="LOG_FILE")
    log_error_file: str = Field(default="", alias="LOG_ERROR_FILE")
    storage_root: str = Field(default="", alias="STORAGE_ROOT")
    ai_analysis_provider: str = Field(default="mock", alias="AI_ANALYSIS_PROVIDER")
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
    s3_cdn_base_url: str = Field(default="", alias="S3_CDN_BASE_URL")  # CDN prefix, e.g. https://cdn.example.com

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

    @model_validator(mode="after")
    def _check_debug_in_production(self) -> "Settings":
        if self.app_debug and self.app_env.lower() not in ("development", "test"):
            raise ValueError(
                f"APP_DEBUG=True is not allowed outside development. "
                f"Set APP_DEBUG=False (current APP_ENV={self.app_env!r})."
            )
        return self

    @model_validator(mode="after")
    def _check_jwt_secret(self) -> "Settings":
        if self.app_env.lower() in ("development", "test"):
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
        if self.app_env.lower() in ("development", "test"):
            return self
        if not self.metrics_auth_enabled:
            return self

        if not self.metrics_auth_token:
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
        return self

    @model_validator(mode="after")
    def _check_redis_url(self) -> "Settings":
        """Require an authenticated Redis URL in production."""
        if self.app_env.lower() in ("development", "test"):
            return self

        password = _url_password(self.redis_url)
        if password is None:
            raise ValueError(
                f"REDIS_URL must include a password in APP_ENV={self.app_env!r}. "
                "Set REDIS_URL=redis://:yourpassword@host:port/db"
            )
        if _is_insecure_placeholder(password):
            raise ValueError(
                f"REDIS_URL contains an insecure placeholder password "
                f"in APP_ENV={self.app_env!r}. Set a strong Redis password."
            )
        return self

    @model_validator(mode="after")
    def _check_database_url(self) -> "Settings":
        """Reject placeholder passwords embedded in DATABASE_URL in production."""
        if self.app_env.lower() in ("development", "test"):
            return self

        password = _url_password(self.database_url)
        if password is not None and _is_insecure_placeholder(password):
            raise ValueError(
                f"DATABASE_URL contains an insecure placeholder password "
                f"in APP_ENV={self.app_env!r}. Set real database credentials."
            )
        return self

    @model_validator(mode="after")
    def _check_app_base_url(self) -> "Settings":
        """Guard APP_BASE_URL against localhost placeholders.

        In production: fail-fast if the value is empty or points to localhost —
        it must be the deployed client URL (needed if self-service reset is re-enabled).
        In development: log a warning when still on the default localhost value.
        """
        _LOCAL_FRAGMENTS = ("localhost", "127.0.0.1")
        url = self.app_base_url.strip()

        if self.app_env.lower() == "production":
            if not url:
                raise ValueError(
                    "APP_BASE_URL must be set to the deployed client URL in production "
                    "(e.g. https://app.example.com). Current value is empty."
                )
            lower = url.lower()
            if any(frag in lower for frag in _LOCAL_FRAGMENTS):
                raise ValueError(
                    f"APP_BASE_URL={url!r} points to localhost, which is not allowed "
                    "in production. Set it to the deployed client URL "
                    "(e.g. https://app.example.com)."
                )
        elif self.app_env.lower() == "development":
            lower = url.lower()
            if not url or any(frag in lower for frag in _LOCAL_FRAGMENTS):
                _logger.warning(
                    "APP_BASE_URL is not configured for real client "
                    "(current: %r). Self-service password reset will not work "
                    "if re-enabled without a real client URL.",
                    url,
                )
        return self

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
    return Settings()
