"""Provider chain (COST-5): try each configured provider in LLM_PROVIDERS order.

"template" in the chain means "no more LLMs": the router raises and the agent renders a
template answer (structured data) or the fallback. Every call passes the quota guard.
"""

from collections.abc import AsyncIterator
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

    def __init__(self, providers: list[LLMProvider], quota: QuotaGuard | None = None) -> None:
        self.providers = providers
        self.quota = quota

    @property
    def available(self) -> bool:
        return bool(self.providers)

    async def generate(
        self,
        prompt: str,
        model_tier: ModelTier,
        json_schema: dict[str, Any] | None = None,
        system: str | None = None,
    ) -> LLMResult:
        last: LLMProviderError | None = None
        for provider in self.providers:
            if self.quota is not None:
                await self.quota.acquire()  # raises LLMQuotaError: no point trying others
            try:
                return await provider.generate(prompt, model_tier, json_schema, system)
            except LLMProviderError as exc:
                log.warning("llm_provider_failed", provider=provider.name, error=str(exc))
                last = exc
        raise last or LLMProviderError("no LLM provider configured")

    async def stream(
        self, prompt: str, model_tier: ModelTier, system: str | None = None
    ) -> AsyncIterator[str]:
        if not self.providers:
            raise LLMProviderError("no LLM provider configured")
        if self.quota is not None:
            await self.quota.acquire()
        async for token in self.providers[0].stream(prompt, model_tier, system):
            yield token


def build_llm(settings: Settings) -> LLMRouter:
    """Build the chain from LLM_PROVIDERS. Unconfigured providers are skipped with a warning."""
    providers: list[LLMProvider] = []
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
            else:
                log.warning(
                    "llm_provider_skipped",
                    provider="gemini",
                    reason="GEMINI_API_KEY, LLM_MODEL_FAST or LLM_MODEL_MAIN missing",
                )
        else:
            log.warning("llm_provider_unknown", provider=name)
    quota = QuotaGuard(
        settings.llm_rpm_limit, settings.llm_rpd_limit, settings.quota_max_wait_seconds
    )
    return LLMRouter(providers, quota)
