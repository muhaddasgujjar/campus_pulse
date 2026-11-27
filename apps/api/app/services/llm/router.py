"""Provider chain (COST-5): try each configured provider in LLM_PROVIDERS order.

"template" in the chain means "no more LLMs": the router raises and the agent renders a
template answer (structured data) or the fallback. Each provider has its own quota guard, so
when Groq's free quota runs out the next provider (Gemini) is tried.
"""

from collections.abc import AsyncIterator, Mapping
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMResult,
    ModelTier,
)
from app.services.quota import QuotaGuard

log = get_logger("llm")


class LLMRouter:
    name = "router"

    def __init__(
        self, providers: list[LLMProvider], quotas: Mapping[str, QuotaGuard] | None = None
    ) -> None:
        self.providers = providers
        self.quotas = dict(quotas or {})

    @property
    def available(self) -> bool:
        return bool(self.providers)

    async def _acquire(self, provider: LLMProvider) -> None:
        guard = self.quotas.get(provider.name)
        if guard is not None:
            await guard.acquire()  # raises LLMQuotaError

    async def generate(
        self,
        prompt: str,
        model_tier: ModelTier,
        json_schema: dict[str, Any] | None = None,
        system: str | None = None,
    ) -> LLMResult:
        last: LLMProviderError | None = None
        for provider in self.providers:
            try:
                await self._acquire(provider)
                return await provider.generate(prompt, model_tier, json_schema, system)
            except LLMProviderError as exc:
                log.warning("llm_provider_failed", provider=provider.name, error=str(exc))
                last = exc
        raise last or LLMProviderError("no LLM provider configured")

    async def stream(
        self, prompt: str, model_tier: ModelTier, system: str | None = None
    ) -> AsyncIterator[str]:
        """Streams from the first provider with quota left (no switching mid-answer)."""
        last: LLMProviderError | None = None
        for provider in self.providers:
            try:
                await self._acquire(provider)
            except LLMProviderError as exc:
                last = exc
                continue
            async for token in provider.stream(prompt, model_tier, system):
                yield token
            return
        raise last or LLMProviderError("no LLM provider configured")


def build_llm(settings: Settings) -> LLMRouter:
    """Build the chain from LLM_PROVIDERS. Unconfigured providers are skipped with a warning."""
    providers: list[LLMProvider] = []
    quotas: dict[str, QuotaGuard] = {}
    wait = settings.quota_max_wait_seconds
    for name in settings.llm_providers:
        if name == "template":
            break
        if name == "fake":
            from app.services.llm.fake import FakeLLM

            providers.append(FakeLLM())
        elif name == "gemini":
            if settings.gemini_api_key and settings.llm_model_fast and settings.llm_model_main:
                from app.services.llm.gemini import GeminiLLM

                providers.append(
                    GeminiLLM(
                        settings.gemini_api_key.get_secret_value(),
                        settings.llm_model_fast,
                        settings.llm_model_main,
                        timeout_seconds=settings.llm_timeout_seconds,
                    )
                )
                quotas["gemini"] = QuotaGuard(
                    settings.gemini_rpm_limit, settings.gemini_rpd_limit, wait
                )
            else:
                log.warning(
                    "llm_provider_skipped",
                    provider="gemini",
                    reason="GEMINI_API_KEY, LLM_MODEL_FAST or LLM_MODEL_MAIN missing",
                )
        elif name == "groq":
            if settings.groq_api_key and settings.groq_model_fast and settings.groq_model_main:
                from app.services.llm.groq import GroqLLM

                providers.append(
                    GroqLLM(
                        settings.groq_api_key.get_secret_value(),
                        settings.groq_model_fast,
                        settings.groq_model_main,
                        timeout_seconds=settings.llm_timeout_seconds,
                        reasoning_effort=settings.groq_reasoning_effort,
                    )
                )
                quotas["groq"] = QuotaGuard(settings.groq_rpm_limit, settings.groq_rpd_limit, wait)
            else:
                log.warning(
                    "llm_provider_skipped",
                    provider="groq",
                    reason="GROQ_API_KEY, GROQ_MODEL_FAST or GROQ_MODEL_MAIN missing",
                )
        else:
            log.warning("llm_provider_unknown", provider=name)
    return LLMRouter(providers, quotas)
