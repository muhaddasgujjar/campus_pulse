"""get_office(name_or_topic): office contacts by name or topic (also used by the fallback)."""

from pydantic import BaseModel, Field

from app.db.repositories import structured as repo
from app.tools.base import Source, ToolContext, ToolResult, oldest


class OfficeArgs(BaseModel):
    name_or_topic: str = Field(
        min_length=2, max_length=120, description="Office name or topic, e.g. 'exam'"
    )


async def get_office(ctx: ToolContext, args: OfficeArgs) -> ToolResult:
    rows = await repo.find_offices(ctx.session, ctx.institution_id, args.name_or_topic)
    data = [
        {
            "name": row.name,
            "phones": list(row.phones),
            "email": row.email,
            "hours": row.hours,
            "location": row.location,
            "last_verified": row.last_verified,
        }
        for row in rows
    ]
    sources = [
        Source(
            title=row.source_name or f"{row.name} contact details",
            office=row.name,
            last_verified=row.last_verified,
        )
        for row in rows
    ]
    return ToolResult(
        tool="get_office",
        data=data,
        sources=sources,
        last_verified=oldest([row.last_verified for row in rows]),
        owner=rows[0].name if rows else None,
    )
