"""Configuration management with Pydantic Settings."""

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    database_path: str = Field(default="data/plans.db", description="SQLite database file path")
    environment: str = Field(default="production", description="Runtime environment")
    log_level: str = Field(default="INFO", description="Logging verbosity")
    max_steps: int = Field(default=10, ge=1, le=50, description="Maximum plan steps allowed")
    max_iterations: int = Field(default=15, ge=1, le=100, description="Maximum execution iterations")
    replan_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Confidence threshold for replanning")
    enable_adaptive_replanning: bool = Field(default=True, description="Enable dynamic replanning loop")
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
