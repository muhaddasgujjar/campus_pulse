"""Minimal admin path: approval workflow, re-embed on approval, audit, imports, PDF upload."""

import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Chunk, Department, Document, Faculty, Institution
from app.services import content_admin as admin
from app.services.embeddings import FakeEmbedder
from app.services.pdf import PdfRejectedError
from app.services.retrieval import search
from app.services.seeding import KbEntryRow
from tests.support.pdf import make_pdf

pytestmark = pytest.mark.integration

ACTOR = admin.Actor(label="cli:test-admin")


@pytest.fixture
async def inst(db_session: AsyncSession) -> uuid.UUID:
    institution = Institution(slug="test-uni", name="Test University", config={})
    db_session.add(institution)
    await db_session.flush()
    db_session.add(Department(institution_id=institution.id, name="Department of Testing"))
    await db_session.flush()
    return institution.id


def _row(**overrides: object) -> KbEntryRow:
    data: dict[str, object] = {
        "title": "Test transport",
        "question": "Is there a test bus?",
        "answer": "The test bus leaves the test campus at 17:00.",
        "category": "transport",
        "owner_name": "Test Transport Office",
        "last_verified": date(2026, 10, 1),
    }
    data.update(overrides)
    return KbEntryRow.model_validate(data)


async def _actions(session: AsyncSession, row_id: uuid.UUID) -> list[str]:
    rows = await session.execute(
        select(AuditLog.action).where(AuditLog.row_id == row_id).order_by(AuditLog.created_at)
    )
    return list(rows.scalars())


async def test_entry_is_searchable_only_after_approval(
    db_session: AsyncSession, inst: uuid.UUID
) -> None:
    embedder = FakeEmbedder()
    entry = await admin.create_entry(db_session, inst, _row(), ACTOR)
    assert entry.status == "draft"
    assert (await search(db_session, embedder, inst, "test bus", k=3)).chunks == []

    await admin.submit_entry(db_session, entry.id, ACTOR)
    _, indexed = await admin.approve_entry(db_session, entry.id, ACTOR, embedder)
    assert indexed.chunks == 1 and indexed.embedded

    found = await search(db_session, embedder, inst, "When does the test bus leave?", k=3)
    assert found.chunks[0].title == "Test transport"
    assert await _actions(db_session, entry.id) == ["create", "update", "approve"]


async def test_reject_needs_reason_and_returns_to_draft(
    db_session: AsyncSession, inst: uuid.UUID
) -> None:
    entry = await admin.create_entry(db_session, inst, _row(), ACTOR, submit=True)
    with pytest.raises(admin.ContentError, match="reason"):
        await admin.reject_entry(db_session, entry.id, ACTOR, " ")
    await admin.reject_entry(db_session, entry.id, ACTOR, "Wrong time, check with the office")
    assert entry.status == "draft"
    assert entry.rejected_reason == "Wrong time, check with the office"
    assert "reject" in await _actions(db_session, entry.id)


async def test_cannot_approve_a_draft_or_twice(db_session: AsyncSession, inst: uuid.UUID) -> None:
    entry = await admin.create_entry(db_session, inst, _row(), ACTOR)
    with pytest.raises(admin.ContentError, match="Only pending"):
        await admin.approve_entry(db_session, entry.id, ACTOR, None)


async def test_editing_an_approved_entry_removes_it_until_reapproved(
    db_session: AsyncSession, inst: uuid.UUID
) -> None:
    embedder = FakeEmbedder()
    entry = await admin.create_entry(db_session, inst, _row(), ACTOR, submit=True)
    await admin.approve_entry(db_session, entry.id, ACTOR, embedder)

    await admin.update_entry(
        db_session, entry.id, {"answer": "The test bus leaves at 18:00."}, ACTOR
    )
    assert entry.status == "pending" and entry.version == 2
    assert (await search(db_session, embedder, inst, "test bus", k=3)).chunks == []

    await admin.approve_entry(db_session, entry.id, ACTOR, embedder)
    chunk = (await db_session.execute(select(Chunk).where(Chunk.entry_id == entry.id))).scalar_one()
    assert "18:00" in chunk.content


async def test_pdf_upload_approve_and_search(db_session: AsyncSession, inst: uuid.UUID) -> None:
    embedder = FakeEmbedder()
    pdf = make_pdf(
        [
            "Test Parking Policy (fake document for tests).",
            "Students park their cars in the north test lot after 08:00.",
        ]
    )
    document = await admin.upload_document(
        db_session,
        inst,
        pdf,
        title="Test Parking Policy",
        category="policies",
        owner_name="Test Estate Office",
        last_verified=date(2026, 9, 30),
        expires_at=None,
        max_mb=10,
        actor=ACTOR,
    )
    assert document.status == "pending"
    assert (await search(db_session, embedder, inst, "where can students park", k=3)).chunks == []

    _, indexed = await admin.approve_document(db_session, document.id, ACTOR, embedder)
    assert indexed.chunks >= 1
    found = await search(db_session, embedder, inst, "where can students park", k=3)
    assert found.chunks[0].title == "Test Parking Policy"
    assert found.chunks[0].owner_name == "Test Estate Office"


