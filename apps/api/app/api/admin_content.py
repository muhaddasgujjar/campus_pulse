"""Admin portal: knowledge entries, documents, approvals, needs-review, unanswered questions
(DATA-1, DATA-3 to DATA-7, AUTH-3, rule 5).

Staff create and edit content of their own department or office and submit it; only an admin
approves or rejects. Approval chunks and embeds at once, so the chat answers from the new text
within seconds (DATA-5). Every write records an audit row in the same transaction (rule 7).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select

from app.api.deps import AdminApprover, Session, StaffUser, chat_services, read_capped
from app.core.auth import AuthenticatedUser
from app.core.rbac import can_edit_row
from app.db.models import Document, KbEntry
from app.services import audit, monitoring
from app.services import content_admin as content
from app.services.chat import ChatServices
from app.services.chunking import chunk_text
from app.services.content_admin import Actor, ContentError
from app.services.seeding import KbEntryRow
from app.services.uploads import ACCEPTED, UploadRejectedError, extract_upload

router = APIRouter(prefix="/api/admin", tags=["admin"])
Services = Annotated[ChatServices, Depends(chat_services)]

Status = Literal["draft", "pending", "approved", "archived"]


def actor(user: AuthenticatedUser) -> Actor:
    return Actor(label=user.label, user_id=user.user_id)


def bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def ensure_scope(
    user: AuthenticatedUser, department_id: uuid.UUID | None, office_id: uuid.UUID | None
) -> None:
    if not can_edit_row(user, department_id=department_id, office_id=office_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "you can only edit content of your department or office"
        )


def default_scope(
    user: AuthenticatedUser, department_id: uuid.UUID | None, office_id: uuid.UUID | None
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Staff who leave both empty get their own department and office."""
    if department_id is None and office_id is None and user.role == "staff":
        return user.department_id, user.office_id
    return department_id, office_id


def in_institution(user: AuthenticatedUser, row: KbEntry | Document) -> None:
    if row.institution_id != user.institution_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")


# --- knowledge entries -------------------------------------------------------------------


class EntryIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    question: str | None = Field(default=None, max_length=500)
    answer: str = Field(min_length=10, max_length=8000)
    category: str = Field(min_length=2, max_length=40)
    language: Literal["en", "ur"] = "en"
    owner_name: str | None = Field(default=None, max_length=200)
    department_id: uuid.UUID | None = None
    office_id: uuid.UUID | None = None
    last_verified: date
    expires_at: date  # DESIGN 6.2.4: expiry is required for new and edited entries
    source_url: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _dates(self) -> "EntryIn":
        if self.expires_at <= self.last_verified:
            raise ValueError("expires_at must be after last_verified")
        return self


class EntryCreate(EntryIn):
    submit: bool = False  # Submit for approval (else Save draft)
    from_unanswered_id: uuid.UUID | None = None  # DATA-7 "Create entry from this question"


class EntryOut(BaseModel):
    id: uuid.UUID
    title: str
    question: str | None
    answer: str
    category: str
    language: str
    owner_name: str | None
    department_id: uuid.UUID | None
    office_id: uuid.UUID | None
    status: Status
    last_verified: date | None
    expires_at: date | None
    source_url: str | None
    version: int
    rejected_reason: str | None
    updated_at: datetime
    can_edit: bool

    @classmethod
    def of(cls, entry: KbEntry, user: AuthenticatedUser) -> "EntryOut":
        return cls(
            id=entry.id,
            title=entry.title,
            question=entry.question,
            answer=entry.answer,
            category=entry.category,
            language=entry.language,
            owner_name=entry.owner_name,
            department_id=entry.department_id,
            office_id=entry.office_id,
            status=entry.status,  # check constraint
            last_verified=entry.last_verified,
            expires_at=entry.expires_at,
            source_url=entry.source_url,
            version=entry.version,
            rejected_reason=entry.rejected_reason,
            updated_at=entry.updated_at,
            can_edit=can_edit_row(
                user, department_id=entry.department_id, office_id=entry.office_id
            ),
        )


@router.get("/kb", response_model=list[EntryOut])
async def list_entries(
    user: StaffUser,
    session: Session,
    status_: Annotated[Status | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EntryOut]:
    stmt = select(KbEntry).where(KbEntry.institution_id == user.institution_id)
    if status_:
        stmt = stmt.where(KbEntry.status == status_)
    if category:
        stmt = stmt.where(KbEntry.category == category)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(KbEntry.title.ilike(pattern), KbEntry.answer.ilike(pattern)))
    rows = await session.execute(
        stmt.order_by(KbEntry.updated_at.desc()).limit(limit).offset(offset)
    )
    return [EntryOut.of(e, user) for e in rows.scalars()]


