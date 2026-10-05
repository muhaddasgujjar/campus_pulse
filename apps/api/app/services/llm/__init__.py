"""LLM providers behind one interface.

M1: interface and FakeLLM only. M2 adds the Gemini adapter (google-genai SDK), the
template provider and the quota guard (per-minute and per-day counters).
"""

from app.services.llm.base import LLMProvider, LLMProviderError, LLMResult, ModelTier
from app.services.llm.fake import FakeLLM

__all__ = ["FakeLLM", "LLMProvider", "LLMProviderError", "LLMResult", "ModelTier"]
