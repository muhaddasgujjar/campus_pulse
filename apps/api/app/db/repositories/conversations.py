"""Conversations and messages (CHAT-1, CHAT-9). User text is redacted by the caller (SEC-3)."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message


async def get_or_create_conversation(
    session: AsyncSession,
    institution_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    language: str | None = None,
) -> Conversation:
    """The client's conversation if it exists for this institution, else a new one.

    A client never chooses the id of a new conversation: ids are server generated."""
    if conversation_id is not None:
        found = await session.get(Conversation, conversation_id)
        if found is not None and found.institution_id == institution_id:
            return found
    conversation = Conversation(institution_id=institution_id, channel="web", language=language)
    session.add(conversation)
    await session.flush()
    return conversation


async def add_message(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    *,
    modality: str = "text",
    sources: list[dict[str, Any]] | None = None,
    tool_used: str | None = None,
    cache_hit: bool = False,
    llm_calls: int = 0,
    latency_ms: int | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        modality=modality,
        content=content,
        sources=sources or [],
        tool_used=tool_used,
        cache_hit=cache_hit,
        llm_calls=llm_calls,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
    session.add(message)
    await session.flush()
    return message


async def list_messages(
    session: AsyncSession, conversation_id: uuid.UUID, limit: int = 100
) -> Sequence[Message]:
    """The newest `limit` messages, oldest first."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(reversed(rows))


async def assistant_messages_after(
    session: AsyncSession, conversation_id: uuid.UUID, last_message_id: uuid.UUID | None
) -> Sequence[Message]:
    """Assistant messages the client has not seen (resume after a dropped socket, CHAT-9)."""
    stmt = select(Message).where(
        Message.conversation_id == conversation_id, Message.role == "assistant"
    )
    if last_message_id is not None:
        last = await session.get(Message, last_message_id)
        if last is None or last.conversation_id != conversation_id:
            return []
        stmt = stmt.where(Message.created_at > last.created_at)
    else:
        return []
    return (await session.execute(stmt.order_by(Message.created_at))).scalars().all()
