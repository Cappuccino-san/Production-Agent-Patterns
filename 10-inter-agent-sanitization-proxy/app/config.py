"""Configuration settings for Inter-Agent Sanitization Proxy."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Inter-Agent Sanitization Proxy"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_path: str = "./data/proxy.db"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    block_critical_injections: bool = True
    quarantine_threshold_score: float = 75.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
