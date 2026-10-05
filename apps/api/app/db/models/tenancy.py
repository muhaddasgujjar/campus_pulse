"""Tenancy and people: institutions, departments, profiles (ADP-1, AUTH-1)."""

import uuid
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, Timestamps, UUIDPk


class Institution(UUIDPk, Timestamps, Base):
    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    # disclaimer, contacts, live-fetch allowlist, starter questions, fallback office (ADP-2)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")


class Department(UUIDPk, Timestamps, Base):
    __tablename__ = "departments"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    faculty: Mapped[str | None] = mapped_column(Text)


class Profile(Timestamps, Base):
    """Extends Supabase auth.users. The FK to auth.users is added by the migration only
    where that schema exists (Supabase), so local and CI databases work without it."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("role in ('student','staff','admin')", name="role"),
        CheckConstraint("semester is null or semester between 1 and 12", name="semester"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(Text, server_default="student")
    full_name: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    program: Mapped[str | None] = mapped_column(Text)
    semester: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(Text)
    language_pref: Mapped[str | None] = mapped_column(Text)
