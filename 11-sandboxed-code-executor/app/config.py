"""Configuration settings for Sandboxed Code Executor."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Sandboxed Code Executor"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_path: str = "./data/sandbox.db"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    sandbox_timeout_seconds: float = 5.0
    enable_network_egress: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
