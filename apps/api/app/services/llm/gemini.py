"""Gemini adapter (google-genai SDK) for the free tier (D14, D15).

Model IDs come from LLM_MODEL_FAST / LLM_MODEL_MAIN. HTTP 429 becomes LLMQuotaError and other
API failures LLMProviderError, so the router and the agent can fall back to templates.
Free-tier requests may be used by Google to improve its products: callers redact personal
data before anything reaches this class (SEC-5).
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.services.llm.base import (
    LLMProviderError,
    LLMQuotaError,
    LLMResult,
    ModelTier,
)


class GeminiLLM:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model_fast: str,
        model_main: str,
        *,
        timeout_seconds: float = 25,
        client: Any = None,
    ) -> None:
        if client is None:
            from google import genai  # imported lazily: tests inject a stub client

            client = genai.Client(api_key=api_key)
        self._client = client
        self._models: dict[ModelTier, str] = {"fast": model_fast, "main": model_main}
        self._timeout = timeout_seconds

    def _config(self, system: str | None, json_schema: dict[str, Any] | None) -> Any:
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.1 if json_schema else 0.3,
            response_mime_type="application/json" if json_schema else None,
            response_json_schema=json_schema,
        )

    @staticmethod
    def _translate(exc: Exception) -> LLMProviderError:
        code = getattr(exc, "code", None)
        if code == 429:
            return LLMQuotaError("Gemini quota reached (429)")
        if isinstance(exc, TimeoutError):
            return LLMProviderError("Gemini timed out")
        return LLMProviderError(f"Gemini request failed ({code or type(exc).__name__})")

    async def generate(
        self,
        prompt: str,
        model_tier: ModelTier,
        json_schema: dict[str, Any] | None = None,
        system: str | None = None,
    ) -> LLMResult:
        from google.genai import errors

        model = self._models[model_tier]
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=model, contents=prompt, config=self._config(system, json_schema)
                ),
                timeout=self._timeout,
            )
        except (errors.APIError, TimeoutError) as exc:
            raise self._translate(exc) from exc
        text = response.text or ""
        parsed: dict[str, Any] | None = None
        if json_schema is not None:
            try:
                loaded = json.loads(text)
                parsed = loaded if isinstance(loaded, dict) else None
            except json.JSONDecodeError:
                parsed = None
        usage = response.usage_metadata
        return LLMResult(
            text=text,
            model=model,
            tokens_in=(usage.prompt_token_count or 0) if usage else 0,
            tokens_out=(usage.candidates_token_count or 0) if usage else 0,
            json=parsed,
        )

    async def stream(
        self, prompt: str, model_tier: ModelTier, system: str | None = None
    ) -> AsyncIterator[str]:
        from google.genai import errors

        try:
            chunks = await self._client.aio.models.generate_content_stream(
                model=self._models[model_tier], contents=prompt, config=self._config(system, None)
            )
            async for chunk in chunks:
                if chunk.text:
                    yield chunk.text
        except errors.APIError as exc:
            raise self._translate(exc) from exc
