"""Application settings, read from environment variables (Memory D12).

Every value that can differ between machines or providers lives here. Model names,
keys and thresholds are never hardcoded elsewhere. See `apps/api/.env.example`.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_DISCLAIMER = (
    "Answers are based on information verified by LGU offices. "
    "Please confirm important decisions with the relevant office."
)


def _split_csv(value: object) -> object:
    """Allow comma-separated env values ("a,b") for list settings."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    """Typed settings. Field names map to upper-case env vars (DATABASE_URL, ...)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    app_env: Literal["local", "test", "ci", "dev", "prod"] = "local"
    log_level: str = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- institution (ADP-2: institution text lives in config, not in code paths) ---
    institution_slug: str = "lgu"
    institution_disclaimer: str = DEFAULT_DISCLAIMER
    # "Today" for date answers (rule 3) is the institution's local date, not the server's UTC
    # date. Pakistan is UTC+5 with no daylight saving time.
    institution_utc_offset_hours: float = Field(default=5, ge=-12, le=14)

    # --- database (Supabase Postgres via the pooler) ---
    database_url: str | None = None  # transaction pooler, used by the app
    database_url_migrations: str | None = None  # session pooler, used by Alembic

    # --- supabase (server-side only; never expose to the web app) ---
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_jwt_secret: SecretStr | None = None

    # --- redis (Upstash) ---
    redis_url: str | None = None

    # --- LLM: Gemini free tier (D15). LLM_MODEL_FAST/MAIN are the Gemini model IDs ---
    gemini_api_key: SecretStr | None = None
    llm_providers: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["template"])
    llm_model_fast: str | None = None
    llm_model_main: str | None = None
    embedding_model: str | None = None
    embedding_dim: int = Field(default=768, gt=0)  # D17: vector(768)
    max_llm_calls_per_turn: int = Field(default=2, ge=0, le=2)  # COST-2
    embedding_batch_size: int = Field(default=16, ge=1, le=100)
    llm_timeout_seconds: float = Field(default=25, gt=0)

    # --- Groq (free tier, OpenAI-compatible). LLM only: Groq has no embeddings API ---
    groq_api_key: SecretStr | None = None
    groq_model_fast: str | None = None
    groq_model_main: str | None = None
    groq_reasoning_effort: str | None = None  # gpt-oss models: low | medium | high

    # --- quota guard per provider (COST-4). Copy the limits from each dashboard.
    # Empty = no local limit (the provider's 429 is still handled).
    gemini_rpm_limit: int | None = Field(default=None, ge=1)
    gemini_rpd_limit: int | None = Field(default=None, ge=1)
    groq_rpm_limit: int | None = Field(default=None, ge=1)
    groq_rpd_limit: int | None = Field(default=None, ge=1)
    quota_max_wait_seconds: float = Field(default=20, ge=0, le=60)

    # --- response cache (COST-3): Redis when REDIS_URL is set, else in process. 0 = off.
    response_cache_ttl_seconds: int = Field(default=3600, ge=0)

    # --- chat (M3): rate limit per IP (CHAT-7) and session memory (CHAT-5) ---
    chat_rate_limit_messages: int = Field(default=20, ge=1)
    chat_rate_limit_window_seconds: int = Field(default=600, ge=1)
    session_memory_turns: int = Field(default=6, ge=0, le=20)
    session_memory_ttl_seconds: int = Field(default=86400, ge=60)
    chat_max_message_chars: int = Field(default=1000, ge=10, le=2000)  # SEC-2 input limit

    # --- retrieval and grading (tune on the golden set, Architectural.md Section 6) ---
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    retrieval_min_similarity: float = Field(default=0.62, ge=0, le=1)
    retrieval_min_keyword_coverage: float = Field(default=0.6, ge=0, le=1)

    # --- ingestion limits (Architectural.md Section 7) ---
    pdf_max_mb: int = Field(default=10, ge=1, le=50)

    # --- ops ---
    internal_jobs_secret: SecretStr | None = None
    chat_retention_days: int = Field(default=60, gt=0)

    @field_validator("cors_origins", "llm_providers", mode="before")
    @classmethod
    def _parse_csv(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator(
        "database_url",
        "database_url_migrations",
        "supabase_url",
        "redis_url",
        "llm_model_fast",
        "llm_model_main",
        "embedding_model",
        "supabase_service_role_key",
        "supabase_jwt_secret",
        "gemini_api_key",
        "internal_jobs_secret",
        "groq_api_key",
        "groq_model_fast",
        "groq_model_main",
        "groq_reasoning_effort",
        "gemini_rpm_limit",
        "gemini_rpd_limit",
        "groq_rpm_limit",
        "groq_rpd_limit",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        """Treat `KEY=` (empty, as in .env.example) as not configured."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings instance (FastAPI dependency)."""
    return Settings()
