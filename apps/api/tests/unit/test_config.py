"""Settings are read from env vars, with safe defaults and no hardcoded model names (D12)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def load(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_defaults_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("DATABASE_URL", "REDIS_URL", "LLM_MODEL_FAST", "LLM_MODEL_MAIN", "EMBEDDING_MODEL"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    assert settings.institution_slug == "lgu"
    assert settings.database_url is None
    assert settings.redis_url is None
    assert settings.llm_model_fast is None  # model names only come from env
    assert settings.llm_model_main is None
    assert settings.embedding_dim == 768
    assert settings.max_llm_calls_per_turn == 2
    assert settings.chat_retention_days == 60


def test_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load(
        monkeypatch,
        APP_ENV="dev",
        INSTITUTION_SLUG="test-uni",
        CORS_ORIGINS="http://localhost:3000, https://example.vercel.app",
        LLM_PROVIDERS="gemini,template",
        LLM_MODEL_FAST="fake-fast-model",
        LLM_MODEL_MAIN="fake-main-model",
        EMBEDDING_MODEL="fake-embedding",
        EMBEDDING_DIM="768",
        MAX_LLM_CALLS_PER_TURN="1",
        CHAT_RETENTION_DAYS="30",
        GEMINI_API_KEY="fake-key-for-tests",
    )
    assert settings.app_env == "dev"
    assert settings.institution_slug == "test-uni"
    assert settings.cors_origins == ["http://localhost:3000", "https://example.vercel.app"]
    assert settings.llm_providers == ["gemini", "template"]
    assert settings.llm_model_fast == "fake-fast-model"
    assert settings.llm_model_main == "fake-main-model"
    assert settings.embedding_model == "fake-embedding"
    assert settings.max_llm_calls_per_turn == 1
    assert settings.chat_retention_days == 30
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "fake-key-for-tests"


def test_empty_values_mean_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load(monkeypatch, DATABASE_URL="", REDIS_URL="  ", GEMINI_API_KEY="")
    assert settings.database_url is None
    assert settings.redis_url is None
    assert settings.gemini_api_key is None


def test_secrets_are_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load(monkeypatch, SUPABASE_SERVICE_ROLE_KEY="fake-service-role")
    assert "fake-service-role" not in repr(settings)


def test_llm_budget_cannot_exceed_two_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        load(monkeypatch, MAX_LLM_CALLS_PER_TURN="3")


def test_invalid_app_env_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        load(monkeypatch, APP_ENV="staging-typo")


def test_empty_disclaimer_keeps_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """.env.example ships `INSTITUTION_DISCLAIMER=`: the footer must not go blank (CHAT-8)."""
    settings = load(monkeypatch, INSTITUTION_DISCLAIMER="")
    assert settings.institution_disclaimer.startswith("Answers are based on information verified")
    custom = load(monkeypatch, INSTITUTION_DISCLAIMER="Confirm with your office.")
    assert custom.institution_disclaimer == "Confirm with your office."


@pytest.mark.parametrize(
    ("model", "override", "expected"),
    [
        ("gemini-embedding-001", "", 0.62),
        ("text-embedding-3-small", "", 0.54),  # tuned on eval/golden.jsonl, 2026-11-28
        ("fake", "", 0.62),
        ("text-embedding-3-small", "0.7", 0.7),  # an explicit value always wins
    ],
)
def test_similarity_threshold_follows_the_embedding_model(
    monkeypatch: pytest.MonkeyPatch, model: str, override: str, expected: float
) -> None:
    settings = load(monkeypatch, EMBEDDING_MODEL=model, RETRIEVAL_MIN_SIMILARITY=override)
    assert settings.min_similarity == expected