@router.get("/kb/{entry_id}", response_model=EntryOut)
async def get_entry(entry_id: uuid.UUID, user: StaffUser, session: Session) -> EntryOut:
    try:
        entry = await content.get_entry(session, entry_id)
    except ContentError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    in_institution(user, entry)
    return EntryOut.of(entry, user)


@router.post("/kb", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
async def create_entry(body: EntryCreate, user: StaffUser, session: Session) -> EntryOut:
    department_id, office_id = default_scope(user, body.department_id, body.office_id)
    ensure_scope(user, department_id, office_id)
    data = KbEntryRow(
        title=body.title,
        question=body.question,
        answer=body.answer,
        category=body.category,
        owner_name=body.owner_name,
        language=body.language,
        last_verified=body.last_verified,
        expires_at=body.expires_at,
        source_url=body.source_url,
    )
    async with session.begin():
        entry = await content.create_entry(
            session, user.institution_id, data, actor(user), submit=body.submit,
            department_id=department_id, office_id=office_id,
        )  # fmt: skip
        if body.from_unanswered_id:
            await _resolve_unanswered(session, user, body.from_unanswered_id, "handled", entry.id)
    return EntryOut.of(entry, user)


@router.put("/kb/{entry_id}", response_model=EntryOut)
async def update_entry(
    entry_id: uuid.UUID, body: EntryIn, user: StaffUser, session: Session
) -> EntryOut:
    """Edit; an approved entry goes back to pending and leaves search until re-approved."""
    async with session.begin():
        entry = await _editable_entry(session, user, entry_id)
        # Like create: staff who leave both empty keep their own office or department.
        department_id, office_id = default_scope(user, body.department_id, body.office_id)
        ensure_scope(user, department_id, office_id)  # cannot move it out of your scope
        changes = {**body.model_dump(), "department_id": department_id, "office_id": office_id}
        try:
            entry = await content.update_entry(session, entry_id, changes, actor(user))
        except ContentError as exc:
            raise bad_request(exc) from exc
    return EntryOut.of(entry, user)


async def _editable_entry(
    session: Session, user: AuthenticatedUser, entry_id: uuid.UUID
) -> KbEntry:
    try:
        entry = await content.get_entry(session, entry_id)
    except ContentError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    in_institution(user, entry)
    ensure_scope(user, entry.department_id, entry.office_id)
    return entry


@router.post("/kb/{entry_id}/submit", response_model=EntryOut)
async def submit_entry(entry_id: uuid.UUID, user: StaffUser, session: Session) -> EntryOut:
    async with session.begin():
        await _editable_entry(session, user, entry_id)
        try:
            entry = await content.submit_entry(session, entry_id, actor(user))
        except ContentError as exc:
            raise bad_request(exc) from exc
    return EntryOut.of(entry, user)


@router.post("/kb/{entry_id}/archive", response_model=EntryOut)
async def archive_entry(entry_id: uuid.UUID, user: StaffUser, session: Session) -> EntryOut:
    async with session.begin():
        await _editable_entry(session, user, entry_id)
        try:
            entry = await content.archive_entry(session, entry_id, actor(user))
        except ContentError as exc:
            raise bad_request(exc) from exc
    return EntryOut.of(entry, user)


# --- documents (DATA-3) --------------------------------------------------------------------


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    owner_name: str | None
    department_id: uuid.UUID | None
    office_id: uuid.UUID | None
    mime: str
    status: Status
    last_verified: date | None
    expires_at: date | None
    source_url: str | None
    characters: int
    updated_at: datetime
    can_edit: bool

    @classmethod
    def of(cls, doc: Document, user: AuthenticatedUser) -> "DocumentOut":
        return cls(
            id=doc.id,
            title=doc.title,
            category=doc.category,
            owner_name=doc.owner_name,
            department_id=doc.department_id,
            office_id=doc.office_id,
            mime=doc.mime,
            status=doc.status,  # check constraint
            last_verified=doc.last_verified,
            expires_at=doc.expires_at,
            source_url=doc.source_url,
            characters=len(doc.content or ""),
            updated_at=doc.updated_at,
            can_edit=can_edit_row(user, department_id=doc.department_id, office_id=doc.office_id),
        )


class PdfPreview(BaseModel):
    pages: int | None  # None for Word files
    characters: int
    chunks: int
    text_preview: str


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    user: StaffUser,
    session: Session,
    status_: Annotated[Status | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentOut]:
    stmt = select(Document).where(Document.institution_id == user.institution_id)
    if status_:
        stmt = stmt.where(Document.status == status_)
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{q.strip()}%"))
    rows = await session.execute(
        stmt.order_by(Document.updated_at.desc()).limit(limit).offset(offset)
    )
    return [DocumentOut.of(d, user) for d in rows.scalars()]


async def _read_upload(request: Request, services: ChatServices) -> tuple[bytes, str]:
    """The raw body and its declared type: a text PDF or a Word (.docx) file (DATA-3)."""
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in ACCEPTED:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a PDF or Word (.docx) file."
        )
    max_mb = services.settings.pdf_max_mb
    body = await read_capped(request, max_mb * 1024 * 1024, f"File larger than {max_mb} MB")
    return body, content_type


