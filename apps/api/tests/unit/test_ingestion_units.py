"""Chunking, PDF extraction, embeddings and grading: pure units, no database, no network."""

import json
import math
import uuid
from datetime import date
from typing import Any

import httpx
import pytest

from app.services.chunking import MAX_TOKENS, WORDS_PER_TOKEN, chunk_text, entry_chunk
from app.services.embeddings import (
    CachedQueryEmbedder,
    EmbeddingError,
    FakeEmbedder,
    OpenAIEmbedder,
    build_embedder,
)
from app.services.pdf import PdfRejectedError, extract_pdf_text
from app.services.retrieval import RetrievedChunk, coverage, grade
from tests.conftest import make_settings
from tests.support.pdf import make_pdf

# --- chunking ------------------------------------------------------------------------------


def test_entry_is_exactly_one_chunk() -> None:
    chunk = entry_chunk("Test entry", "What is tested?", "Everything is tested.")
    assert chunk == "Test entry\nQ: What is tested?\nA: Everything is tested."


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("Para one about testing.\n\nPara two about testing.") == [
        "Para one about testing. Para two about testing."
    ]


def test_long_text_splits_within_limit_with_overlap() -> None:
    paragraphs = [" ".join(f"word{p}x{i}" for i in range(120)) for p in range(10)]
    chunks = chunk_text("\n\n".join(paragraphs))
    max_words = int(MAX_TOKENS * WORDS_PER_TOKEN)
    assert len(chunks) > 1
    assert all(len(c.split()) <= max_words for c in chunks)
    # consecutive chunks share words (10-15% overlap)
    first, second = chunks[0].split(), chunks[1].split()
    assert set(first[-20:]) & set(second[:60])


def test_one_huge_paragraph_is_split_at_sentences() -> None:
    sentence = "This test sentence has exactly ten words in it. "
    chunks = chunk_text(sentence * 200)
    assert len(chunks) > 3
    assert all(c.rstrip().endswith(".") for c in chunks[:-1])


# --- pdf -----------------------------------------------------------------------------------


def test_text_pdf_is_extracted() -> None:
    pdf = make_pdf(["Test Hostel Policy (fake).", "Rooms are allocated first come first served."])
    result = extract_pdf_text(pdf, max_mb=10)
    assert result.pages == 1
    assert "Test Hostel Policy (fake)." in result.text


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"PK\x03\x04 not a pdf", "not a PDF"),
        (make_pdf(), "OCR is not supported"),
        (b"%PDF-1.4 broken", "could not be read"),
    ],
)
def test_bad_pdfs_are_rejected(data: bytes, message: str) -> None:
    with pytest.raises(PdfRejectedError, match=message):
        extract_pdf_text(data, max_mb=10)


def test_size_limit() -> None:
    with pytest.raises(PdfRejectedError, match="larger than 1 MB"):
        extract_pdf_text(b"%PDF-" + b"0" * (1024 * 1024 + 1), max_mb=1)


# --- embeddings ----------------------------------------------------------------------------


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_fake_embedder_is_deterministic_normalized_and_lexical() -> None:
    embedder = FakeEmbedder()
    fee, fees, hostel = (
        await embedder.embed_query("tuition fee per credit hour"),
        await embedder.embed_query("Tuition fees per credit hour"),
        await embedder.embed_query("hostel rooms for girls"),
    )
    assert len(fee) == 768
    assert math.isclose(math.sqrt(sum(v * v for v in fee)), 1.0, rel_tol=1e-9)
    assert _cos(fee, fees) > 0.95  # same words modulo case and plural
    assert _cos(fee, hostel) < 0.3


async def test_query_cache_avoids_repeat_calls() -> None:
    inner = FakeEmbedder()
    cached = CachedQueryEmbedder(inner)
    await cached.embed_query("What is the fee?")
    await cached.embed_query("  what is   the FEE? ")
    assert inner.calls == 1
    assert cached.hits == 1


def test_build_embedder_choices() -> None:
    assert build_embedder(make_settings(embedding_model="gemini-embedding-001")) is None  # no key
    assert build_embedder(make_settings(embedding_model=None, gemini_api_key="k")) is None
    fake = build_embedder(make_settings(embedding_model="fake"))
    assert fake is not None and fake.name == "fake-hashed-bow"
    gemini = build_embedder(
        make_settings(embedding_model="gemini-embedding-001", gemini_api_key="fake-key")
    )
    assert gemini is not None and gemini.name == "gemini-embedding-001"  # no network call


# --- grading -------------------------------------------------------------------------------


def _chunk(content: str, similarity: float | None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        content=content,
        title="Test",
        category=None,
        owner_name=None,
        last_verified=date(2026, 1, 1),
        expires_at=None,
        source_url=None,
        similarity=similarity,
        keyword_rank=None,
        score=0.03,
    )


def test_coverage_ignores_stopwords_and_matches_word_stems() -> None:
    assert coverage("What is the hostel fee?", "Hostel fees are listed") == 1.0
    assert coverage("kya hostel available hai", "The hostel has rooms") == 0.5


def test_grade_ok_by_similarity_or_coverage_and_weak_otherwise() -> None:
    kwargs = {"min_similarity": 0.6, "min_coverage": 0.5}
    assert grade("anything", [], **kwargs).reason == "no_results"
    assert grade("unrelated words", [_chunk("text", 0.8)], **kwargs).reason == "similarity"
    assert grade("hostel fee", [_chunk("hostel fee table", 0.1)], **kwargs).reason == (
        "keyword_coverage"
    )
    weak = grade("scholarship deadline", [_chunk("hostel rooms", 0.2)], **kwargs)
    assert not weak.ok and weak.reason == "weak_match"


def _openai_embedder(handler: Any, dim: int = 4) -> OpenAIEmbedder:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAIEmbedder("test-key", "text-embedding-3-small", dim, batch_size=2, client=client)


async def test_openai_embedder_asks_for_the_dimension_and_normalizes_in_order() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        data = [
            {"index": i, "embedding": [3.0, 4.0, 0.0, float(i)]} for i in range(len(body["input"]))
        ]
        return httpx.Response(200, json={"data": list(reversed(data))})

    vectors = await _openai_embedder(handler).embed_documents(["a", "b", "c"])
    assert [b["input"] for b in bodies] == [["a", "b"], ["c"]]  # batches
    assert all(b["dimensions"] == 4 and b["model"] == "text-embedding-3-small" for b in bodies)
    assert vectors[0] == [0.6, 0.8, 0.0, 0.0]  # index 0 first, normalized
    assert abs(sum(v * v for v in vectors[1]) - 1) < 1e-9


async def test_openai_embedder_errors_become_embedding_errors() -> None:
    with pytest.raises(EmbeddingError, match="status 429"):
        await _openai_embedder(lambda r: httpx.Response(429, json={})).embed_query("q")
    wrong_size = {"data": [{"index": 0, "embedding": [1.0, 2.0]}]}
    with pytest.raises(EmbeddingError, match="expected 4 dimensions"):
        await _openai_embedder(lambda r: httpx.Response(200, json=wrong_size)).embed_query("q")


def test_build_embedder_picks_openai_by_model_name() -> None:
    no_key = make_settings(embedding_model="text-embedding-3-small", gemini_api_key="g")
    assert build_embedder(no_key) is None  # an OpenAI model never falls back to Gemini
    openai = build_embedder(
        make_settings(embedding_model="text-embedding-3-small", openai_api_key="o-key")
    )
    assert openai is not None and (openai.name, openai.dim) == ("text-embedding-3-small", 768)