async def test_scanned_pdf_is_rejected(db_session: AsyncSession, inst: uuid.UUID) -> None:
    with pytest.raises(PdfRejectedError, match="OCR is not supported"):
        await admin.upload_document(
            db_session,
            inst,
            make_pdf(),
            title="Scan",
            category="policies",
            owner_name=None,
            last_verified=date(2026, 9, 30),
            expires_at=None,
            max_mb=10,
            actor=ACTOR,
        )


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_csv_preview_reports_every_bad_row(tmp_path: Path) -> None:
    header = (
        "program,semester,section,day,start_time,end_time,course_code,course_name,"
        "faculty_name,room,effective_from,effective_to,last_verified,source_name\n"
    )
    csv_path = _write(
        tmp_path / "timetable.csv",
        header
        + "BSTS,3,A,Tuesday,08:30,10:00,TEST-101,Intro to Testing,Dr. Test,T-1,,,2026-09-01,Test\n"
        + "BSTS,30,A,Tuesday,08:30,10:00,TEST-102,Bad Semester,,T-1,,,2026-09-01,Test\n"
        + "BSTS,3,A,Funday,08:30,10:00,TEST-103,Bad Day,,T-1,,,2026-09-01,Test\n",
    )
    preview = admin.preview_csv("timetable", csv_path)
    assert len(preview.rows) == 1
    assert [e.split(":")[0] for e in preview.errors] == ["row 3", "row 4"]
    assert "semester" in preview.errors[0]
    assert "day" in preview.errors[1]


async def test_faculty_import_resolves_department_and_audits(
    db_session: AsyncSession, inst: uuid.UUID, tmp_path: Path
) -> None:
    csv_path = _write(
        tmp_path / "faculty.csv",
        "name,designation,department,email,office_room,courses,status,last_verified,source_name\n"
        "Dr. Test Faculty,Lecturer,Department of Testing,t@example.test,T-0,TEST-101|TEST-102,"
        "active,2026-09-01,Test list\n",
    )
    preview = admin.preview_csv("faculty", csv_path)
    assert preview.errors == []
    stats = await admin.import_rows(db_session, inst, "faculty", preview.rows, ACTOR)
    assert stats.created == 1
    member = (await db_session.execute(select(Faculty))).scalar_one()
    assert member.courses == ["TEST-101", "TEST-102"]
    assert member.department_id is not None
    assert await _actions(db_session, member.id) == ["create"]


# --- one-time website import: pending until approved (D6) ----------------------------------


def _page(content: str = "Test bus pass costs 500 per semester.", **extra: str) -> admin.WebPage:
    values = {
        "url": "https://test.edu/transport/",
        "title": "Test transport page",
        "category": "transport",
        "content": content,
        "sha256": "x" * 64,
    }
    values.update(extra)
    return admin.WebPage.model_validate(values)


async def test_web_pages_are_pending_and_not_searchable_until_approved(
    db_session: AsyncSession, inst: uuid.UUID
) -> None:
    embedder = FakeEmbedder()
    report = await admin.import_web_pages(
        db_session, inst, [_page()], ACTOR, owner_name="Test website"
    )
    assert report.created == 1
    document = (await db_session.execute(select(Document))).scalars().one()
    assert (document.status, document.mime, document.last_verified) == (
        "pending",
        "text/html",
        None,
    )
    assert (await search(db_session, embedder, inst, "test bus pass", k=3)).chunks == []

    _, indexed = await admin.approve_document(
        db_session, document.id, ACTOR, embedder, verified_on=date(2026, 10, 6)
    )
    assert indexed.chunks == 1 and document.last_verified == date(2026, 10, 6)
    found = await search(db_session, embedder, inst, "How much is the test bus pass?", k=3)
    assert found.chunks[0].source_url == "https://test.edu/transport/"
    assert await _actions(db_session, document.id) == ["create", "approve"]


async def test_reimport_skips_unchanged_and_sends_changed_pages_back_to_pending(
    db_session: AsyncSession, inst: uuid.UUID
) -> None:
    embedder = FakeEmbedder()
    await admin.import_web_pages(db_session, inst, [_page()], ACTOR, owner_name="Test website")
    document = (await db_session.execute(select(Document))).scalars().one()
    await admin.approve_document(db_session, document.id, ACTOR, embedder, date(2026, 10, 6))

    same = await admin.import_web_pages(db_session, inst, [_page()], ACTOR, owner_name="T")
    assert (same.unchanged, document.status) == (1, "approved")

    changed = await admin.import_web_pages(
        db_session, inst, [_page("Test bus pass now costs 900.")], ACTOR, owner_name="T"
    )
    assert changed.updated == 1
    assert (document.status, document.last_verified) == ("pending", None)
    chunks = await db_session.execute(select(Chunk).where(Chunk.document_id == document.id))
    assert chunks.scalars().all() == []  # out of search until approved again
    assert await _actions(db_session, document.id) == ["create", "approve", "update"]


async def test_reimport_leaves_archived_pages_alone(
    db_session: AsyncSession, inst: uuid.UUID
) -> None:
    await admin.import_web_pages(db_session, inst, [_page()], ACTOR, owner_name="T")
    document = (await db_session.execute(select(Document))).scalars().one()
    document.status = "archived"
    report = await admin.import_web_pages(
        db_session, inst, [_page("new text")], ACTOR, owner_name="T"
    )
    assert report.archived_skipped == 1 and document.content != "new text"
