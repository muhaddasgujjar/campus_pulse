"""FakeLLM satisfies the LLMProvider interface and records calls for budget tests (D15)."""

from app.services.llm import FakeLLM, LLMProvider


def test_fake_llm_implements_provider_protocol() -> None:
    assert isinstance(FakeLLM(), LLMProvider)


async def test_generate_returns_queued_replies_in_order() -> None:
    llm = FakeLLM(["first", "second"])
    assert (await llm.generate("q", "fast")).text == "first"
    assert (await llm.generate("q", "main")).text == "second"
    assert [tier for tier, _ in llm.calls] == ["fast", "main"]


async def test_generate_with_schema_returns_json() -> None:
    result = await FakeLLM(["planned"]).generate("q", "fast", json_schema={"type": "object"})
    assert result.json == {"text": "planned"}


async def test_stream_yields_full_text() -> None:
    llm = FakeLLM(["hello from the fake"])
    chunks = [chunk async for chunk in llm.stream("q", "main")]
    assert "".join(chunks) == "hello from the fake"
    assert len(llm.calls) == 1
