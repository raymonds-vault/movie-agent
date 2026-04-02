"""
Core configuration module.
Loads all settings from environment variables using Pydantic BaseSettings.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ──────────────────────────────────
    APP_NAME: str = "Movie Agent"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    # Run `npm run dev` in frontend/ when API starts (set AUTO_START_REACT_DEV=false to disable)
    AUTO_START_REACT_DEV: bool = True
    OPEN_REACT_BROWSER: bool = True
    REACT_DEV_URL: str = "http://127.0.0.1:5173"

    # ── Ollama ───────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1"
    OLLAMA_CODE_MODEL: str = "deepseek-coder"

    # ── OMDb ─────────────────────────────────────────
    OMDB_API_KEY: str = ""
    OMDB_BASE_URL: str = "http://www.omdbapi.com/"

    # ── Database ─────────────────────────────────────
    DATABASE_URL: str = "mysql+aiomysql://root:Admin123@localhost:3306/movie_agent"

    # ── Redis & Embeddings ───────────────────────────
    REDIS_URL: str = "redis://localhost:6379"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    # If True, an LLM must confirm a Redis semantic-cache hit before it is returned.
    SEMANTIC_CACHE_VERIFY: bool = True

    @property
    def omdb_configured(self) -> bool:
        return bool(self.OMDB_API_KEY)


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
