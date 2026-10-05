"""Load an institution's seed directory (seed/<slug>/) into the database (ADP-1, ADP-2, OPS-3).

Idempotent: rows are matched by natural key and only changed columns are updated. Every create
or update writes an audit row in the same transaction. Rows are validated before anything is
written, so a bad file changes nothing. Facts come only from the seed files (Memory rule 1).
"""

import csv
import datetime as dt
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Department,
    Faculty,
    Fee,
    Institution,
    KbEntry,
    KeyDate,
    Office,
    Timetable,
)
from app.db.repositories.upsert import UpsertStats, upsert
from app.services import audit

DAY_NAMES = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value.strip() if isinstance(value, str) else value


def _pipe_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split("|") if part.strip()]


class _Row(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _blanks(cls, value: Any) -> Any:
        return _blank_to_none(value)


class DepartmentRow(_Row):
    name: str
    faculty: str | None = None


class OfficeRow(_Row):
    name: str
    phones: list[str] = Field(default_factory=list)
    email: str | None = None
    hours: str | None = None
    location: str | None = None
    topics: list[str] = Field(default_factory=list)
    last_verified: date
    source_name: str

    @field_validator("phones", "topics", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> list[str]:
        return _pipe_list(value)


class FeeRow(_Row):
    program_group: str
    level: str | None = None
    fiscal_year: str
    admission_fee: Decimal | None = None
    tuition_per_credit_hour: Decimal | None = None
    misc_per_semester: Decimal | None = None
    credit_hours_sem1: int | None = None
    notes: str | None = None
    last_verified: date
    source_name: str


class KeyDateRow(_Row):
    title: str
    date: dt.date  # `dt.date`: the field named `date` shadows the type in this class body
    kind: str
    program_scope: str | None = None
    office_name: str | None = None
    last_verified: dt.date
    source_name: str


class FacultyRow(_Row):
    name: str
    designation: str | None = None
    department: str | None = None
    email: str | None = None
    office_room: str | None = None
    courses: list[str] = Field(default_factory=list)
    status: str = "active"
    last_verified: date
    source_name: str

    @field_validator("courses", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> list[str]:
        return _pipe_list(value)


class TimetableRow(_Row):
    program: str
    semester: int = Field(ge=1, le=12)
    section: str | None = None
    day: int = Field(ge=1, le=7)
    start_time: time
    end_time: time
    course_code: str | None = None
    course_name: str
    faculty_name: str | None = None
    room: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    last_verified: date
    source_name: str

    @field_validator("day", mode="before")
    @classmethod
    def _day(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lower() in DAY_NAMES:
            return DAY_NAMES[value.strip().lower()]
        return value


class KbEntryRow(_Row):
    title: str
    question: str | None = None
    answer: str
    category: str
    owner_name: str | None = None
    language: str = "en"
    status: str = "approved"
    last_verified: date
    expires_at: date | None = None
    source_url: str | None = None


RowT = TypeVar("RowT", bound=_Row)


@dataclass
class SeedReport:
    institution_id: uuid.UUID | None = None
    tables: dict[str, UpsertStats] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [f"{'table':<12} created  updated  unchanged"]
        for table, stats in self.tables.items():
            lines.append(
                f"{table:<12} {stats.created:>7}  {stats.updated:>7}  {stats.unchanged:>9}"
            )
        return "\n".join(lines)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def parse_rows(rows: list[dict[str, Any]], model: type[RowT], source: str) -> list[RowT]:
    """Validate every row first; raise with the file and line number on the first error."""
    parsed: list[RowT] = []
    for number, row in enumerate(rows, start=2):  # line 1 is the CSV header
        try:
            parsed.append(model.model_validate(row))
        except ValueError as exc:
            raise ValueError(f"{source} row {number}: {exc}") from exc
    return parsed


async def load_seed_dir(
    session: AsyncSession,
    seed_dir: Path,
    *,
    actor_label: str = "seed",
    on_kb_entry: Callable[[KbEntry], Any] | None = None,
) -> SeedReport:
    """Load seed_dir into the database within the caller's transaction.

    `on_kb_entry` is called for every created or updated KB entry (used to chunk and embed).
    """
    report = SeedReport()
    meta = json.loads((seed_dir / "institution.json").read_text(encoding="utf-8"))

    # Validate all files before writing anything.
    departments = parse_rows(
        read_csv(seed_dir / "departments.csv"), DepartmentRow, "departments.csv"
    )
    offices = parse_rows(read_csv(seed_dir / "offices.csv"), OfficeRow, "offices.csv")
    fees = parse_rows(read_csv(seed_dir / "fees.csv"), FeeRow, "fees.csv")
    key_dates = parse_rows(read_csv(seed_dir / "key_dates.csv"), KeyDateRow, "key_dates.csv")
    faculty = parse_rows(read_csv(seed_dir / "faculty.csv"), FacultyRow, "faculty.csv")
    timetable = parse_rows(read_csv(seed_dir / "timetable.csv"), TimetableRow, "timetable.csv")
    kb_path = seed_dir / "kb_entries.json"
    kb_raw = (
        json.loads(kb_path.read_text(encoding="utf-8")).get("entries", [])
        if kb_path.exists()
        else []
    )
    kb_entries = parse_rows(kb_raw, KbEntryRow, "kb_entries.json")

    institution = (
        await session.execute(select(Institution).where(Institution.slug == meta["slug"]))
    ).scalar_one_or_none()
    stats = UpsertStats()
    if institution is None:
        institution = Institution(slug=meta["slug"], name=meta["name"], config=meta["config"])
        session.add(institution)
        await session.flush()
        audit.record(
            session,
            institution_id=institution.id,
            action="create",
            table_name="institutions",
            row_id=institution.id,
            diff={"new": meta},
            actor_label=actor_label,
        )
        stats.add("created", institution.id)
    elif institution.name != meta["name"] or institution.config != meta["config"]:
        diff = {"old": {"name": institution.name, "config": institution.config}, "new": meta}
        institution.name, institution.config = meta["name"], meta["config"]
        audit.record(
            session,
            institution_id=institution.id,
            action="update",
            table_name="institutions",
            row_id=institution.id,
            diff=diff,
            actor_label=actor_label,
        )
        stats.add("updated", institution.id)
    else:
        stats.add("unchanged", institution.id)
    report.tables["institutions"] = stats
    inst_id = institution.id
    report.institution_id = inst_id

    async def run(
        table: str, model: type[Any], items: list[tuple[dict[str, Any], dict[str, Any]]]
    ) -> list[Any]:
        table_stats = UpsertStats()
        rows = []
        for key, values in items:
            row, outcome = await upsert(
                session,
                model,
                key={"institution_id": inst_id, **key},
                values=values,
                institution_id=inst_id,
                actor_label=actor_label,
            )
            table_stats.add(outcome, row.id)
            rows.append((row, outcome))
        report.tables[table] = table_stats
        return rows

    dept_rows = await run(
        "departments",
        Department,
        [({"name": d.name}, {"faculty": d.faculty}) for d in departments],
    )
    dept_ids = {row.name: row.id for row, _ in dept_rows}

    await run(
        "offices",
        Office,
        [({"name": o.name}, o.model_dump(exclude={"name"})) for o in offices],
    )
    await run(
        "fees",
        Fee,
        [
            (
                {"program_group": f.program_group, "fiscal_year": f.fiscal_year},
                f.model_dump(exclude={"program_group", "fiscal_year"}),
            )
            for f in fees
        ],
    )
    await run(
        "key_dates",
        KeyDate,
        [
            ({"title": k.title, "date": k.date}, k.model_dump(exclude={"title", "date"}))
            for k in key_dates
        ],
    )
    await run(
        "faculty",
        Faculty,
        [
            (
                {"name": f.name},
                {
                    **f.model_dump(exclude={"name", "department"}),
                    "department_id": dept_ids.get(f.department) if f.department else None,
                },
            )
            for f in faculty
        ],
    )
    await run(
        "timetable",
        Timetable,
        [
            (
                {
                    "program": t.program,
                    "semester": t.semester,
                    "section": t.section,
                    "day": t.day,
                    "start_time": t.start_time,
                    "course_name": t.course_name,
                },
                t.model_dump(
                    exclude={"program", "semester", "section", "day", "start_time", "course_name"}
                ),
            )
            for t in timetable
        ],
    )
    kb_rows = await run(
        "kb_entries",
        KbEntry,
        [({"title": e.title}, e.model_dump(exclude={"title"})) for e in kb_entries],
    )
    if on_kb_entry is not None:
        for row, outcome in kb_rows:
            if outcome != "unchanged":
                result = on_kb_entry(row)
                if hasattr(result, "__await__"):
                    await result
    return report
