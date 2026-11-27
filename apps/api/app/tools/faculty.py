"""find_faculty(name=None, department=None, course=None)."""

from pydantic import BaseModel, Field, model_validator

from app.db.repositories import structured as repo
from app.tools.base import Source, ToolContext, ToolResult, dedupe_sources, oldest


class FacultyArgs(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    department: str | None = Field(default=None, max_length=80)
    course: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def _at_least_one(self) -> "FacultyArgs":
        if not (self.name or self.department or self.course):
            raise ValueError("give at least one of name, department or course")
        return self


async def find_faculty(ctx: ToolContext, args: FacultyArgs) -> ToolResult:
    rows = await repo.find_faculty(
        ctx.session, ctx.institution_id, args.name, args.department, args.course
    )
    data = [
        {
            "name": member.name,
            "designation": member.designation,
            "department": department,
            "email": member.email,
            "office_room": member.office_room,
            "courses": list(member.courses),
            "last_verified": member.last_verified,
        }
        for member, department in rows
    ]
    sources = dedupe_sources(
        [
            Source(
                title=member.source_name or "Faculty directory",
                office=department,
                last_verified=member.last_verified,
            )
            for member, department in rows
        ]
    )
    return ToolResult(
        tool="find_faculty",
        data=data,
        sources=sources,
        last_verified=oldest([member.last_verified for member, _ in rows]),
        owner=rows[0][1] if rows else None,
    )
