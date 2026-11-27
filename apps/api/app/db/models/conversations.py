"""Conversations, messages, feedback and unanswered queries (CHAT, ANS-5, DATA-7)."""

import uuid
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, Timestamps, UUIDPk


class Conversation(UUIDPk, Timestamps, Base):
    __tablename__ = "conversations"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    # References auth.users on Supabase (FK added by the migration where auth exists).
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    channel: Mapped[str] = mapped_column(Text, server_default="web")
    language: Mapped[str | None] = mapped_column(Text)


class Message(UUIDPk, Timestamps, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role in ('user','assistant')", name="role"),
        CheckConstraint("modality in ('text','voice')", name="modality"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(Text, server_default="text")
    content: Mapped[str] = mapped_column(Text)  # user text is redacted before storing
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    tool_used: Mapped[str | None] = mapped_column(Text)
    cache_hit: Mapped[bool] = mapped_column(Boolean, server_default="false")
    llm_calls: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)


class Feedback(UUIDPk, Timestamps, Base):
    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("rating in (-1, 1)", name="rating"),)

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)


class UnansweredQuery(UUIDPk, Timestamps, Base):
    __tablename__ = "unanswered_queries"
    __table_args__ = (CheckConstraint("status in ('open','handled','ignored')", name="status"),)

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    query: Mapped[str] = mapped_column(Text)  # redacted
    reason: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, server_default="open")
    resolved_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("kb_entries.id", ondelete="SET NULL")
    )
