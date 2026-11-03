"""Application configuration and environment settings."""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment or defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(
        default="human-in-the-loop-approval-agent",
        description="Application identifier",
    )
    database_path: str = Field(
        default="data/approvals.db",
        description="Path to SQLite database file",
    )
    environment: str = Field(
        default="development",
        description="Runtime environment (development, staging, production, testing)",
    )
    log_level: str = Field(
        default="INFO",
        description="Standard logging level",
    )
    api_prefix: str = Field(
        default="/api/v1",
        description="Prefix for API routes",
    )
    default_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Default timeout in seconds for agent actions",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
