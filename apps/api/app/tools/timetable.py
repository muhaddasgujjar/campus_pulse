"""get_timetable(program, semester, section=None, day=None). Missing arguments may be filled
from the student's profile by the agent (PER-2)."""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.db.repositories import structured as repo
from app.tools.base import Source, ToolContext, ToolResult, dedupe_sources, oldest

DAY_NUMBERS = {
    "mon": 1,
    "monday": 1,
    "tue": 2,
    "tues": 2,
    "tuesday": 2,
    "wed": 3,
    "wednesday": 3,
    "thu": 4,
    "thur": 4,
    "thurs": 4,
    "thursday": 4,
    "fri": 5,
    "friday": 5,
    "sat": 6,
    "saturday": 6,
    "sun": 7,
    "sunday": 7,
}
DAY_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday",
             6: "Saturday", 7: "Sunday"}  # fmt: skip


class TimetableArgs(BaseModel):
    program: str = Field(min_length=2, max_length=40, description="Program, e.g. BSCS")
    semester: int = Field(ge=1, le=12)
    section: str | None = Field(default=None, max_length=10)
    day: int | None = Field(default=None, ge=1, le=7, description="1 = Monday ... 7 = Sunday")

    @field_validator("day", mode="before")
    @classmethod
    def _day_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            key = value.strip().lower()
            if key in DAY_NUMBERS:
                return DAY_NUMBERS[key]
        return value


async def get_timetable(ctx: ToolContext, args: TimetableArgs) -> ToolResult:
    rows = await repo.find_timetable(
        ctx.session,
        ctx.institution_id,
        args.program,
        args.semester,
        args.section,
        args.day,
        ctx.today,
    )
    data = [
        {
            "program": row.program,
            "semester": row.semester,
            "section": row.section,
            "day": DAY_NAMES[row.day],
            "start_time": row.start_time.strftime("%H:%M"),
            "end_time": row.end_time.strftime("%H:%M"),
            "course_code": row.course_code,
            "course_name": row.course_name,
            "faculty": row.faculty_name,
            "room": row.room,
            "last_verified": row.last_verified,
        }
        for row in rows
    ]
    sources = dedupe_sources(
        [
            Source(title=row.source_name or "Timetable", last_verified=row.last_verified)
            for row in rows
        ]
    )
    return ToolResult(
        tool="get_timetable",
        data=data,
        sources=sources,
        last_verified=oldest([row.last_verified for row in rows]),
        owner=None,
    )
