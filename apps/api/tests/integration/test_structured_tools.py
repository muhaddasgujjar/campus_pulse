"""Structured tools against a real Postgres with FAKE data only (Memory rule 1 and rule 9)."""

import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Department, Faculty, Fee, Institution, KeyDate, Office, Timetable
from app.tools import STRUCTURED_TOOLS, ToolContext, run_tool

pytestmark = pytest.mark.integration

TODAY = date(2026, 10, 5)
VERIFIED = date(2026, 9, 1)


async def _institution(session: AsyncSession, slug: str) -> uuid.UUID:
    inst = Institution(slug=slug, name=f"{slug} University", config={})
    session.add(inst)
    await session.flush()
    return inst.id


@pytest.fixture
async def ctx(db_session: AsyncSession) -> ToolContext:
    inst = await _institution(db_session, "test-uni")
    other = await _institution(db_session, "other-uni")
    dept = Department(institution_id=inst, name="Department of Testing", faculty="Test Sciences")
    db_session.add(dept)
    await db_session.flush()
    teacher = Faculty(
        institution_id=inst,
        name="Dr. Test Faculty",
        designation="Assistant Professor",
        department_id=dept.id,
        email="test.faculty@example.test",
        office_room="T-000",
        courses=["TEST-101 Introduction to Testing"],
        last_verified=VERIFIED,
        source_name="Test faculty list",
    )
    db_session.add_all(
        [
            teacher,
            Faculty(institution_id=other, name="Dr. Test Faculty Other", last_verified=VERIFIED),
            Faculty(institution_id=inst, name="Dr. Inactive Test", status="inactive"),
            Fee(
                institution_id=inst,
                program_group="Faculty of Test Sciences (BSTS, BS QA)",
                level="Undergraduate",
                fiscal_year="2026-27",
                admission_fee=Decimal("1000"),
                tuition_per_credit_hour=Decimal("2000"),
                misc_per_semester=Decimal("300"),
                last_verified=VERIFIED,
                source_name="Test fee page",
            ),
            Fee(
                institution_id=inst,
                program_group="Faculty of Test Sciences (BSTS, BS QA)",
                level="Undergraduate",
                fiscal_year="2025-26",
                tuition_per_credit_hour=Decimal("1900"),
                last_verified=date(2025, 9, 1),
                source_name="Test fee page",
            ),
            Office(
                institution_id=inst,
                name="Test Exam Office",
                phones=["000-0000000"],
                hours="Mon-Fri 09:00-17:00",
                topics=["exam", "datesheet"],
                last_verified=VERIFIED,
                source_name="Test contacts page",
            ),
            Office(institution_id=inst, name="Test Admission Office", topics=["admission"]),
            KeyDate(
                institution_id=inst,
                title="Test application deadline",
                date=date(2026, 10, 2),
                kind="admission",
                office_name="Test Admission Office",
                last_verified=VERIFIED,
            ),
            KeyDate(
                institution_id=inst,
                title="Test fee deadline",
                date=date(2026, 10, 20),
                kind="fee",
                program_scope="BSTS",
                last_verified=VERIFIED,
            ),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Timetable(
                institution_id=inst,
                program="BSTS",
                semester=3,
                section="A",
                day=2,
                start_time=time(8, 30),
                end_time=time(10, 0),
                course_code="TEST-101",
                course_name="Introduction to Testing",
                faculty_id=teacher.id,
                faculty_name="Dr. Test Faculty",
                room="T-101",
                last_verified=VERIFIED,
            ),
            Timetable(
                institution_id=inst,
                program="BSTS",
                semester=3,
                section="A",
                day=4,
                start_time=time(11, 0),
                end_time=time(12, 30),
                course_name="Advanced Testing",
                last_verified=VERIFIED,
            ),
            Timetable(  # expired row must not be returned
                institution_id=inst,
                program="BSTS",
                semester=3,
                section="A",
                day=2,
                start_time=time(14, 0),
                end_time=time(15, 0),
                course_name="Old Course",
                effective_to=date(2026, 6, 30),
            ),
        ]
    )
    await db_session.flush()
    return ToolContext(session=db_session, institution_id=inst, today=TODAY)


# --- get_fee -------------------------------------------------------------------------------


async def test_get_fee_matches_program_inside_group_newest_year_first(ctx: ToolContext) -> None:
    result = await run_tool(ctx, "get_fee", {"program_group": "bs ts"})
    assert [row["fiscal_year"] for row in result.data] == ["2026-27", "2025-26"]
    latest = result.data[0]
    assert latest["tuition_per_credit_hour"] == 2000.0
    assert latest["admission_fee"] == 1000.0
    assert latest["currency"] == "Rs"
    assert result.sources[0].title == "Test fee page (FY 2026-27)"


async def test_get_fee_unknown_program_returns_nothing(ctx: ToolContext) -> None:
    result = await run_tool(ctx, "get_fee", {"program_group": "MBBS"})
    assert not result.found
    assert result.sources == []


