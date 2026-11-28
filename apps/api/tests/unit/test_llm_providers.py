"""Quota guard (COST-4), provider chain (COST-5) and the Gemini adapter with a stub client.
No network and no API key: Gemini is exercised through a fake `client.aio.models`."""

import json
from collections.abc import Callable
from datetime import date
from types import SimpleNamespace
from typing import Any

import httpx
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
from app.services.llm.groq import GROQ_BASE_URL, GroqLLM
from app.services.llm.openai import OPENAI_BASE_URL, OpenAILLM
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
    router = LLMRouter([llm], {"fake": _guard(t, rpm=None, rpd=1)})
    await router.generate("q", "fast")
    with pytest.raises(LLMQuotaError):
        await router.generate("q", "fast")
    assert len(llm.calls) == 1


async def test_quota_on_one_provider_falls_through_to_the_next() -> None:
    t = FakeClock()

    class Second(FakeLLM):
        name = "second"

    first, second = FakeLLM(["first"]), Second(["second"])
    router = LLMRouter([first, second], {"fake": _guard(t, rpm=None, rpd=1)})
    assert (await router.generate("q", "fast")).text == "first"
    assert (await router.generate("q", "fast")).text == "second"
    assert len(first.calls) == 1


def test_build_llm_template_only_has_no_providers() -> None:
    assert not build_llm(make_settings(llm_providers=["template"])).available


def test_build_llm_skips_gemini_without_key_and_stops_at_template() -> None:
    router = build_llm(make_settings(llm_providers=["gemini", "fake", "template", "fake"]))
    assert [p.name for p in router.providers] == ["fake"]


def test_build_llm_groq_first_with_its_own_quota() -> None:
    settings = make_settings(
        llm_providers=["groq", "template"],
        groq_api_key="test-key",
        groq_model_fast="test-fast",
        groq_model_main="test-main",
        groq_rpm_limit=30,
        groq_rpd_limit=1000,
    )
    router = build_llm(settings)
    assert [p.name for p in router.providers] == ["groq"]
    assert (router.quotas["groq"].rpm_limit, router.quotas["groq"].rpd_limit) == (30, 1000)


def test_build_llm_skips_groq_without_models() -> None:
    settings = make_settings(llm_providers=["groq"], groq_api_key="test-key")
    assert not build_llm(settings).available


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


# --- Groq adapter (OpenAI-compatible HTTP API, mocked transport) ------------------------------


def _groq(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> GroqLLM:
    client = httpx.AsyncClient(base_url=GROQ_BASE_URL, transport=httpx.MockTransport(handler))
    return GroqLLM("test-key", "test-fast", "test-main", client=client, **kwargs)


def _completion(content: str) -> dict[str, Any]:
    return {
        "model": "test-fast",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5},
    }


async def test_groq_sends_system_schema_and_parses_json() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, json=_completion('{"intent": "smalltalk"}'))

    llm = _groq(handler, reasoning_effort="low")
    result = await llm.generate("q", "fast", json_schema={"type": "object"}, system="sys")
    assert result.json == {"intent": "smalltalk"}
    assert (result.tokens_in, result.tokens_out) == (20, 5)
    body = seen[0]
    assert body["model"] == "test-fast"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is False
    assert body["reasoning_effort"] == "low"


async def test_groq_main_tier_plain_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "test-main" and "response_format" not in body
        return httpx.Response(200, json=_completion("Hello"))

    result = await _groq(handler).generate("q", "main")
    assert result.text == "Hello" and result.json is None


async def test_groq_429_is_a_quota_error_and_500_a_provider_error() -> None:
    with pytest.raises(LLMQuotaError):
        await _groq(lambda r: httpx.Response(429, json={})).generate("q", "fast")
    with pytest.raises(LLMProviderError) as info:
        await _groq(lambda r: httpx.Response(500, json={})).generate("q", "fast")
    assert not isinstance(info.value, LLMQuotaError)


async def test_groq_network_error_is_a_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(LLMProviderError):
        await _groq(handler).generate("q", "fast")


async def test_groq_stream_reads_server_sent_events() -> None:
    events = [
        'data: {"choices": [{"delta": {"role": "assistant"}}]}',
        'data: {"choices": [{"delta": {"content": "Hel"}}]}',
        'data: {"choices": [{"delta": {"content": "lo"}}]}',
        "data: [DONE]",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text="\n\n".join(events))

    chunks = [c async for c in _groq(handler).stream("q", "main")]
    assert "".join(chunks) == "Hello"


# --- OpenAI adapter (paid backup, same API as Groq) -------------------------------------------


def _openai(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> OpenAILLM:
    client = httpx.AsyncClient(base_url=OPENAI_BASE_URL, transport=httpx.MockTransport(handler))
    return OpenAILLM("test-key", "test-fast", "test-main", client=client, **kwargs)


async def test_openai_sends_no_temperature_and_parses_json() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_completion('{"intent": "knowledge"}'))

    result = await _openai(handler, reasoning_effort="minimal").generate(
        "q", "fast", json_schema={"type": "object"}
    )
    assert result.json == {"intent": "knowledge"}
    body = json.loads(seen[0].content)
    assert "temperature" not in body  # gpt-5 family accepts only the default
    assert body["reasoning_effort"] == "minimal"
    assert str(seen[0].url) == f"{OPENAI_BASE_URL}/chat/completions"


async def test_openai_errors_name_the_provider() -> None:
    with pytest.raises(LLMQuotaError, match="OpenAI quota"):
        await _openai(lambda r: httpx.Response(429, json={})).generate("q", "fast")


async def test_openai_stream_skips_a_usage_only_chunk() -> None:
    events = [
        'data: {"choices": [{"delta": {"content": "Hi"}}]}',
        'data: {"choices": [], "usage": {"prompt_tokens": 3}}',
        "data: [DONE]",
    ]
    chunks = [
        c
        async for c in _openai(lambda r: httpx.Response(200, text="\n\n".join(events))).stream(
            "q", "main"
        )
    ]
    assert chunks == ["Hi"]


def test_build_llm_openai_after_groq_with_a_daily_cap() -> None:
    settings = make_settings(
        llm_providers=["groq", "openai", "template"],
        groq_api_key="g-key", groq_model_fast="g-fast", groq_model_main="g-main",
        openai_api_key="o-key", openai_model_fast="o-fast", openai_model_main="o-main",
        openai_rpd_limit=500,
    )  # fmt: skip
    router = build_llm(settings)
    assert [p.name for p in router.providers] == ["groq", "openai"]
    assert router.quotas["openai"].rpd_limit == 500


def test_build_llm_skips_openai_without_a_key() -> None:
    settings = make_settings(llm_providers=["openai"], openai_model_fast="f", openai_model_main="m")
    assert not build_llm(settings).available
