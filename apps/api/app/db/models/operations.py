"""Operations: audit log (ADM-2, rule 7) and daily usage (COST-4)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, Timestamps, UUIDPk


class AuditLog(UUIDPk, Timestamps, Base):
    __tablename__ = "audit_log"
    # data_version for the response cache: the latest audit row per institution (COST-3).
    __table_args__ = (
        Index("ix_audit_log_institution_id_created_at", "institution_id", "created_at"),
    )

    # clock_timestamp(), not now(): now() is fixed per transaction, so the actions of one admin
    # write (create, update, approve) would share a timestamp and lose their order.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_label: Mapped[str | None] = mapped_column(Text)  # e.g. "cli:<os user>" before M5 auth
    action: Mapped[str] = mapped_column(Text)
    table_name: Mapped[str] = mapped_column(Text)
    row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    ip: Mapped[str | None] = mapped_column(INET)


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), primary_key=True
    )
    llm_calls: Mapped[int] = mapped_column(Integer, server_default="0")
    embed_calls: Mapped[int] = mapped_column(Integer, server_default="0")
    cache_hits: Mapped[int] = mapped_column(Integer, server_default="0")
    fallbacks: Mapped[int] = mapped_column(Integer, server_default="0")
