"""Minimal admin path for M2 (Phases.md): knowledge entries, documents, CSV imports, re-index.

Used by the CLI now and by the admin API in M5 (where RBAC and real user ids are added).
Workflow (DATA-4, DATA-5): draft -> pending (submitted) -> approved (indexed immediately) or
back to draft with a rejection reason; approved -> archived. Editing an entry sends it back to
pending and removes it from search until it is approved again (version history is a Could).
Every write records an audit row in the same transaction (rule 7).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Department, Document, Faculty, Institution, KbEntry, Timetable
from app.db.repositories.upsert import UpsertStats, upsert
from app.services import audit
from app.services.embeddings import Embedder
from app.services.ingestion import IndexResult, index_document, index_entry
from app.services.pdf import extract_pdf_text
from app.services.seeding import FacultyRow, KbEntryRow, SeedRow, TimetableRow, read_csv


class ContentError(ValueError):
    """A request that breaks the workflow rules. The message is safe to show."""


@dataclass(frozen=True)
class Actor:
    label: str  # "cli:<user>" until M5, then the Supabase user
    user_id: uuid.UUID | None = None


async def institution_id_for(session: AsyncSession, slug: str) -> uuid.UUID:
    inst = (
        await session.execute(select(Institution.id).where(Institution.slug == slug))
    ).scalar_one_or_none()
    if inst is None:
        raise ContentError(f"Unknown institution '{slug}'. Run `make seed` first.")
    return inst


def _audit(
    session: AsyncSession,
    actor: Actor,
    institution_id: uuid.UUID,
    action: str,
    table: str,
    row_id: uuid.UUID,
    diff: dict[str, Any],
) -> None:
    audit.record(
        session,
        institution_id=institution_id,
        action=action,
        table_name=table,
        row_id=row_id,
        diff=diff,
        actor_label=actor.label,
        actor_id=actor.user_id,
    )


# --- knowledge entries -------------------------------------------------------------------


async def create_entry(
    session: AsyncSession,
    institution_id: uuid.UUID,
    data: KbEntryRow,
    actor: Actor,
    *,
    submit: bool = False,
) -> KbEntry:
    values = data.model_dump()
    values["status"] = "pending" if submit else "draft"
    entry = KbEntry(institution_id=institution_id, owner_id=actor.user_id, **values)
    session.add(entry)
    await session.flush()
    _audit(session, actor, institution_id, "create", "kb_entries", entry.id, {"new": values})
    return entry


async def _get_entry(session: AsyncSession, entry_id: uuid.UUID) -> KbEntry:
    entry = await session.get(KbEntry, entry_id)
    if entry is None:
        raise ContentError(f"Knowledge entry {entry_id} not found.")
    return entry


async def _set_status(
    session: AsyncSession, entry: KbEntry, status: str, actor: Actor, **extra: Any
) -> None:
    diff = {"status": {"old": entry.status, "new": status}}
    entry.status = status
    for name, value in extra.items():
        diff[name] = {"old": getattr(entry, name), "new": value}
        setattr(entry, name, value)
    await session.flush()
    action = {"approved": "approve", "archived": "archive"}.get(status, "update")
    if extra.get("rejected_reason"):
        action = "reject"
    _audit(session, actor, entry.institution_id, action, "kb_entries", entry.id, diff)


async def submit_entry(session: AsyncSession, entry_id: uuid.UUID, actor: Actor) -> KbEntry:
    entry = await _get_entry(session, entry_id)
    if entry.status != "draft":
        raise ContentError(f"Only drafts can be submitted (status is {entry.status}).")
    await _set_status(session, entry, "pending", actor, rejected_reason=None)
    return entry


async def approve_entry(
    session: AsyncSession, entry_id: uuid.UUID, actor: Actor, embedder: Embedder | None
) -> tuple[KbEntry, IndexResult]:
    entry = await _get_entry(session, entry_id)
    if entry.status != "pending":
        raise ContentError(f"Only pending entries can be approved (status is {entry.status}).")
    if entry.last_verified is None:
        raise ContentError("Set last_verified before approving (D6: every fact is dated).")
    await _set_status(session, entry, "approved", actor, approved_by=actor.user_id)
    return entry, await index_entry(session, entry, embedder)


async def reject_entry(
    session: AsyncSession, entry_id: uuid.UUID, actor: Actor, reason: str
) -> KbEntry:
    entry = await _get_entry(session, entry_id)
    if entry.status != "pending":
        raise ContentError(f"Only pending entries can be rejected (status is {entry.status}).")
    if not reason.strip():
        raise ContentError("A rejection needs a reason.")
    await _set_status(session, entry, "draft", actor, rejected_reason=reason.strip())
    return entry


async def update_entry(
    session: AsyncSession, entry_id: uuid.UUID, changes: dict[str, Any], actor: Actor
) -> KbEntry:
    """Edit fields; the entry goes back to pending and leaves search until re-approved."""
    allowed = {"title", "question", "answer", "category", "owner_name", "language",
               "last_verified", "expires_at", "source_url"}  # fmt: skip
    unknown = set(changes) - allowed
    if unknown:
        raise ContentError(f"Cannot edit: {', '.join(sorted(unknown))}")
    entry = await _get_entry(session, entry_id)
    if entry.status == "archived":
        raise ContentError("Archived entries cannot be edited.")
    diff = {k: {"old": getattr(entry, k), "new": v} for k, v in changes.items()}
    for name, value in changes.items():
        setattr(entry, name, value)
    if entry.status == "approved":
        diff["status"] = {"old": "approved", "new": "pending"}
        entry.status = "pending"
    entry.version += 1
    await session.flush()
    _audit(session, actor, entry.institution_id, "update", "kb_entries", entry.id, diff)
    await index_entry(session, entry, None)  # removes chunks while not approved
    return entry


async def archive_entry(session: AsyncSession, entry_id: uuid.UUID, actor: Actor) -> KbEntry:
    entry = await _get_entry(session, entry_id)
    await _set_status(session, entry, "archived", actor)
    await index_entry(session, entry, None)
    return entry


# --- documents ---------------------------------------------------------------------------


async def upload_document(
    session: AsyncSession,
    institution_id: uuid.UUID,
    pdf_bytes: bytes,
    *,
    title: str,
    category: str,
    owner_name: str | None,
    last_verified: date,
    expires_at: date | None,
    max_mb: int,
    actor: Actor,
) -> Document:
    extracted = extract_pdf_text(pdf_bytes, max_mb)  # raises PdfRejectedError
    document = Document(
        institution_id=institution_id,
        title=title,
        category=category,
        owner_name=owner_name,
        content=extracted.text,
        status="pending",
        uploaded_by=actor.user_id,
        last_verified=last_verified,
        expires_at=expires_at,
    )
    session.add(document)
    await session.flush()
    _audit(
        session,
        actor,
        institution_id,
        "create",
        "documents",
        document.id,
        {
            "new": {
                "title": title,
                "category": category,
                "pages": extracted.pages,
                "characters": len(extracted.text),
            }
        },
    )
    return document


async def approve_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    actor: Actor,
    embedder: Embedder | None,
    verified_on: date | None = None,
) -> tuple[Document, IndexResult]:
    """Approve and index. Approval is the staff check, so a document without a verification
    date (an imported web page) gets `verified_on` as its last_verified date."""
    document = await session.get(Document, document_id)
    if document is None:
        raise ContentError(f"Document {document_id} not found.")
    if document.status != "pending":
        raise ContentError(f"Only pending documents can be approved (status is {document.status}).")
    diff: dict[str, Any] = {"status": {"old": "pending", "new": "approved"}}
    if document.last_verified is None and verified_on is not None:
        document.last_verified = verified_on
        diff["last_verified"] = {"old": None, "new": verified_on.isoformat()}
    document.status = "approved"
    document.approved_by = actor.user_id
    await session.flush()
    _audit(session, actor, document.institution_id, "approve", "documents", document.id, diff)
    return document, await index_document(session, document, embedder)


# --- one-time website import (pending documents, D1 note and D6) -------------------------


@dataclass
class WebImportReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    archived_skipped: int = 0


class WebPage(BaseModel):
    """One page of a snapshot written by app.devtools.web_import."""

    url: str = Field(min_length=8, max_length=500)
    title: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1)
    page_modified: str | None = None
    sha256: str


async def import_web_pages(
    session: AsyncSession,
    institution_id: uuid.UUID,
    pages: list[WebPage],
    actor: Actor,
    *,
    owner_name: str,
) -> WebImportReport:
    """Load pages as pending documents, keyed by URL. Nothing is indexed here: a staff member
    approves each page (approve_document), which chunks and embeds it. A page whose text
    changed goes back to pending and out of search until it is approved again."""
    report = WebImportReport()
    for page in pages:
        existing = (
            await session.execute(
                select(Document).where(
                    Document.institution_id == institution_id, Document.source_url == page.url
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            document = Document(
                institution_id=institution_id,
                title=page.title,
                category=page.category,
                owner_name=owner_name,
                mime="text/html",
                content=page.content,
                status="pending",
                uploaded_by=actor.user_id,
                source_url=page.url,
            )
            session.add(document)
            await session.flush()
            _audit(session, actor, institution_id, "create", "documents", document.id,
                   {"new": {"title": page.title, "url": page.url, "sha256": page.sha256,
                            "characters": len(page.content)}})  # fmt: skip
            report.created += 1
            continue
        if existing.content == page.content:
            report.unchanged += 1
            continue
        if existing.status == "archived":  # staff removed it on purpose
            report.archived_skipped += 1
            continue
        old_status = existing.status
        existing.content, existing.title, existing.status = page.content, page.title, "pending"
        existing.last_verified = None  # the new text has not been checked
        await session.flush()
        await index_document(session, existing, None)  # not approved: removes its chunks
        _audit(session, actor, institution_id, "update", "documents", existing.id,
               {"status": {"old": old_status, "new": "pending"}, "sha256": page.sha256,
                "reason": "page text changed on the website"})  # fmt: skip
        report.updated += 1
    return report


# --- CSV imports (DATA-2) ----------------------------------------------------------------


@dataclass
class ImportPreview:
    rows: list[SeedRow]
    errors: list[str]


def preview_csv(kind: str, path: Path) -> ImportPreview:
    """Validate every row and report all errors (not just the first) before importing."""
    models: dict[str, type[SeedRow]] = {"timetable": TimetableRow, "faculty": FacultyRow}
    model = models[kind]
    rows: list[SeedRow] = []
    errors: list[str] = []
    for number, raw in enumerate(read_csv(path), start=2):  # line 1 is the header
        try:
            rows.append(model.model_validate(raw))
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or 'row'}: {err['msg']}"
                for err in exc.errors()
            )
            errors.append(f"row {number}: {details}")
    if not rows and not errors:
        errors.append("the file has no data rows")
    return ImportPreview(rows=rows, errors=errors)


async def import_rows(
    session: AsyncSession, institution_id: uuid.UUID, kind: str, rows: list[SeedRow], actor: Actor
) -> UpsertStats:
    stats = UpsertStats()
    for row in rows:
        if isinstance(row, TimetableRow):
            key_fields = ("program", "semester", "section", "day", "start_time", "course_name")
            key = {f: getattr(row, f) for f in key_fields}
            values = row.model_dump(exclude=set(key_fields))
            model: type[Any] = Timetable
        elif isinstance(row, FacultyRow):
            key = {"name": row.name}
            values = row.model_dump(exclude={"name", "department"})
            values["department_id"] = (
                await _department_id(session, institution_id, row.department)
                if row.department
                else None
            )
            model = Faculty
        else:  # pragma: no cover - guarded by preview_csv
            raise ContentError(f"Unsupported import kind {kind}")
        obj, outcome = await upsert(
            session,
            model,
            key={"institution_id": institution_id, **key},
            values=values,
            institution_id=institution_id,
            actor_label=actor.label,
        )
        stats.add(outcome, obj.id)
    return stats


async def _department_id(session: AsyncSession, institution_id: uuid.UUID, name: str) -> uuid.UUID:
    dept = (
        await session.execute(
            select(Department.id).where(
                Department.institution_id == institution_id, Department.name == name
            )
        )
    ).scalar_one_or_none()
    if dept is None:
        raise ContentError(f"Unknown department '{name}'. Add it to departments.csv first.")
    return dept


# --- re-index ----------------------------------------------------------------------------


async def reindex_all(
    session: AsyncSession, institution_id: uuid.UUID, embedder: Embedder | None
) -> tuple[int, int]:
    """Re-chunk and re-embed every approved entry and document (after a model change)."""
    chunks = embedded = 0
    entries = (
        await session.execute(
            select(KbEntry).where(
                KbEntry.institution_id == institution_id, KbEntry.status == "approved"
            )
        )
    ).scalars()
    documents = (
        await session.execute(
            select(Document).where(
                Document.institution_id == institution_id, Document.status == "approved"
            )
        )
    ).scalars()
    for entry in list(entries):
        result = await index_entry(session, entry, embedder)
        chunks += result.chunks
        embedded += result.chunks if result.embedded else 0
    for document in list(documents):
        result = await index_document(session, document, embedder)
        chunks += result.chunks
        embedded += result.chunks if result.embedded else 0
    return chunks, embedded
