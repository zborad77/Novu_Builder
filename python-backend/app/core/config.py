from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    app_name: str = Field(default="FotoNabidka API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    database_url: str = Field(default="sqlite+aiosqlite:///./python-backend.db", alias="DATABASE_URL")
    database_url_sync_override: str | None = Field(default=None, alias="DATABASE_URL_SYNC")
    db_auto_create_schema: bool = Field(default=True, alias="DB_AUTO_CREATE_SCHEMA")
    db_seed_on_startup: bool = Field(default=True, alias="DB_SEED_ON_STARTUP")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    ai_analysis_provider: str = Field(default="mock", alias="AI_ANALYSIS_PROVIDER")

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
    def should_auto_create_schema(self) -> bool:
        return self.app_env.lower() == "development" and self.db_auto_create_schema

    @property
    def should_seed_on_startup(self) -> bool:
        return self.app_env.lower() == "development" and self.db_seed_on_startup


@lru_cache
def get_settings() -> Settings:
    return Settings()
