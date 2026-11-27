"""Deterministic fake LLM for tests and local development (Memory rule 12).

Burns no quota and needs no network. Responses are queued by tests, or a fixed default is
returned. With a JSON schema, a queued reply that is valid JSON is parsed into `json`.
Every call is recorded so tests can assert the LLM budget.
"""

import json
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from app.services.llm.base import LLMProviderError, LLMResult, ModelTier

DEFAULT_REPLY = "This is a fake LLM reply."


class FakeLLM:
    name = "fake"

    def __init__(self, replies: list[str] | None = None, *, fail: bool = False) -> None:
        self._replies: deque[str] = deque(replies or [])
        self.calls: list[tuple[ModelTier, str]] = []
        self.systems: list[str | None] = []
        self.fail = fail

    def queue(self, *replies: str) -> None:
        self._replies.extend(replies)

    def _next(self) -> str:
        return self._replies.popleft() if self._replies else DEFAULT_REPLY

    async def generate(
        self,
        prompt: str,
        model_tier: ModelTier,
        json_schema: dict[str, Any] | None = None,
        system: str | None = None,
    ) -> LLMResult:
        self.calls.append((model_tier, prompt))
        self.systems.append(system)
        if self.fail:
            raise LLMProviderError("fake provider is down")
        text = self._next()
        parsed: dict[str, Any] | None = None
        if json_schema is not None:
            try:
                loaded = json.loads(text)
                parsed = loaded if isinstance(loaded, dict) else None
            except json.JSONDecodeError:
                parsed = None
        return LLMResult(
            text=text,
            model=f"fake-{model_tier}",
            tokens_in=len(prompt.split()),
            tokens_out=len(text.split()),
            json=parsed,
        )

    async def stream(
        self, prompt: str, model_tier: ModelTier, system: str | None = None
    ) -> AsyncIterator[str]:
        self.calls.append((model_tier, prompt))
        self.systems.append(system)
        if self.fail:
            raise LLMProviderError("fake provider is down")
        words = self._next().split(" ")
        for index, word in enumerate(words):
            yield word if index == len(words) - 1 else word + " "
