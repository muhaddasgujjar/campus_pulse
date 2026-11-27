"""Structured tools over the real seed/lgu rows: exact-data answers must match the seed files."""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.seeding import load_seed_dir
from app.tools import ToolContext, run_tool

pytestmark = pytest.mark.integration

SEED_DIR = Path(__file__).resolve().parents[4] / "seed" / "lgu"


@pytest.fixture
async def lgu(db_session: AsyncSession) -> ToolContext:
    report = await load_seed_dir(db_session, SEED_DIR)
    assert report.institution_id is not None
    return ToolContext(
        session=db_session, institution_id=report.institution_id, today=date(2026, 10, 5)
    )


@pytest.mark.parametrize("query", ["BSCS", "bs cs", "BSSE", "computer sciences", "BS CySec"])
async def test_cs_programs_resolve_to_the_cs_fee_row(lgu: ToolContext, query: str) -> None:
    result = await run_tool(lgu, "get_fee", {"program_group": query})
    assert len(result.data) == 1
    row = result.data[0]
    assert (row["tuition_per_credit_hour"], row["admission_fee"], row["misc_per_semester"]) == (
        7744.0,
        17500.0,
        6360.0,
    )
    assert row["fiscal_year"] == "2026-27"


async def test_bba_fee_has_no_admission_fee_listed(lgu: ToolContext) -> None:
    row = (await run_tool(lgu, "get_fee", {"program_group": "BBA"})).data[0]
    assert row["tuition_per_credit_hour"] == 7392.0
    assert row["admission_fee"] is None  # not in the source: never invented


async def test_exam_office_by_topic(lgu: ToolContext) -> None:
    result = await run_tool(lgu, "get_office", {"name_or_topic": "exam"})
    assert result.data[0]["name"] == "Exam Office"
    assert result.data[0]["phones"] == ["042-37181828"]


async def test_admission_deadline_has_passed(lgu: ToolContext) -> None:
    result = await run_tool(lgu, "get_key_dates", {"kind": "admission"})
    assert result.data[0]["date"] == date(2026, 10, 2)
    assert result.data[0]["passed"] is True
    assert result.data[0]["office"] == "Admission Office"