async def test_get_fee_like_wildcards_are_literal(ctx: ToolContext) -> None:
    result = await run_tool(ctx, "get_fee", {"program_group": "%%"})
    assert not result.found


# --- get_office ----------------------------------------------------------------------------


async def test_get_office_by_topic_inside_question(ctx: ToolContext) -> None:
    result = await run_tool(ctx, "get_office", {"name_or_topic": "when is my exam datesheet"})
    assert [row["name"] for row in result.data] == ["Test Exam Office"]
    assert result.data[0]["phones"] == ["000-0000000"]
    assert result.owner == "Test Exam Office"


async def test_get_office_name_match_ranks_first(ctx: ToolContext) -> None:
    result = await run_tool(ctx, "get_office", {"name_or_topic": "admission office"})
    assert result.data[0]["name"] == "Test Admission Office"


# --- get_key_dates -------------------------------------------------------------------------


async def test_key_dates_flag_passed_dates_against_today(ctx: ToolContext) -> None:
    result = await run_tool(ctx, "get_key_dates", {})
    by_title = {row["title"]: row for row in result.data}
    assert by_title["Test application deadline"]["passed"] is True
    assert by_title["Test application deadline"]["days_left"] == -3
    assert by_title["Test fee deadline"]["passed"] is False
    assert by_title["Test fee deadline"]["days_left"] == 15


async def test_key_dates_filters(ctx: ToolContext) -> None:
    fee = await run_tool(ctx, "get_key_dates", {"kind": "fee"})
    assert [row["title"] for row in fee.data] == ["Test fee deadline"]
    upcoming = await run_tool(ctx, "get_key_dates", {"from_date": "2026-10-05"})
    assert [row["title"] for row in upcoming.data] == ["Test fee deadline"]
    other_program = await run_tool(ctx, "get_key_dates", {"program_scope": "BBA"})
    assert [row["title"] for row in other_program.data] == ["Test application deadline"]


# --- find_faculty --------------------------------------------------------------------------


async def test_find_faculty_by_name_course_and_department(ctx: ToolContext) -> None:
    for args in ({"name": "test faculty"}, {"course": "TEST-101"}, {"department": "testing"}):
        result = await run_tool(ctx, "find_faculty", args)
        assert [row["name"] for row in result.data] == ["Dr. Test Faculty"], args
    assert result.data[0]["office_room"] == "T-000"


async def test_find_faculty_hides_inactive_and_other_institutions(ctx: ToolContext) -> None:
    result = await run_tool(ctx, "find_faculty", {"name": "Dr."})
    assert [row["name"] for row in result.data] == ["Dr. Test Faculty"]


async def test_find_faculty_needs_an_argument(ctx: ToolContext) -> None:
    with pytest.raises(ValidationError):
        await run_tool(ctx, "find_faculty", {})


# --- get_timetable -------------------------------------------------------------------------


async def test_timetable_for_program_semester_section(ctx: ToolContext) -> None:
    result = await run_tool(
        ctx, "get_timetable", {"program": "bs ts", "semester": 3, "section": "a"}
    )
    assert [(row["day"], row["start_time"], row["course_name"]) for row in result.data] == [
        ("Tuesday", "08:30", "Introduction to Testing"),
        ("Thursday", "11:00", "Advanced Testing"),
    ]


async def test_timetable_day_name_is_accepted(ctx: ToolContext) -> None:
    result = await run_tool(
        ctx, "get_timetable", {"program": "BSTS", "semester": 3, "day": "Tuesday"}
    )
    assert [row["course_name"] for row in result.data] == ["Introduction to Testing"]
    assert result.data[0]["room"] == "T-101"


async def test_timetable_wrong_semester_is_empty(ctx: ToolContext) -> None:
    result = await run_tool(ctx, "get_timetable", {"program": "BSTS", "semester": 5})
    assert not result.found


async def test_timetable_rejects_invalid_semester(ctx: ToolContext) -> None:
    with pytest.raises(ValidationError):
        await run_tool(ctx, "get_timetable", {"program": "BSTS", "semester": 99})


# --- safety --------------------------------------------------------------------------------


async def test_hostile_input_is_treated_as_data(ctx: ToolContext) -> None:
    hostile = "x'; drop table faculty; --"
    result = await run_tool(ctx, "find_faculty", {"name": hostile})
    assert not result.found
    still_there = await ctx.session.execute(text("select count(*) from faculty"))
    assert still_there.scalar_one() == 3


async def test_unknown_tool_is_rejected(ctx: ToolContext) -> None:
    with pytest.raises(KeyError):
        await run_tool(ctx, "run_sql", {"query": "select 1"})


def test_every_tool_publishes_a_json_schema() -> None:
    for spec in STRUCTURED_TOOLS.values():
        schema = spec.json_schema()
        assert schema["type"] == "object"
        assert schema["properties"]
