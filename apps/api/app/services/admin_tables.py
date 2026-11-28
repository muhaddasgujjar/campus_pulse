"""CRUD for the structured tables in the admin portal (DATA-1): faculty, timetable, fees,
offices, key dates.

- These rows feed the SQL tools directly (D3), so a saved change is live at once. Answers stay
  dated because `last_verified` and `source_name` are required on every write (D6).
- Staff scope (AUTH-3): faculty and timetable rows by department, an office row by the office
  itself. Fees and key dates have no owner column, so they are admin-only.
- Every write records an audit row in the same transaction (rule 7); the newest audit row is
  the cache's data_version, so cached answers are replaced immediately (COST-3).
"""

import datetime as dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.core.rbac import can_edit_row
from app.db.models import Base, Faculty, Fee, KeyDate, Office, Timetable
from app.services import audit
from app.services.content_admin import ContentError

Scope = tuple[uuid.UUID | None, uuid.UUID | None]  # (department_id, office_id)


class _In(BaseModel):
    last_verified: dt.date
    source_name: str = Field(min_length=1, max_length=200)

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class FacultyIn(_In):
    name: str = Field(min_length=1, max_length=200)
    designation: str | None = Field(default=None, max_length=200)
    department_id: uuid.UUID | None = None
    email: str | None = Field(default=None, max_length=200)
    office_room: str | None = Field(default=None, max_length=100)
    courses: list[str] = Field(default_factory=list, max_length=50)
    status: Literal["active", "on_leave", "left"] = "active"


class TimetableIn(_In):
    program: str = Field(min_length=1, max_length=50)
    semester: int = Field(ge=1, le=12)
    section: str | None = Field(default=None, max_length=20)
    department_id: uuid.UUID | None = None
    day: int = Field(ge=1, le=7)
    start_time: dt.time
    end_time: dt.time
    course_code: str | None = Field(default=None, max_length=30)
    course_name: str = Field(min_length=1, max_length=200)
    faculty_name: str | None = Field(default=None, max_length=200)
    room: str | None = Field(default=None, max_length=50)
    effective_from: dt.date | None = None
    effective_to: dt.date | None = None

    @model_validator(mode="after")
    def _times(self) -> "TimetableIn":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class FeeIn(_In):
    program_group: str = Field(min_length=1, max_length=100)
    level: str | None = Field(default=None, max_length=50)
    fiscal_year: str = Field(min_length=4, max_length=20)  # always stated in answers (ANS-6)
    admission_fee: Decimal | None = Field(default=None, ge=0)
    tuition_per_credit_hour: Decimal | None = Field(default=None, ge=0)
    misc_per_semester: Decimal | None = Field(default=None, ge=0)
    credit_hours_sem1: int | None = Field(default=None, ge=0, le=40)
    notes: str | None = Field(default=None, max_length=1000)


class OfficeIn(_In):
    name: str = Field(min_length=1, max_length=200)
    phones: list[str] = Field(default_factory=list, max_length=10)
    email: str | None = Field(default=None, max_length=200)
    hours: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    topics: list[str] = Field(default_factory=list, max_length=50)


class KeyDateIn(_In):
    title: str = Field(min_length=1, max_length=200)
    date: dt.date
    kind: Literal["admission", "fee", "scholarship", "exam", "semester", "holiday", "other"]
    program_scope: str | None = Field(default=None, max_length=100)
    office_name: str | None = Field(default=None, max_length=200)


@dataclass(frozen=True)
class TableSpec:
    name: str  # URL segment, e.g. "key-dates"
    model: type[Base]
    schema: type[_In]
    search: tuple[str, ...]  # text columns for ?q=
    order: tuple[str, ...]
    scope: Callable[[dict[str, Any], uuid.UUID | None], Scope]  # (values, row id) -> scope


def _department(values: dict[str, Any], _row_id: uuid.UUID | None) -> Scope:
    return values.get("department_id"), None


def _office(_values: dict[str, Any], row_id: uuid.UUID | None) -> Scope:
    return None, row_id


def _nobody(_values: dict[str, Any], _row_id: uuid.UUID | None) -> Scope:
    return None, None


