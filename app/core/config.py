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
    # Second synthesis pass when quality check fails (defaults to code model if unset).
    OLLAMA_SYNTH_FALLBACK_MODEL: str = ""
    # Step-specific model routing for latency/quality trade-offs.
    OLLAMA_CONTEXT_MODEL: str = ""
    OLLAMA_TOOL_DECISION_MODEL: str = ""
    OLLAMA_SYNTH_MODEL: str = ""
    OLLAMA_QUALITY_MODEL: str = ""

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

    # ── Answer quality (cache + graph + regenerate) ──
    QUALITY_MIN_SCORE: int = 6
    # Max synthesis runs per request (initial + retries after failed quality).
    MAX_SYNTHESIS_PASSES: int = 2
    # Conditional summarization threshold.
    HISTORY_SUMMARY_MIN_MESSAGES: int = 8
    # Rule-based quality gate threshold before invoking LLM quality eval.
    QUALITY_RULE_MIN_CHARS: int = 40

    # ── Firebase Auth (backend) ──────────────────────
    AUTH_ENABLED: bool = True
    # When True, skips Firebase verification and uses a fixed dev user (tests/local only).
    AUTH_DEV_BYPASS: bool = False
    FIREBASE_PROJECT_ID: str = ""
    # Path to service account JSON, or leave empty to use FIREBASE_CREDENTIALS_JSON env.
    FIREBASE_CREDENTIALS_PATH: str = ""
    # Raw JSON string of the Firebase service account (alternative to path).
    FIREBASE_CREDENTIALS_JSON: str = ""

    # ── Langfuse (local Docker or cloud) ──────────────
    # https://langfuse.com/docs — never commit keys.
    # Default True: if LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY are set, tracing runs.
    # Set LANGFUSE_ENABLED=false to disable even when keys are present.
    LANGFUSE_ENABLED: bool = True
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    # Langfuse UI base URL (local Docker default).
    LANGFUSE_HOST: str = "http://localhost:3000"
    # Name of the Langfuse project whose API keys you use (for metadata / docs).
    LANGFUSE_PROJECT_NAME: str = "movie-agent"

    @property
    def omdb_configured(self) -> bool:
        return bool(self.OMDB_API_KEY)

    @property
    def langfuse_configured(self) -> bool:
        """True when Langfuse tracing should be active (explicit opt-out + keys)."""
        if not self.LANGFUSE_ENABLED:
            return False
        return bool(
            (self.LANGFUSE_PUBLIC_KEY or "").strip()
            and (self.LANGFUSE_SECRET_KEY or "").strip()
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
