"""LLM providers behind one interface: Gemini, the FakeLLM for tests, and the provider chain
with the quota guard (COST-4, COST-5)."""

from app.services.llm.base import (
    LLMBudgetError,
    LLMProvider,
    LLMProviderError,
    LLMQuotaError,
    LLMResult,
    ModelTier,
)
from app.services.llm.fake import FakeLLM
from app.services.llm.router import LLMRouter, build_llm

__all__ = [
    "FakeLLM",
    "LLMBudgetError",
    "LLMProvider",
    "LLMProviderError",
    "LLMQuotaError",
    "LLMResult",
    "LLMRouter",
    "ModelTier",
    "build_llm",
]
