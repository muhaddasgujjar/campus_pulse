"""LLM provider interface (D12, D15, COST-5).

Providers are chosen by the LLM_PROVIDERS env var (for example "gemini,template").
Model IDs come from LLM_MODEL_FAST and LLM_MODEL_MAIN, never from code.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

ModelTier = Literal["fast", "main"]  # fast: plan (call 1). main: compose (call 2).


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    json: dict[str, Any] | None = field(default=None)


@runtime_checkable
class LLMProvider(Protocol):
    """One LLM backend. The agent never calls a vendor SDK directly."""

    name: str

    async def generate(
        self,
        prompt: str,
        model_tier: ModelTier,
        json_schema: dict[str, Any] | None = None,
        system: str | None = None,
    ) -> LLMResult:
        """Single completion. With `json_schema`, `LLMResult.json` holds the parsed object."""
        ...

    def stream(
        self, prompt: str, model_tier: ModelTier, system: str | None = None
    ) -> AsyncIterator[str]:
        """Stream text tokens (used by the compose node over the WebSocket in M3)."""
        ...


class LLMProviderError(RuntimeError):
    """Provider failed. The router tries the next provider; the agent then uses templates."""


class LLMQuotaError(LLMProviderError):
    """Rate or daily quota reached (HTTP 429 or the local quota guard)."""


class LLMBudgetError(LLMProviderError):
    """This turn already used its LLM calls (COST-2: at most 2 per turn)."""
