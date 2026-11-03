"""Configuration settings for Shadow Trajectory Comparator."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Shadow Trajectory Comparator"
    app_version: str = "0.1.0"
    environment: str = "development"
    database_path: str = "./data/shadow_comparator.db"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    shadow_sample_rate: float = 0.05  # 5% traffic mirror

    @property
    def sqlite_db_path(self) -> str:
        return self.database_path


@lru_cache
def get_settings() -> Settings:
    return Settings()