TABLES: dict[str, TableSpec] = {
    spec.name: spec
    for spec in (
        TableSpec("faculty", Faculty, FacultyIn, ("name", "designation", "email"), ("name",),
                  _department),
        TableSpec("timetable", Timetable, TimetableIn, ("program", "course_name", "course_code",
                  "faculty_name", "room"), ("program", "semester", "section", "day",
                  "start_time"), _department),
        TableSpec("fees", Fee, FeeIn, ("program_group", "level", "fiscal_year"),
                  ("program_group",), _nobody),
        TableSpec("offices", Office, OfficeIn, ("name", "email", "location"), ("name",), _office),
        TableSpec("key-dates", KeyDate, KeyDateIn, ("title", "kind", "program_scope"), ("date",),
                  _nobody),
    )
}  # fmt: skip


def row_values(spec: TableSpec, row: Any) -> dict[str, Any]:
    return {name: getattr(row, name) for name in spec.schema.model_fields}


def row_scope(spec: TableSpec, row: Any) -> Scope:
    return spec.scope(row_values(spec, row), row.id)


def can_edit(
    user: AuthenticatedUser, spec: TableSpec, row: Any | None, values: dict[str, Any]
) -> bool:
    """A create needs the new values in scope; an update needs the row and the new values."""
    row_id = row.id if row is not None else None
    if row is None and spec.scope is _office and user.role != "admin":
        return False  # only an admin adds an office (staff edit their own office row)
    department, office = spec.scope(values, row_id)
    if not can_edit_row(user, department_id=department, office_id=office):
        return False
    if row is not None:
        department, office = row_scope(spec, row)
        return can_edit_row(user, department_id=department, office_id=office)
    return True


async def list_rows(
    session: AsyncSession,
    spec: TableSpec,
    institution_id: uuid.UUID,
    *,
    query: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Any]:
    model: Any = spec.model
    stmt = select(model).where(model.institution_id == institution_id)
    if query:
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(*(cast(getattr(model, column), String).ilike(pattern) for column in spec.search))
        )
    stmt = stmt.order_by(*(getattr(model, column) for column in spec.order), model.id)
    return list((await session.execute(stmt.limit(limit).offset(offset))).scalars())


async def get_row(
    session: AsyncSession, spec: TableSpec, institution_id: uuid.UUID, row_id: uuid.UUID
) -> Any:
    row: Any = await session.get(spec.model, row_id)
    if row is None or row.institution_id != institution_id:
        raise ContentError(f"Row {row_id} not found in {spec.name}.")
    return row


def _record(
    session: AsyncSession,
    spec: TableSpec,
    user: AuthenticatedUser,
    action: str,
    row_id: uuid.UUID,
    diff: dict[str, Any],
) -> None:
    audit.record(
        session,
        institution_id=user.institution_id,
        action=action,
        table_name=spec.model.__tablename__,
        row_id=row_id,
        diff=diff,
        actor_label=user.label,
        actor_id=user.user_id,
    )


async def create_row(
    session: AsyncSession, spec: TableSpec, user: AuthenticatedUser, data: _In
) -> Any:
    values = data.model_dump()
    row: Any = spec.model(institution_id=user.institution_id, **values)
    session.add(row)
    await session.flush()
    _record(session, spec, user, "create", row.id, {"new": values})
    return row


def _same(current: Any, new: Any) -> bool:
    if isinstance(current, Decimal) and new is not None:
        return current == Decimal(str(new))
    return bool(current == new)


async def update_row(
    session: AsyncSession, spec: TableSpec, user: AuthenticatedUser, row: Any, data: _In
) -> Any:
    values = data.model_dump()
    changes = {
        name: {"old": getattr(row, name), "new": value}
        for name, value in values.items()
        if not _same(getattr(row, name), value)
    }
    if not changes:
        return row
    for name, change in changes.items():
        setattr(row, name, change["new"])
    await session.flush()
    _record(session, spec, user, "update", row.id, changes)
    return row


async def delete_row(
    session: AsyncSession, spec: TableSpec, user: AuthenticatedUser, row: Any
) -> None:
    old = row_values(spec, row)
    row_id = row.id
    await session.delete(row)
    await session.flush()
    _record(session, spec, user, "delete", row_id, {"old": old})
