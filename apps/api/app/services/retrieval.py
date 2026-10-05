"""Retrieval and deterministic grading (ANS-3, ANS-4, Architectural.md Sections 6, 7, 15).

search(): one call to the hybrid_search SQL function (vector + full-text, RRF, approved only).
If the query embedding fails, the search runs keyword-only and says so.
grade(): no LLM. Retrieval is strong enough when the best chunk is semantically close
(cosine similarity) or covers enough of the question's content words.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import EMBEDDING_DIM
from app.services.embeddings import Embedder, EmbeddingError

log = get_logger("retrieval")

_SEARCH_SQL = text(
    "select * from hybrid_search(:query_text, :query_embedding, :match_count, "
    ":institution_id, :category)"
).bindparams(bindparam("query_embedding", type_=Vector(EMBEDDING_DIM)))

# Words that carry no meaning for coverage (English and common Roman Urdu fillers).
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "am",
        "do",
        "does",
        "did",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "from",
        "by",
        "with",
        "and",
        "or",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "why",
        "how",
        "can",
        "could",
        "should",
        "would",
        "will",
        "shall",
        "may",
        "might",
        "must",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "it",
        "they",
        "them",
        "their",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "please",
        "tell",
        "about",
        "any",
        "some",
        "much",
        "many",
        "get",
        "got",
        "give",
        "know",
        "want",
        "need",
        "lgu",
        "university",
        "kya",
        "hai",
        "hain",
        "ka",
        "ki",
        "ke",
        "ko",
        "se",
        "mein",
        "mai",
        "main",
        "aur",
        "ya",
        "kab",
        "kahan",
        "kaise",
        "kitni",
        "kitna",
        "kon",
        "kaun",
        "mujhe",
        "hum",
        "tum",
        "aap",
        "batao",
        "bataein",
    ]
)
_WORD = re.compile(r"[\w']+", re.UNICODE)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    content: str
    title: str
    category: str | None
    owner_name: str | None
    last_verified: date | None
    expires_at: date | None
    source_url: str | None
    similarity: float | None
    keyword_rank: int | None
    score: float


@dataclass(frozen=True)
class SearchResult:
    chunks: list[RetrievedChunk]
    embedding_failed: bool


@dataclass(frozen=True)
class Grade:
    ok: bool
    reason: str
    best_similarity: float | None
    best_coverage: float


def content_terms(text_: str) -> set[str]:
    return {
        w for w in (t.lower() for t in _WORD.findall(text_)) if len(w) > 2 and w not in STOPWORDS
    }


def coverage(query: str, content: str) -> float:
    """Fraction of the query's content words that appear in the chunk (prefix match, so
    'fee' matches 'fees' and 'eligible' matches 'eligibility')."""
    terms = content_terms(query)
    if not terms:
        return 0.0
    words = content_terms(content)
    hits = sum(1 for t in terms if any(w.startswith(t[:5]) or t.startswith(w[:5]) for w in words))
    return hits / len(terms)


async def search(
    session: AsyncSession,
    embedder: Embedder | None,
    institution_id: uuid.UUID,
    query: str,
    *,
    category: str | None = None,
    k: int = 5,
) -> SearchResult:
    embedding: list[float] | None = None
    embedding_failed = False
    if embedder is not None:
        try:
            embedding = await embedder.embed_query(query)
        except EmbeddingError as exc:
            embedding_failed = True
            log.warning("query_embedding_failed_keyword_only", error=str(exc))
    rows = (
        await session.execute(
            _SEARCH_SQL,
            {
                "query_text": query,
                "query_embedding": embedding,
                "match_count": k,
                "institution_id": institution_id,
                "category": category,
            },
        )
    ).mappings()
    chunks = [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            content=row["content"],
            title=row["title"],
            category=row["category"],
            owner_name=row["owner_name"],
            last_verified=row["last_verified"],
            expires_at=row["expires_at"],
            source_url=row["source_url"],
            similarity=row["similarity"],
            keyword_rank=row["keyword_rank"],
            score=float(row["score"]),
        )
        for row in rows
    ]
    return SearchResult(chunks=chunks, embedding_failed=embedding_failed or embedder is None)


def grade(
    query: str, chunks: list[RetrievedChunk], *, min_similarity: float, min_coverage: float
) -> Grade:
    if not chunks:
        return Grade(False, "no_results", None, 0.0)
    best_similarity = max((c.similarity for c in chunks if c.similarity is not None), default=None)
    best_coverage = max(coverage(query, f"{c.title} {c.content}") for c in chunks)
    if best_similarity is not None and best_similarity >= min_similarity:
        return Grade(True, "similarity", best_similarity, best_coverage)
    if best_coverage >= min_coverage:
        return Grade(True, "keyword_coverage", best_similarity, best_coverage)
    return Grade(False, "weak_match", best_similarity, best_coverage)
