"""Application configuration settings using Pydantic Settings."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for RAG hybrid SQLite FTS5 agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RAG Hybrid SQLite FTS5 Agent"
    environment: str = "development"
    log_level: str = "INFO"
    database_path: str = "data/rag_documents.db"

    # RAG Retrieval and Agent defaults
    default_top_k: int = 5
    relevance_threshold: float = 0.0
    max_iterations: int = 2
    enable_query_decomposition: bool = True


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
