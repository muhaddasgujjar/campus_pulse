"""Groq adapter (OpenAI-compatible chat completions API), free tier, no SDK: plain httpx.

Model IDs come from GROQ_MODEL_FAST / GROQ_MODEL_MAIN. HTTP 429 becomes LLMQuotaError and
other failures LLMProviderError, so the router falls back to the next provider and the agent to
templates. JSON plans use `json_schema` in best-effort mode (strict mode needs every object
closed, and the plan's `args` is free-form); the agent validates the plan itself (D10).
Groq has no embeddings API: embeddings stay on Gemini (D17).
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.services.llm.base import LLMProviderError, LLMQuotaError, LLMResult, ModelTier

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqLLM:
    name = "groq"

    def __init__(
        self,
        api_key: str,
        model_fast: str,
        model_main: str,
        *,
        timeout_seconds: float = 25,
        reasoning_effort: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=GROQ_BASE_URL)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._models: dict[ModelTier, str] = {"fast": model_fast, "main": model_main}
        self._timeout = timeout_seconds
        self._reasoning_effort = reasoning_effort

    def _body(
        self,
        prompt: str,
        model_tier: ModelTier,
        system: str | None,
        json_schema: dict[str, Any] | None,
        stream: bool = False,
    ) -> dict[str, Any]:
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": self._models[model_tier],
            "messages": messages,
            "temperature": 0.1 if json_schema else 0.3,
        }
        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "plan", "strict": False, "schema": json_schema},
            }
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort
        if stream:
            body["stream"] = True
        return body

    @staticmethod
    def _error(status: int) -> LLMProviderError:
        if status == 429:
            return LLMQuotaError("Groq quota reached (429)")
        return LLMProviderError(f"Groq request failed ({status})")

    async def generate(
        self,
        prompt: str,
        model_tier: ModelTier,
        json_schema: dict[str, Any] | None = None,
        system: str | None = None,
    ) -> LLMResult:
        try:
            response = await self._client.post(
                "/chat/completions",
                json=self._body(prompt, model_tier, system, json_schema),
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise LLMProviderError("Groq timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Groq request failed ({type(exc).__name__})") from exc
        if response.status_code != 200:
            raise self._error(response.status_code)
        payload = response.json()
        text = (payload["choices"][0]["message"].get("content") or "").strip()
        parsed: dict[str, Any] | None = None
        if json_schema is not None:
            try:
                loaded = json.loads(text)
                parsed = loaded if isinstance(loaded, dict) else None
            except json.JSONDecodeError:
                parsed = None
        usage = payload.get("usage") or {}
        return LLMResult(
            text=text,
            model=payload.get("model", self._models[model_tier]),
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            json=parsed,
        )

    async def stream(
        self, prompt: str, model_tier: ModelTier, system: str | None = None
    ) -> AsyncIterator[str]:
        """Server-sent events: `data: {json}` lines, ending with `data: [DONE]`."""
        try:
            async with self._client.stream(
                "POST",
                "/chat/completions",
                json=self._body(prompt, model_tier, system, None, stream=True),
                headers=self._headers,
                timeout=self._timeout,
            ) as response:
                if response.status_code != 200:
                    raise self._error(response.status_code)
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ").strip()
                    if data == "[DONE]":
                        return
                    delta = json.loads(data)["choices"][0].get("delta") or {}
                    if delta.get("content"):
                        yield delta["content"]
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Groq stream failed ({type(exc).__name__})") from exc
