"""Configuration settings for API-to-Browser Fallback Agent."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "API-to-Browser Fallback Agent"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_path: str = "./data/fallback_agent.db"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    api_timeout_seconds: float = 5.0
    browser_timeout_seconds: float = 15.0

    @property
    def sqlite_db_path(self) -> str:
        return self.database_path


@lru_cache
def get_settings() -> Settings:
    return Settings()
