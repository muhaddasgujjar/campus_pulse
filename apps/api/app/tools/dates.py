"""get_key_dates(kind=None, program_scope=None, from_date=None) with a `passed` flag (ANS-7)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.db.repositories import structured as repo
from app.tools.base import Source, ToolContext, ToolResult, dedupe_sources, oldest

DateKind = Literal["admission", "fee", "scholarship", "exam", "semester", "holiday", "other"]


class KeyDatesArgs(BaseModel):
    kind: DateKind | None = Field(default=None, description="Type of date")
    program_scope: str | None = Field(default=None, max_length=80)
    from_date: date | None = Field(
        default=None, description="Only dates on or after this day (YYYY-MM-DD)"
    )


async def get_key_dates(ctx: ToolContext, args: KeyDatesArgs) -> ToolResult:
    rows = await repo.find_key_dates(
        ctx.session, ctx.institution_id, args.kind, args.program_scope, args.from_date
    )
    data = [
        {
            "title": row.title,
            "date": row.date,
            "kind": row.kind,
            "program_scope": row.program_scope,
            "office": row.office_name,
            # Compared with today on every call, never trusted from the LLM (ANS-7).
            "passed": row.date < ctx.today,
            "days_left": (row.date - ctx.today).days,
            "last_verified": row.last_verified,
        }
        for row in rows
    ]
    sources = dedupe_sources(
        [
            Source(
                title=row.source_name or "Key dates",
                office=row.office_name,
                last_verified=row.last_verified,
            )
            for row in rows
        ]
    )
    return ToolResult(
        tool="get_key_dates",
        data=data,
        sources=sources,
        last_verified=oldest([row.last_verified for row in rows]),
        owner=rows[0].office_name if rows else None,
    )
