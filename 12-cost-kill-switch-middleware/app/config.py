"""Configuration settings for Cost Kill-Switch Middleware."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Cost Kill-Switch Middleware"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_path: str = "./data/cost_control.db"

    @property
    def sqlite_db_path(self) -> str:
        return self.database_path
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    max_spend_limit_usd: float = 0.50
    max_loop_depth: int = 5
    frontier_model: str = "gpt-4o"
    fallback_model: str = "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()
