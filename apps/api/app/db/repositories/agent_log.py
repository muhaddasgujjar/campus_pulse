"""Agent reads and writes: unanswered queries (ANS-5, DATA-7), daily usage (COST-4) and the
content version for the response cache (COST-3)."""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, UnansweredQuery, UsageDaily


async def log_unanswered(
    session: AsyncSession,
    institution_id: uuid.UUID,
    redacted_query: str,
    reason: str,
    conversation_id: uuid.UUID | None,
) -> None:
    session.add(
        UnansweredQuery(
            institution_id=institution_id,
            query=redacted_query,
            reason=reason,
            conversation_id=conversation_id,
        )
    )
    await session.flush()


async def add_usage(
    session: AsyncSession,
    institution_id: uuid.UUID,
    day: date,
    *,
    llm_calls: int = 0,
    embed_calls: int = 0,
    cache_hits: int = 0,
    fallbacks: int = 0,
) -> None:
    """Atomic increment (one upsert), safe with concurrent turns."""
    stmt = insert(UsageDaily).values(
        day=day,
        institution_id=institution_id,
        llm_calls=llm_calls,
        embed_calls=embed_calls,
        cache_hits=cache_hits,
        fallbacks=fallbacks,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[UsageDaily.day, UsageDaily.institution_id],
        set_={
            "llm_calls": UsageDaily.llm_calls + stmt.excluded.llm_calls,
            "embed_calls": UsageDaily.embed_calls + stmt.excluded.embed_calls,
            "cache_hits": UsageDaily.cache_hits + stmt.excluded.cache_hits,
            "fallbacks": UsageDaily.fallbacks + stmt.excluded.fallbacks,
        },
    )
    await session.execute(stmt)


async def data_version(session: AsyncSession, institution_id: uuid.UUID) -> str:
    """Changes whenever content changes: every admin write records an audit row in the same
    transaction (rule 7), so the newest audit timestamp versions the data (COST-3)."""
    latest = await session.scalar(
        select(func.max(AuditLog.created_at)).where(AuditLog.institution_id == institution_id)
    )
    return latest.isoformat() if latest is not None else "0"
