"""FakeLLM satisfies the LLMProvider interface and records calls for budget tests (D15)."""

import pytest

from app.services.llm import FakeLLM, LLMProvider, LLMProviderError


def test_fake_llm_implements_provider_protocol() -> None:
    assert isinstance(FakeLLM(), LLMProvider)


async def test_generate_returns_queued_replies_in_order() -> None:
    llm = FakeLLM(["first", "second"])
    assert (await llm.generate("q", "fast")).text == "first"
    assert (await llm.generate("q", "main")).text == "second"
    assert [tier for tier, _ in llm.calls] == ["fast", "main"]


async def test_generate_with_schema_parses_a_json_reply() -> None:
    result = await FakeLLM(['{"intent": "smalltalk"}']).generate(
        "q", "fast", json_schema={"type": "object"}
    )
    assert result.json == {"intent": "smalltalk"}


async def test_generate_with_schema_and_invalid_json_gives_none() -> None:
    result = await FakeLLM(["not json"]).generate("q", "fast", json_schema={"type": "object"})
    assert result.json is None


async def test_failing_fake_raises_and_still_records_the_call() -> None:
    llm = FakeLLM(fail=True)
    with pytest.raises(LLMProviderError):
        await llm.generate("q", "fast", system="sys")
    assert len(llm.calls) == 1
    assert llm.systems == ["sys"]


async def test_stream_yields_full_text() -> None:
    llm = FakeLLM(["hello from the fake"])
    chunks = [chunk async for chunk in llm.stream("q", "main")]
    assert "".join(chunks) == "hello from the fake"
    assert len(llm.calls) == 1
