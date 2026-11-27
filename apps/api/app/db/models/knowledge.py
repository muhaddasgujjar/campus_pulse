"""Knowledge for RAG: kb_entries, documents, chunks (D4, D6, D17, DATA-1 to DATA-9)."""

import uuid
from datetime import date
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Computed, Date, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, Timestamps, UUIDPk

# D17: gemini-embedding-001 at 768 dimensions. Changing it needs a migration and a re-embed.
EMBEDDING_DIM = 768

CONTENT_STATUSES = ("draft", "pending", "approved", "archived")
_STATUS_CHECK = "status in ('draft','pending','approved','archived')"


class KbEntry(UUIDPk, Timestamps, Base):
    __tablename__ = "kb_entries"
    __table_args__ = (CheckConstraint(_STATUS_CHECK, name="status"),)

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    question: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    language: Mapped[str] = mapped_column(Text, server_default="en")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    # Display name of the owning office for the "Verified by" badge (seeds have no user owner).
    owner_name: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, server_default="draft", index=True)
    last_verified: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    rejected_reason: Mapped[str | None] = mapped_column(Text)


class Document(UUIDPk, Timestamps, Base):
    __tablename__ = "documents"
    __table_args__ = (CheckConstraint(_STATUS_CHECK, name="status"),)

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    owner_name: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)  # Supabase Storage key (M5)
    mime: Mapped[str] = mapped_column(Text, server_default="application/pdf")
    # Extracted text, so approval can (re)chunk without re-reading the file.
    content: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[str] = mapped_column(Text, server_default="pending", index=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    last_verified: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)


class Chunk(UUIDPk, Timestamps, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint("(entry_id is not null) <> (document_id is not null)", name="one_parent"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("kb_entries.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ord: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    # Null when embedding failed or no embedder was configured: keyword search still works.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # English stemming plus 'simple' (no stemming) so Roman Urdu words still match.
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', content) || to_tsvector('simple', content)", persisted=True
        ),
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default="{}")
