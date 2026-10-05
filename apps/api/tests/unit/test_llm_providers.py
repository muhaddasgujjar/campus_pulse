"""Quota guard (COST-4), provider chain (COST-5) and the Gemini adapter with a stub client.
No network and no API key: Gemini is exercised through a fake `client.aio.models`."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from app.services.llm import (
    FakeLLM,
    LLMProviderError,
    LLMQuotaError,
    LLMRouter,
    build_llm,
)
from app.services.llm.gemini import GeminiLLM
from app.services.quota import QuotaGuard
from tests.conftest import make_settings


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.day = date(2026, 10, 5)
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def today(self) -> date:
        return self.day

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _guard(t: FakeClock, rpm: int | None, rpd: int | None, wait: float = 20) -> QuotaGuard:
    return QuotaGuard(rpm, rpd, wait, clock=t.clock, today=t.today, sleep=t.sleep)


# --- quota guard ------------------------------------------------------------------------------


async def test_no_limits_never_blocks() -> None:
    t = FakeClock()
    guard = _guard(t, None, None)
    for _ in range(100):
        await guard.acquire()
    assert guard.used_today == 100 and t.slept == []


async def test_per_minute_limit_waits_with_backoff_then_raises() -> None:
    t = FakeClock()
    guard = _guard(t, rpm=2, rpd=None, wait=20)
    await guard.acquire()
    await guard.acquire()
    with pytest.raises(LLMQuotaError, match="per-minute"):
        await guard.acquire()
    assert sum(t.slept) == pytest.approx(20)
    assert t.slept[:3] == [1.0, 2.0, 4.0]


async def test_per_minute_slot_frees_up_after_a_minute() -> None:
    t = FakeClock()
    guard = _guard(t, rpm=1, rpd=None, wait=60)
    await guard.acquire()
    await guard.acquire()  # waits until the first call is a minute old
    assert t.now >= 60


async def test_daily_limit_raises_without_waiting_and_resets_next_day() -> None:
    t = FakeClock()
    guard = _guard(t, rpm=None, rpd=1)
    await guard.acquire()
    with pytest.raises(LLMQuotaError, match="daily"):
        await guard.acquire()
    assert t.slept == []
    t.day = date(2026, 10, 6)
    await guard.acquire()


# --- router -------------------------------------------------------------------------------


async def test_router_falls_through_to_the_next_provider() -> None:
    down, up = FakeLLM(fail=True), FakeLLM(["ok"])
    result = await LLMRouter([down, up]).generate("q", "fast")
    assert result.text == "ok"
    assert len(down.calls) == 1 and len(up.calls) == 1


async def test_router_raises_when_every_provider_fails() -> None:
    with pytest.raises(LLMProviderError):
        await LLMRouter([FakeLLM(fail=True)]).generate("q", "fast")
    with pytest.raises(LLMProviderError):
        await LLMRouter([]).generate("q", "fast")


async def test_router_stops_on_quota_without_calling_providers() -> None:
    t = FakeClock()
    llm = FakeLLM()
    router = LLMRouter([llm], _guard(t, rpm=None, rpd=1))
    await router.generate("q", "fast")
    with pytest.raises(LLMQuotaError):
        await router.generate("q", "fast")
    assert len(llm.calls) == 1


def test_build_llm_template_only_has_no_providers() -> None:
    assert not build_llm(make_settings(llm_providers=["template"])).available


def test_build_llm_skips_gemini_without_key_and_stops_at_template() -> None:
    router = build_llm(make_settings(llm_providers=["gemini", "fake", "template", "fake"]))
    assert [p.name for p in router.providers] == ["fake"]


# --- Gemini adapter -------------------------------------------------------------------------


class StubModels:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def _gemini(models: StubModels) -> GeminiLLM:
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiLLM("unused", "test-fast", "test-main", client=client)


def _response(text: str) -> Any:
    usage = SimpleNamespace(prompt_token_count=12, candidates_token_count=3)
    return SimpleNamespace(text=text, usage_metadata=usage)


async def test_gemini_parses_json_and_uses_the_tier_model() -> None:
    models = StubModels(_response('{"intent": "smalltalk"}'))
    result = await _gemini(models).generate("q", "fast", json_schema={"type": "object"}, system="s")
    assert result.json == {"intent": "smalltalk"}
    assert (result.model, result.tokens_in, result.tokens_out) == ("test-fast", 12, 3)
    config = models.calls[0]["config"]
    assert models.calls[0]["model"] == "test-fast"
    assert config.response_mime_type == "application/json"
    assert config.system_instruction == "s"


async def test_gemini_429_becomes_quota_error() -> None:
    models = StubModels(error=errors.ClientError(429, {"error": {"message": "quota"}}))
    with pytest.raises(LLMQuotaError):
        await _gemini(models).generate("q", "main")


async def test_gemini_server_error_becomes_provider_error() -> None:
    models = StubModels(error=errors.ServerError(503, {"error": {"message": "down"}}))
    with pytest.raises(LLMProviderError) as info:
        await _gemini(models).generate("q", "main")
    assert not isinstance(info.value, LLMQuotaError)
