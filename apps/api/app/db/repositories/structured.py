"""Read-only, parameterized queries over the structured tables (D3, ANS-2, SEC-2).

User and LLM text is only ever passed as bound parameters, never concatenated into SQL.
"""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any, TypeVar

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.db.models import Department, Faculty, Fee, KeyDate, Office, Timetable


def _squash(column: InstrumentedAttribute[Any]) -> ColumnElement[str]:
    """Lower-case and remove whitespace, so 'BS CS', 'bscs' and 'BSCS' compare equal."""
    return func.lower(func.regexp_replace(column, r"\s+", "", "g"))


def squash(text: str) -> str:
    return "".join(text.split()).lower()


def _contains(value: str) -> str:
    """LIKE pattern with LIKE wildcards in the input escaped."""
    escaped = value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


T = TypeVar("T")


async def _all(session: AsyncSession, stmt: Select[T]) -> Sequence[T]:
    return (await session.execute(stmt)).scalars().all()


async def find_fees(
    session: AsyncSession, institution_id: uuid.UUID, program_group: str, level: str | None
) -> Sequence[Fee]:
    stmt = select(Fee).where(
        Fee.institution_id == institution_id,
        _squash(Fee.program_group).like(_contains(squash(program_group))),
    )
    if level:
        stmt = stmt.where(Fee.level.ilike(_contains(level.strip())))
    return await _all(session, stmt.order_by(Fee.fiscal_year.desc(), Fee.program_group))


async def find_offices(
    session: AsyncSession, institution_id: uuid.UUID, name_or_topic: str
) -> Sequence[Office]:
    query = name_or_topic.strip().lower()
    topic = func.unnest(Office.topics).table_valued("value").render_derived(name="topic")
    topic_match = (
        select(1)
        .select_from(topic)
        .where(
            or_(
                # the topic appears in the question ("when is my exam" -> "exam")
                func.strpos(query, func.lower(topic.c.value)) > 0,
                func.lower(topic.c.value).like(_contains(query)),
            )
        )
        .exists()
    )
    name_match = func.lower(Office.name).like(_contains(query))
    stmt = (
        select(Office)
        .where(Office.institution_id == institution_id, or_(name_match, topic_match))
        .order_by(name_match.desc(), Office.name)
    )
    return await _all(session, stmt)


async def find_key_dates(
    session: AsyncSession,
    institution_id: uuid.UUID,
    kind: str | None,
    program_scope: str | None,
    from_date: date | None,
) -> Sequence[KeyDate]:
    stmt = select(KeyDate).where(KeyDate.institution_id == institution_id)
    if kind:
        stmt = stmt.where(func.lower(KeyDate.kind) == kind.strip().lower())
    if program_scope:
        # dates without a scope apply to everyone
        stmt = stmt.where(
            or_(
                KeyDate.program_scope.is_(None),
                _squash(KeyDate.program_scope).like(_contains(squash(program_scope))),
            )
        )
    if from_date:
        stmt = stmt.where(KeyDate.date >= from_date)
    return await _all(session, stmt.order_by(KeyDate.date))


async def find_faculty(
    session: AsyncSession,
    institution_id: uuid.UUID,
    name: str | None,
    department: str | None,
    course: str | None,
) -> Sequence[tuple[Faculty, str | None]]:
    stmt = (
        select(Faculty, Department.name)
        .outerjoin(Department, Department.id == Faculty.department_id)
        .where(Faculty.institution_id == institution_id, Faculty.status == "active")
    )
    if name:
        stmt = stmt.where(Faculty.name.ilike(_contains(name.strip())))
    if department:
        stmt = stmt.where(
            or_(
                Department.name.ilike(_contains(department.strip())),
                Department.faculty.ilike(_contains(department.strip())),
            )
        )
    if course:
        course_value = (
            func.unnest(Faculty.courses).table_valued("value").render_derived(name="course")
        )
        stmt = stmt.where(
            select(1)
            .select_from(course_value)
            .where(course_value.c.value.ilike(_contains(course.strip())))
            .exists()
        )
    rows = (await session.execute(stmt.order_by(Faculty.name).limit(20))).all()
    return [(row[0], row[1]) for row in rows]


async def find_timetable(
    session: AsyncSession,
    institution_id: uuid.UUID,
    program: str,
    semester: int,
    section: str | None,
    day: int | None,
    today: date,
) -> Sequence[Timetable]:
    stmt = select(Timetable).where(
        Timetable.institution_id == institution_id,
        _squash(Timetable.program) == squash(program),
        Timetable.semester == semester,
        and_(
            or_(Timetable.effective_from.is_(None), Timetable.effective_from <= today),
            or_(Timetable.effective_to.is_(None), Timetable.effective_to >= today),
        ),
    )
    if section:
        stmt = stmt.where(func.lower(Timetable.section) == section.strip().lower())
    if day:
        stmt = stmt.where(Timetable.day == day)
    return await _all(session, stmt.order_by(Timetable.day, Timetable.start_time))