@router.post("/documents/preview", response_model=PdfPreview)
async def preview_document(request: Request, user: StaffUser, services: Services) -> PdfPreview:
    """Extract the text and count the chunks without saving anything (DESIGN 6.2.5)."""
    data, content_type = await _read_upload(request, services)
    try:
        extracted = extract_upload(data, content_type, services.settings.pdf_max_mb)
    except UploadRejectedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return PdfPreview(
        pages=extracted.pages,
        characters=len(extracted.text),
        chunks=len(chunk_text(extracted.text)),
        text_preview=extracted.text[:3000],
    )


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    user: StaffUser,
    session: Session,
    services: Services,
    title: Annotated[str, Query(min_length=3, max_length=200)],
    category: Annotated[str, Query(min_length=2, max_length=40)],
    last_verified: date,
    expires_at: date,
    owner_name: Annotated[str | None, Query(max_length=200)] = None,
    department_id: uuid.UUID | None = None,
    office_id: uuid.UUID | None = None,
) -> DocumentOut:
    """The raw PDF or .docx is the body; metadata in the query (no multipart, like voice).
    The document is pending until an admin approves it; only then is it chunked and embedded."""
    if expires_at <= last_verified:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "expiry must be after last verified"
        )
    department_id, office_id = default_scope(user, department_id, office_id)
    ensure_scope(user, department_id, office_id)
    data, content_type = await _read_upload(request, services)
    async with session.begin():
        try:
            doc = await content.upload_document(
                session, user.institution_id, data, title=title.strip(), category=category.strip(),
                owner_name=owner_name, last_verified=last_verified, expires_at=expires_at,
                max_mb=services.settings.pdf_max_mb, actor=actor(user),
                department_id=department_id, office_id=office_id, content_type=content_type,
            )  # fmt: skip
        except UploadRejectedError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return DocumentOut.of(doc, user)


async def _editable_document(
    session: Session, user: AuthenticatedUser, document_id: uuid.UUID
) -> Document:
    try:
        doc = await content.get_document(session, document_id)
    except ContentError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    in_institution(user, doc)
    ensure_scope(user, doc.department_id, doc.office_id)
    return doc


@router.post("/documents/{document_id}/submit", response_model=DocumentOut)
async def submit_document(document_id: uuid.UUID, user: StaffUser, session: Session) -> DocumentOut:
    async with session.begin():
        await _editable_document(session, user, document_id)
        try:
            doc = await content.submit_document(session, document_id, actor(user))
        except ContentError as exc:
            raise bad_request(exc) from exc
    return DocumentOut.of(doc, user)


@router.post("/documents/{document_id}/archive", response_model=DocumentOut)
async def archive_document(
    document_id: uuid.UUID, user: StaffUser, session: Session
) -> DocumentOut:
    async with session.begin():
        await _editable_document(session, user, document_id)
        try:
            doc = await content.archive_document(session, document_id, actor(user))
        except ContentError as exc:
            raise bad_request(exc) from exc
    return DocumentOut.of(doc, user)


# --- approvals (DATA-4, DATA-5) ------------------------------------------------------------


Kind = Literal["kb", "document"]


class ApprovalOut(BaseModel):
    kind: Kind
    id: uuid.UUID
    title: str
    category: str
    submitted_at: datetime
    current: dict[str, Any] | None  # None = new content (never approved)
    proposed: dict[str, Any]


