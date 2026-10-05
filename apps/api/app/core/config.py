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

    # --- database (Supabase Postgres via the pooler) ---
    database_url: str | None = None  # transaction pooler, used by the app
    database_url_migrations: str | None = None  # session pooler, used by Alembic

    # --- supabase (server-side only; never expose to the web app) ---
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_jwt_secret: SecretStr | None = None

    # --- redis (Upstash) ---
    redis_url: str | None = None

    # --- LLM (Gemini free tier, D15) ---
    gemini_api_key: SecretStr | None = None
    llm_providers: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["template"])
    llm_model_fast: str | None = None
    llm_model_main: str | None = None
    embedding_model: str | None = None
    embedding_dim: int = Field(default=768, gt=0)  # D17: vector(768)
    max_llm_calls_per_turn: int = Field(default=2, ge=0, le=2)  # COST-2

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
