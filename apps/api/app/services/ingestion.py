"""Ingestion (Architectural.md Section 7, DATA-3, DATA-5): chunk, embed, replace chunks.

Only APPROVED content gets chunks (D6). Re-indexing deletes the old chunks of that entry or
document and inserts the new ones in the caller's transaction, so search never sees a mix.
If embedding fails, chunks are stored without vectors (keyword search still finds them) and
the failure is logged; re-run `reindex` later.
"""

from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Chunk, Document, KbEntry
from app.services.chunking import chunk_text, entry_chunk
from app.services.embeddings import Embedder, EmbeddingError

log = get_logger("ingestion")


@dataclass(frozen=True)
class IndexResult:
    chunks: int
    embedded: bool


async def _embed(embedder: Embedder | None, texts: list[str]) -> list[list[float]] | None:
    if embedder is None or not texts:
        return None
    try:
        return await embedder.embed_documents(texts)
    except EmbeddingError as exc:
        log.warning("embedding_failed_keyword_only", error=str(exc), chunks=len(texts))
        return None


async def index_entry(
    session: AsyncSession, entry: KbEntry, embedder: Embedder | None
) -> IndexResult:
    await session.execute(delete(Chunk).where(Chunk.entry_id == entry.id))
    if entry.status != "approved":
        await session.flush()
        return IndexResult(chunks=0, embedded=False)

    text = entry_chunk(entry.title, entry.question, entry.answer)
    vectors = await _embed(embedder, [text])
    session.add(
        Chunk(
            institution_id=entry.institution_id,
            entry_id=entry.id,
            ord=0,
            content=text,
            embedding=vectors[0] if vectors else None,
            metadata_={
                "source": "kb_entry",
                "title": entry.title,
                "embedding_model": embedder.name if vectors and embedder else None,
            },
        )
    )
    await session.flush()
    return IndexResult(chunks=1, embedded=vectors is not None)


async def index_document(
    session: AsyncSession, document: Document, embedder: Embedder | None
) -> IndexResult:
    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    if document.status != "approved" or not document.content.strip():
        await session.flush()
        return IndexResult(chunks=0, embedded=False)

    pieces = chunk_text(document.content)
    # Prefix the title so short chunks still carry their context for search.
    texts = [f"{document.title}\n{piece}" for piece in pieces]
    vectors = await _embed(embedder, texts)
    for ord_, text in enumerate(texts):
        session.add(
            Chunk(
                institution_id=document.institution_id,
                document_id=document.id,
                ord=ord_,
                content=text,
                embedding=vectors[ord_] if vectors else None,
                metadata_={
                    "source": "document",
                    "title": document.title,
                    "embedding_model": embedder.name if vectors and embedder else None,
                },
            )
        )
    await session.flush()
    return IndexResult(chunks=len(texts), embedded=vectors is not None)
