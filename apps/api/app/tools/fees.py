"""get_fee(program_group, level=None): fee rows with fiscal year (ANS-6: always state the year)."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.db.repositories import structured as repo
from app.tools.base import Source, ToolContext, ToolResult, oldest


class FeeArgs(BaseModel):
    program_group: str = Field(
        min_length=2, max_length=80, description="Program or program group, e.g. BSCS or BBA"
    )
    level: str | None = Field(default=None, max_length=40)


def _num(value: Decimal | float | None) -> float | None:
    return float(value) if value is not None else None


async def get_fee(ctx: ToolContext, args: FeeArgs) -> ToolResult:
    rows = await repo.find_fees(ctx.session, ctx.institution_id, args.program_group, args.level)
    data: list[dict[str, Any]] = [
        {
            "program_group": row.program_group,
            "level": row.level,
            "fiscal_year": row.fiscal_year,
            "currency": "Rs",
            "admission_fee": _num(row.admission_fee),
            "tuition_per_credit_hour": _num(row.tuition_per_credit_hour),
            "misc_per_semester": _num(row.misc_per_semester),
            "credit_hours_sem1": row.credit_hours_sem1,
            "notes": row.notes,
            "last_verified": row.last_verified,
        }
        for row in rows
    ]
    sources = [
        Source(
            title=f"{row.source_name or 'Fee structure'} (FY {row.fiscal_year})",
            last_verified=row.last_verified,
        )
        for row in rows
    ]
    return ToolResult(
        tool="get_fee",
        data=data,
        sources=sources,
        last_verified=oldest([row.last_verified for row in rows]),
        owner=None,
    )
