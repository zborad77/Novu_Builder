import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_JWT_SECRET = "change-me-in-production"

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
    # Dev default allows Vite dev server; production must set this explicitly.
    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
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
    app_base_url: str = Field(default="http://localhost:5173", alias="APP_BASE_URL")

    # Storage backend — "local" (default) or "s3"
    storage_backend: str = Field(default="local", alias="STORAGE_BACKEND")
    s3_bucket: str = Field(default="", alias="S3_BUCKET")
    s3_endpoint_url: str = Field(default="", alias="S3_ENDPOINT_URL")  # leave empty for AWS S3
    s3_access_key_id: str = Field(default="", alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str = Field(default="", alias="S3_SECRET_ACCESS_KEY")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    s3_cdn_base_url: str = Field(default="", alias="S3_CDN_BASE_URL")  # CDN prefix, e.g. https://cdn.example.com

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
        if self.jwt_secret == _DEFAULT_JWT_SECRET and self.app_env.lower() != "development":
            raise ValueError(
                f"JWT_SECRET must be changed from the default value in non-development environments. "
                f"Set a strong, unique JWT_SECRET (current APP_ENV={self.app_env!r})."
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
