"""Ingestion and hybrid retrieval against Postgres + pgvector (FAKE content, fake embedder)."""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Institution, KbEntry
from app.services.embeddings import EmbeddingError, FakeEmbedder
from app.services.ingestion import index_entry
from app.services.retrieval import grade, search
from app.tools import ToolContext
from app.tools.search import SearchArgs, search_knowledge

pytestmark = pytest.mark.integration

TODAY = date(2026, 10, 5)


class FailingEmbedder(FakeEmbedder):
    async def embed_query(self, text: str) -> list[float]:
        raise EmbeddingError("quota exceeded (test)")


async def _entry(
    session: AsyncSession, inst: uuid.UUID, title: str, answer: str, **extra: object
) -> KbEntry:
    values: dict[str, object] = {
        "category": "other",
        "status": "approved",
        "owner_name": "Test Office",
        "last_verified": date(2026, 9, 1),
    }
    values.update(extra)
    entry = KbEntry(institution_id=inst, title=title, answer=answer, **values)
    session.add(entry)
    await session.flush()
    return entry


@pytest.fixture
async def kb(db_session: AsyncSession) -> tuple[uuid.UUID, FakeEmbedder]:
    inst = Institution(slug="test-uni", name="Test University", config={})
    db_session.add(inst)
    await db_session.flush()
    embedder = FakeEmbedder()
    entries = [
        await _entry(
            db_session,
            inst.id,
            "Test hostel rooms",
            "Hostel rooms at Test University are shared by two students.",
            category="hostel",
        ),
        await _entry(
            db_session,
            inst.id,
            "Test scholarship deadline",
            "Scholarship forms for the test program close in November.",
            category="scholarships",
        ),
        await _entry(
            db_session,
            inst.id,
            "Test library hours",
            "The test library opens at nine in the morning.",
            expires_at=date(2026, 1, 1),
        ),
        await _entry(
            db_session,
            inst.id,
            "Draft hostel fee",
            "Hostel fee draft that is not approved yet.",
            status="pending",
        ),
    ]
    for entry in entries:
        await index_entry(db_session, entry, embedder)
    return inst.id, embedder


async def test_only_approved_entries_get_chunks(
    db_session: AsyncSession, kb: tuple[uuid.UUID, FakeEmbedder]
) -> None:
    count = (await db_session.execute(select(func.count()).select_from(Chunk))).scalar_one()
    assert count == 3
    embedded = (
        await db_session.execute(
            select(func.count()).select_from(Chunk).where(Chunk.embedding.is_not(None))
        )
    ).scalar_one()
    assert embedded == 3


async def test_reindex_replaces_chunks(
    db_session: AsyncSession, kb: tuple[uuid.UUID, FakeEmbedder]
) -> None:
    _, embedder = kb
    entry = (
        await db_session.execute(select(KbEntry).where(KbEntry.title == "Test hostel rooms"))
    ).scalar_one()
    entry.answer = "Hostel rooms are now single rooms (test update)."
    await index_entry(db_session, entry, embedder)
    chunks = (
        (await db_session.execute(select(Chunk).where(Chunk.entry_id == entry.id))).scalars().all()
    )
    assert len(chunks) == 1
    assert "single rooms" in chunks[0].content


async def test_hybrid_search_finds_the_right_entry(
    db_session: AsyncSession, kb: tuple[uuid.UUID, FakeEmbedder]
) -> None:
    inst, embedder = kb
    result = await search(db_session, embedder, inst, "Are hostel rooms shared?", k=3)
    assert result.chunks[0].title == "Test hostel rooms"
    assert result.chunks[0].similarity is not None
    assert result.chunks[0].keyword_rank == 1
    assert not result.embedding_failed
    assert "Draft hostel fee" not in [c.title for c in result.chunks]  # never unapproved


async def test_keyword_only_when_query_embedding_fails(
    db_session: AsyncSession, kb: tuple[uuid.UUID, FakeEmbedder]
) -> None:
    inst, _ = kb
    result = await search(db_session, FailingEmbedder(), inst, "scholarship deadline", k=3)
    assert result.embedding_failed
    assert result.chunks[0].title == "Test scholarship deadline"
    assert result.chunks[0].similarity is None


async def test_category_filter(
    db_session: AsyncSession, kb: tuple[uuid.UUID, FakeEmbedder]
) -> None:
    inst, embedder = kb
    result = await search(db_session, embedder, inst, "hostel", category="scholarships", k=3)
    assert {c.category for c in result.chunks} <= {"scholarships"}


async def test_grade_rejects_unrelated_questions(
    db_session: AsyncSession, kb: tuple[uuid.UUID, FakeEmbedder]
) -> None:
    inst, embedder = kb
    query = "What is the transport bus route to campus?"
    result = await search(db_session, embedder, inst, query, k=3)
    verdict = grade(query, result.chunks, min_similarity=0.62, min_coverage=0.5)
    assert not verdict.ok


async def test_search_tool_marks_expired_sources(
    db_session: AsyncSession, kb: tuple[uuid.UUID, FakeEmbedder]
) -> None:
    inst, embedder = kb
    ctx = ToolContext(session=db_session, institution_id=inst, today=TODAY)
    tool_result, _ = await search_knowledge(
        ctx, SearchArgs(query="library opening hours"), embedder
    )
    top = tool_result.sources[0]
    assert top.title == "Test library hours"
    assert top.expired is True
    assert top.office == "Test Office"


async def test_other_institutions_are_invisible(
    db_session: AsyncSession, kb: tuple[uuid.UUID, FakeEmbedder]
) -> None:
    _, embedder = kb
    other = Institution(slug="other-uni", name="Other University", config={})
    db_session.add(other)
    await db_session.flush()
    result = await search(db_session, embedder, other.id, "hostel rooms", k=3)
    assert result.chunks == []
