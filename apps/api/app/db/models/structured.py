"""Structured data queried by SQL tools, never by vector search (D3, ANS-2).

`source_name` (an addition to Architectural.md Section 5) names where a row came from, for
citations (ANS-6), e.g. "LGU website: Fee Structure page".
"""

import datetime as dt
import uuid
from datetime import date, time

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, Timestamps, UUIDPk


class Faculty(UUIDPk, Timestamps, Base):
    __tablename__ = "faculty"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    designation: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    email: Mapped[str | None] = mapped_column(Text)
    office_room: Mapped[str | None] = mapped_column(Text)
    courses: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    status: Mapped[str] = mapped_column(Text, server_default="active")
    last_verified: Mapped[date | None] = mapped_column(Date)
    source_name: Mapped[str | None] = mapped_column(Text)


class Timetable(UUIDPk, Timestamps, Base):
    __tablename__ = "timetable"
    __table_args__ = (
        CheckConstraint("day between 1 and 7", name="day"),
        CheckConstraint("start_time < end_time", name="times"),
    )

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    program: Mapped[str] = mapped_column(Text)
    semester: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(Text)
    # Staff scope (AUTH-3): the department that owns this timetable row.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    day: Mapped[int] = mapped_column(SmallInteger)  # 1 = Monday ... 7 = Sunday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    course_code: Mapped[str | None] = mapped_column(Text)
    course_name: Mapped[str] = mapped_column(Text)
    faculty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("faculty.id", ondelete="SET NULL")
    )
    faculty_name: Mapped[str | None] = mapped_column(Text)
    room: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    last_verified: Mapped[date | None] = mapped_column(Date)
    source_name: Mapped[str | None] = mapped_column(Text)


class Fee(UUIDPk, Timestamps, Base):
    __tablename__ = "fees"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    program_group: Mapped[str] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(Text)
    fiscal_year: Mapped[str] = mapped_column(Text)  # always stored and stated (ANS-6)
    admission_fee: Mapped[float | None] = mapped_column(Numeric(12, 2))
    tuition_per_credit_hour: Mapped[float | None] = mapped_column(Numeric(12, 2))
    misc_per_semester: Mapped[float | None] = mapped_column(Numeric(12, 2))
    credit_hours_sem1: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    last_verified: Mapped[date | None] = mapped_column(Date)
    source_name: Mapped[str | None] = mapped_column(Text)


class Office(UUIDPk, Timestamps, Base):
    __tablename__ = "offices"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    phones: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    email: Mapped[str | None] = mapped_column(Text)
    hours: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    last_verified: Mapped[date | None] = mapped_column(Date)
    source_name: Mapped[str | None] = mapped_column(Text)


class KeyDate(UUIDPk, Timestamps, Base):
    __tablename__ = "key_dates"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    # `dt.date` because the column named `date` shadows the type inside this class body.
    date: Mapped[dt.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(Text)
    program_scope: Mapped[str | None] = mapped_column(Text)
    office_name: Mapped[str | None] = mapped_column(Text)  # who to confirm with when passed
    last_verified: Mapped[dt.date | None] = mapped_column(Date)
    source_name: Mapped[str | None] = mapped_column(Text)


class LiveSource(UUIDPk, Timestamps, Base):
    __tablename__ = "live_sources"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    ttl_minutes: Mapped[int] = mapped_column(Integer, server_default="30")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="false")