class Decision(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class ApprovalResult(BaseModel):
    kind: Kind
    id: uuid.UUID
    status: Status
    chunks: int = 0
    embedded: bool = False


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(user: StaffUser, session: Session) -> list[ApprovalOut]:
    """The pending queue (staff see it read-only; only admins decide)."""
    out: list[ApprovalOut] = []
    queues: tuple[tuple[Kind, type[KbEntry] | type[Document], str], ...] = (
        ("kb", KbEntry, "kb_entries"),
        ("document", Document, "documents"),
    )
    for kind, model, table in queues:
        rows = await session.execute(
            select(model)
            .where(model.institution_id == user.institution_id, model.status == "pending")
            .order_by(model.updated_at)
        )
        for row in cast(list[KbEntry | Document], list(rows.scalars())):
            current, proposed = await monitoring.approval_diff(session, table, row)
            out.append(ApprovalOut(
                kind=kind, id=row.id, title=row.title, category=row.category,
                submitted_at=row.updated_at, current=current, proposed=proposed,
            ))  # fmt: skip
    return sorted(out, key=lambda a: a.submitted_at)


@router.post("/approvals/{kind}/{row_id}/approve", response_model=ApprovalResult)
async def approve(
    kind: Kind,
    row_id: uuid.UUID,
    user: AdminApprover,
    session: Session,
    services: Services,
    body: Decision | None = None,
) -> ApprovalResult:
    """Approve and index in the same transaction: live in the chat within seconds (DATA-5)."""
    today = services.today()
    async with session.begin():
        try:
            if kind == "kb":
                entry = await content.get_entry(session, row_id)
                in_institution(user, entry)
                entry, result = await content.approve_entry(
                    session, row_id, actor(user), services.embedder
                )
            else:
                doc = await content.get_document(session, row_id)
                in_institution(user, doc)
                doc, result = await content.approve_document(
                    session, row_id, actor(user), services.embedder, verified_on=today
                )
        except ContentError as exc:
            raise bad_request(exc) from exc
    return ApprovalResult(
        kind=kind, id=row_id, status="approved", chunks=result.chunks, embedded=result.embedded
    )


@router.post("/approvals/{kind}/{row_id}/reject", response_model=ApprovalResult)
async def reject(
    kind: Kind, row_id: uuid.UUID, body: Decision, user: AdminApprover, session: Session
) -> ApprovalResult:
    reason = (body.comment or "").strip()
    async with session.begin():
        try:
            if kind == "kb":
                in_institution(user, await content.get_entry(session, row_id))
                await content.reject_entry(session, row_id, actor(user), reason)
            else:
                in_institution(user, await content.get_document(session, row_id))
                await content.reject_document(session, row_id, actor(user), reason)
        except ContentError as exc:
            raise bad_request(exc) from exc
    return ApprovalResult(kind=kind, id=row_id, status="draft")


# --- needs review (DATA-6) -----------------------------------------------------------------


class ReviewOut(BaseModel):
    kind: Kind
    id: uuid.UUID
    title: str
    category: str
    expires_at: date
    expired: bool
    owner_name: str | None
    can_edit: bool


@router.get("/review", response_model=list[ReviewOut])
async def review_queue(
    user: StaffUser,
    session: Session,
    services: Services,
    mine: bool = False,
) -> list[ReviewOut]:
    """Expired or expiring within 14 days. `mine=true`: only what this user may edit (the
    in-app reminder on a staff member's dashboard; no email is sent, D16)."""
    items = await monitoring.needs_review(session, user.institution_id, services.today())
    out = [
        ReviewOut(
            kind=i.kind,
            id=i.id,
            title=i.title,
            category=i.category,
            expires_at=i.expires_at,
            expired=i.expired,
            owner_name=i.owner_name,
            can_edit=can_edit_row(user, department_id=i.department_id, office_id=i.office_id),
        )
        for i in items
    ]
    return [r for r in out if r.can_edit] if mine else out


# --- unanswered questions (DATA-7) ---------------------------------------------------------


class UnansweredOut(BaseModel):
    id: uuid.UUID
    query: str
    count: int
    last_seen: datetime
    reason: str | None


class UnansweredAction(BaseModel):
    status: Literal["handled", "ignored"]


@router.get("/unanswered", response_model=list[UnansweredOut])
async def list_unanswered(
    user: StaffUser,
    session: Session,
    status_: Annotated[Literal["open", "handled", "ignored"], Query(alias="status")] = "open",
) -> list[UnansweredOut]:
    groups = await monitoring.unanswered_groups(session, user.institution_id, status_)
    return [
        UnansweredOut(id=g.id, query=g.query, count=g.count, last_seen=g.last_seen, reason=g.reason)
        for g in groups
    ]


async def _resolve_unanswered(
    session: Session,
    user: AuthenticatedUser,
    row_id: uuid.UUID,
    new_status: str,
    entry_id: uuid.UUID | None = None,
) -> int:
    rows = await monitoring.same_question_rows(session, user.institution_id, row_id)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "question not found")
    for row in rows:
        row.status = new_status
        if entry_id is not None:
            row.resolved_entry_id = entry_id
    await session.flush()
    audit.record(
        session, institution_id=user.institution_id, action=new_status,
        table_name="unanswered_queries", row_id=row_id,
        diff={"rows": len(rows), "resolved_entry_id": entry_id},
        actor_label=user.label, actor_id=user.user_id,
    )  # fmt: skip
    return len(rows)


@router.post("/unanswered/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
async def act_on_unanswered(
    row_id: uuid.UUID, body: UnansweredAction, user: StaffUser, session: Session
) -> None:
    async with session.begin():
        await _resolve_unanswered(session, user, row_id, body.status)
