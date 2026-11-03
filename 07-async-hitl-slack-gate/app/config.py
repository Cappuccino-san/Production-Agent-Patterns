"""Configuration settings for Async HITL Slack Gate."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Async HITL Slack Gate"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_path: str = "./data/hitl_gate.db"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    approval_timeout_hours: int = 72
    slack_webhook_secret: str = "default-secret"


@lru_cache
def get_settings() -> Settings:
    return Settings()
