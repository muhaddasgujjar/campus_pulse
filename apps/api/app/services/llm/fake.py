"""Deterministic fake LLM for tests and local development (Memory rule 12).

Burns no quota and needs no network. Responses are queued by tests, or a fixed
default is returned. Every call is recorded so tests can assert the LLM budget.
"""

from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from app.services.llm.base import LLMResult, ModelTier

DEFAULT_REPLY = "This is a fake LLM reply."


class FakeLLM:
    name = "fake"

    def __init__(self, replies: list[str] | None = None) -> None:
        self._replies: deque[str] = deque(replies or [])
        self.calls: list[tuple[ModelTier, str]] = []

    def queue(self, *replies: str) -> None:
        self._replies.extend(replies)

    def _next(self) -> str:
        return self._replies.popleft() if self._replies else DEFAULT_REPLY

    async def generate(
        self,
        prompt: str,
        model_tier: ModelTier,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        self.calls.append((model_tier, prompt))
        text = self._next()
        parsed = {"text": text} if json_schema is not None else None
        return LLMResult(
            text=text,
            model=f"fake-{model_tier}",
            tokens_in=len(prompt.split()),
            tokens_out=len(text.split()),
            json=parsed,
        )

    async def stream(self, prompt: str, model_tier: ModelTier) -> AsyncIterator[str]:
        self.calls.append((model_tier, prompt))
        words = self._next().split(" ")
        for index, word in enumerate(words):
            yield word if index == len(words) - 1 else word + " "
