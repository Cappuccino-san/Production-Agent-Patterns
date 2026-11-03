"""Configuration management with Pydantic Settings."""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    database_path: str = Field(
        default="data/reflections.db", description="SQLite database file path"
    )
    environment: str = Field(default="production", description="Runtime environment")
    log_level: str = Field(default="INFO", description="Logging verbosity")
    default_threshold: float = Field(
        default=85.0, ge=0.0, le=100.0, description="Default passing score threshold"
    )
    default_max_iterations: int = Field(
        default=4, ge=1, le=10, description="Default maximum reflexion iterations"
    )
    api_port: int = Field(default=8000, description="HTTP API port")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()
