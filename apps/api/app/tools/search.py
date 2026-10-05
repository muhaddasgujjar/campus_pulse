"""search_knowledge(query, category=None, k=5): RAG over approved KB entries and documents."""

from pydantic import BaseModel, Field

from app.services.embeddings import Embedder
from app.services.retrieval import SearchResult, search
from app.tools.base import Source, ToolContext, ToolResult, dedupe_sources, oldest


class SearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    category: str | None = Field(default=None, max_length=40)
    k: int = Field(default=5, ge=1, le=10)


def to_tool_result(ctx: ToolContext, result: SearchResult) -> ToolResult:
    chunks = result.chunks
    data = [
        {
            "title": c.title,
            "content": c.content,
            "owner": c.owner_name,
            "last_verified": c.last_verified,
            "expired": bool(c.expires_at and c.expires_at < ctx.today),
            "similarity": c.similarity,
            "keyword_rank": c.keyword_rank,
        }
        for c in chunks
    ]
    sources = dedupe_sources(
        [
            Source(
                title=c.title,
                office=c.owner_name,
                url=c.source_url,
                last_verified=c.last_verified,
                expired=bool(c.expires_at and c.expires_at < ctx.today),
            )
            for c in chunks
        ]
    )
    return ToolResult(
        tool="search_knowledge",
        data=data,
        sources=sources,
        last_verified=oldest([c.last_verified for c in chunks]),
        owner=chunks[0].owner_name if chunks else None,
        score=chunks[0].score if chunks else None,
    )


async def search_knowledge(
    ctx: ToolContext, args: SearchArgs, embedder: Embedder | None
) -> tuple[ToolResult, SearchResult]:
    result = await search(
        ctx.session, embedder, ctx.institution_id, args.query, category=args.category, k=args.k
    )
    return to_tool_result(ctx, result), result
