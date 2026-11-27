"""Seed loader: exact facts from seed/lgu, idempotent, audited, validated (M2, rule 1, rule 7)."""

import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Fee, Institution, KbEntry, KeyDate, Office
from app.services.seeding import load_seed_dir

pytestmark = pytest.mark.integration

SEED_DIR = Path(__file__).resolve().parents[4] / "seed" / "lgu"


async def count(session: AsyncSession, model: type) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_loads_listed_facts_exactly(db_session: AsyncSession) -> None:
    report = await load_seed_dir(db_session, SEED_DIR)

    assert report.tables["offices"].created == 2
    assert report.tables["fees"].created == 2
    assert report.tables["key_dates"].created == 1
    assert report.tables["kb_entries"].created == 7
    assert report.tables["departments"].created == 4
    assert report.tables["faculty"].created == 0  # no verified faculty data yet
    assert report.tables["timetable"].created == 0  # no verified timetable yet

    cs = (
        await db_session.execute(select(Fee).where(Fee.program_group.ilike("%BSCS%")))
    ).scalar_one()
    assert cs.fiscal_year == "2026-27"
    assert cs.tuition_per_credit_hour == Decimal("7744")
    assert cs.admission_fee == Decimal("17500")
    assert cs.misc_per_semester == Decimal("6360")

    exam = (
        await db_session.execute(select(Office).where(Office.name == "Exam Office"))
    ).scalar_one()
    assert exam.phones == ["042-37181828"]

    deadline = (await db_session.execute(select(KeyDate))).scalar_one()
    assert deadline.date.isoformat() == "2026-10-02"

    lgu = (await db_session.execute(select(Institution))).scalar_one()
    assert lgu.slug == "lgu"
    assert lgu.config["fallback_office"] == "Admission Office"


async def test_second_load_changes_nothing(db_session: AsyncSession) -> None:
    await load_seed_dir(db_session, SEED_DIR)
    audits_after_first = await count(db_session, AuditLog)

    report = await load_seed_dir(db_session, SEED_DIR)

    assert all(stats.created == 0 and stats.updated == 0 for stats in report.tables.values())
    assert await count(db_session, KbEntry) == 7
    assert await count(db_session, AuditLog) == audits_after_first


async def test_every_created_row_is_audited(db_session: AsyncSession) -> None:
    report = await load_seed_dir(db_session, SEED_DIR)
    created = sum(stats.created for stats in report.tables.values())
    audits = (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "create")
        )
    ).scalar_one()
    assert audits == created
    labels = (await db_session.execute(select(AuditLog.actor_label).distinct())).scalars().all()
    assert labels == ["seed"]


async def test_changed_value_is_updated_and_audited(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    seed = tmp_path / "lgu"
    shutil.copytree(SEED_DIR, seed)
    await load_seed_dir(db_session, seed)

    fees = (seed / "fees.csv").read_text(encoding="utf-8").replace(",7392,", ",7400,")
    (seed / "fees.csv").write_text(fees, encoding="utf-8")
    report = await load_seed_dir(db_session, seed)

    assert report.tables["fees"].updated == 1
    update = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "update", AuditLog.table_name == "fees")
        )
    ).scalar_one()
    assert update.diff["tuition_per_credit_hour"] == {"old": 7392.0, "new": 7400.0}


async def test_invalid_row_is_rejected_before_any_write(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    seed = tmp_path / "lgu"
    shutil.copytree(SEED_DIR, seed)
    with (seed / "key_dates.csv").open("a", encoding="utf-8") as handle:
        handle.write("Fake deadline,not-a-date,admission,,,2026-10-05,Test\n")

    with pytest.raises(ValueError, match=r"key_dates.csv row 3"):
        await load_seed_dir(db_session, seed)
    assert await count(db_session, Institution) == 0
