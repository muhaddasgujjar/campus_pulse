"""Admin portal: users (ADM-4), audit log (ADM-2), dashboard metrics (ADM-3), settings (ADP-2)
and the department and office lists the forms need.

Users, audit, metrics and settings are admin only (Architectural.md Section 11). Every write
records an audit row in the same transaction (rule 7); settings changes also move the cache's
`data_version`, so the chat shows new text at once.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import Session, StaffUser, chat_services, require
from app.core.auth import AuthenticatedUser
from app.db.models import AuditLog, Department, Institution, Office, Profile
from app.services import audit, monitoring
from app.services import users as accounts
from app.services.chat import ChatServices
from app.services.content_admin import ContentError

router = APIRouter(prefix="/api/admin", tags=["admin"])
Services = Annotated[ChatServices, Depends(chat_services)]
UserAdmin = Annotated[AuthenticatedUser, Depends(require("manage_users"))]
AuditViewer = Annotated[AuthenticatedUser, Depends(require("view_audit"))]
MetricsViewer = Annotated[AuthenticatedUser, Depends(require("view_metrics"))]
SettingsEditor = Annotated[AuthenticatedUser, Depends(require("edit_settings"))]


def auth_admin(request: Request) -> accounts.AuthAdmin:
    found: accounts.AuthAdmin | None = getattr(request.app.state, "auth_admin", None)
    if found is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "account creation is not configured (SUPABASE_URL and the service role key)",
        )
    return found


AuthAdminDep = Annotated[accounts.AuthAdmin, Depends(auth_admin)]


# --- lookups ------------------------------------------------------------------------------


class Named(BaseModel):
    id: uuid.UUID
    name: str


class Lookups(BaseModel):
    departments: list[Named]
    offices: list[Named]


@router.get("/lookups", response_model=Lookups)
async def lookups(user: StaffUser, session: Session) -> Lookups:
    departments = await session.execute(
        select(Department.id, Department.name)
        .where(Department.institution_id == user.institution_id)
        .order_by(Department.name)
    )
    offices = await session.execute(
        select(Office.id, Office.name)
        .where(Office.institution_id == user.institution_id)
        .order_by(Office.name)
    )
    return Lookups(
        departments=[Named(id=i, name=n) for i, n in departments],
        offices=[Named(id=i, name=n) for i, n in offices],
    )


# --- users (ADM-4) -----------------------------------------------------------------------


class UserOut(BaseModel):
    id: uuid.UUID
    email: str | None
    full_name: str | None
    role: str
    department_id: uuid.UUID | None
    office_id: uuid.UUID | None
    is_active: bool
    created_at: datetime

    @classmethod
    def of(cls, p: Profile) -> "UserOut":
        return cls(
            id=p.id,
            email=p.email,
            full_name=p.full_name,
            role=p.role,
            department_id=p.department_id,
            office_id=p.office_id,
            is_active=p.is_active,
            created_at=p.created_at,
        )


class UserCreate(BaseModel):
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=72)  # temporary, given to the person
    full_name: str = Field(min_length=2, max_length=200)
    role: accounts.StaffRole = "staff"
    department_id: uuid.UUID | None = None
    office_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: Literal["staff", "admin"] | None = None
    department_id: uuid.UUID | None = None
    office_id: uuid.UUID | None = None
    is_active: bool | None = None


@router.get("/users", response_model=list[UserOut])
async def list_users(user: UserAdmin, session: Session) -> list[UserOut]:
    return [UserOut.of(p) for p in await accounts.list_staff(session, user.institution_id)]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, user: UserAdmin, session: Session, provider: AuthAdminDep
) -> UserOut:
    """Creates the Supabase account with the email already confirmed (no email is sent)."""
    new = accounts.NewStaff(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        role=body.role,
        department_id=body.department_id,
        office_id=body.office_id,
    )
    async with session.begin():
        try:
            profile = await accounts.create_staff(session, provider, user, new)
        except ContentError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        except accounts.AuthAdminError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return UserOut.of(profile)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, user: UserAdmin, session: Session, provider: AuthAdminDep
) -> UserOut:
    """Only the fields sent are changed. Send `department_id: null` to clear it."""
    changes = body.model_dump(exclude_unset=True)
    async with session.begin():
        try:
            profile = await accounts.update_staff(session, provider, user, user_id, changes)
        except ContentError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        except accounts.AuthAdminError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return UserOut.of(profile)


# --- audit log (ADM-2) --------------------------------------------------------------------


class AuditOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    actor_label: str | None
    action: str
    table_name: str
    row_id: uuid.UUID | None
    diff: dict[str, Any]


class AuditPage(BaseModel):
    items: list[AuditOut]
    actions: list[str]
    tables: list[str]


@router.get("/audit", response_model=AuditPage)
async def audit_log(
    user: AuditViewer,
    session: Session,
    services: Services,
    actor: Annotated[str | None, Query(max_length=200)] = None,
    action: Annotated[str | None, Query(max_length=40)] = None,
    table: Annotated[str | None, Query(max_length=60)] = None,
    since: date | None = None,
    until: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    """Newest first. `since` and `until` are institution-local days, both included."""
    offset_hours = services.settings.institution_utc_offset_hours
    day = monitoring.local_day(AuditLog.created_at, offset_hours)
    inst = AuditLog.institution_id == user.institution_id
    stmt = select(AuditLog).where(inst)
    if actor:
        stmt = stmt.where(AuditLog.actor_label.ilike(f"%{actor.strip()}%"))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if table:
        stmt = stmt.where(AuditLog.table_name == table)
    if since:
        stmt = stmt.where(day >= since)
    if until:
        stmt = stmt.where(day <= until)
    rows = await session.execute(
        stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    )
    actions = await session.execute(
        select(AuditLog.action).where(inst).distinct().order_by(AuditLog.action)
    )
    tables = await session.execute(
        select(AuditLog.table_name).where(inst).distinct().order_by(AuditLog.table_name)
    )
    return AuditPage(
        items=[
            AuditOut(
                id=r.id,
                created_at=r.created_at,
                actor_label=r.actor_label,
                action=r.action,
                table_name=r.table_name,
                row_id=r.row_id,
                diff=dict(r.diff or {}),
            )
            for r in rows.scalars()
        ],
        actions=list(actions.scalars()),
        tables=list(tables.scalars()),
    )


# --- metrics (ADM-3) ----------------------------------------------------------------------


class DayOut(BaseModel):
    day: date
    questions: int
    fallbacks: int


class Counted(BaseModel):
    label: str
    count: int


class MetricsOut(BaseModel):
    window_days: int
    days: list[DayOut]
    questions_today: int
    fallback_rate: float | None
    avg_latency_ms: int | None
    thumbs_up_rate: float | None
    thumbs_down: int
    top_questions: list[Counted]
    tool_usage: list[Counted]
    open_unanswered: int
    needs_review: int
    recent_thumbs_down: list[dict[str, Any]]
    usage_today: dict[str, int]
    database_bytes: int | None
    database_limit_bytes: int


@router.get("/metrics", response_model=MetricsOut)
async def dashboard_metrics(
    user: MetricsViewer,
    session: Session,
    services: Services,
    days: Annotated[int, Query(ge=7, le=90)] = 14,
) -> MetricsOut:
    m = await monitoring.metrics(
        session,
        user.institution_id,
        services.today(),
        services.settings.institution_utc_offset_hours,
        window_days=days,
    )
    return MetricsOut(
        window_days=m.window_days,
        days=[DayOut(day=d.day, questions=d.questions, fallbacks=d.fallbacks) for d in m.days],
        questions_today=m.questions_today,
        fallback_rate=m.fallback_rate,
        avg_latency_ms=m.avg_latency_ms,
        thumbs_up_rate=m.thumbs_up_rate,
        thumbs_down=m.thumbs_down,
        top_questions=[Counted(label=q, count=n) for q, n in m.top_questions],
        tool_usage=[Counted(label=t, count=n) for t, n in m.tool_usage],
        open_unanswered=m.open_unanswered,
        needs_review=m.needs_review,
        recent_thumbs_down=m.recent_thumbs_down,
        usage_today=m.usage_today,
        database_bytes=m.database_bytes,
        database_limit_bytes=m.database_limit_bytes,
    )


# --- settings (ADP-2) ---------------------------------------------------------------------


class Contact(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=200)


class SettingsIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    short_name: str | None = Field(default=None, max_length=20)
    disclaimer: str = Field(min_length=10, max_length=600)
    starter_questions: list[Annotated[str, Field(min_length=3, max_length=120)]] = Field(
        default_factory=list, max_length=6
    )
    fallback_office: str | None = Field(default=None, max_length=120)
    contacts: list[Contact] = Field(default_factory=list, max_length=20)
    live_fetch_allowlist: list[Annotated[str, Field(min_length=3, max_length=120)]] = Field(
        default_factory=list, max_length=20
    )


SETTINGS_KEYS = ("short_name", "disclaimer", "starter_questions", "fallback_office", "contacts",
                 "live_fetch_allowlist")  # fmt: skip


def _settings_out(inst: Institution, default_disclaimer: str) -> SettingsIn:
    config = dict(inst.config or {})
    return SettingsIn.model_validate(
        {
            "name": inst.name,
            "short_name": config.get("short_name"),
            "disclaimer": config.get("disclaimer") or default_disclaimer,
            "starter_questions": config.get("starter_questions") or [],
            "fallback_office": config.get("fallback_office"),
            "contacts": config.get("contacts") or [],
            "live_fetch_allowlist": config.get("live_fetch_allowlist") or [],
        }
    )


async def _institution(session: Session, user: AuthenticatedUser) -> Institution:
    inst = await session.get(Institution, user.institution_id)
    if inst is None:  # pragma: no cover - the user's institution always exists
        raise HTTPException(status.HTTP_404_NOT_FOUND, "institution not found")
    return inst


@router.get("/settings", response_model=SettingsIn)
async def get_settings_(user: SettingsEditor, session: Session, services: Services) -> SettingsIn:
    inst = await _institution(session, user)
    return _settings_out(inst, services.settings.institution_disclaimer)


@router.put("/settings", response_model=SettingsIn)
async def put_settings(
    body: SettingsIn, user: SettingsEditor, session: Session, services: Services
) -> SettingsIn:
    async with session.begin():
        inst = await _institution(session, user)
        if body.fallback_office:
            # Must name a real office: a typo would leave unanswered questions with no contact.
            office = (
                await session.execute(
                    select(Office.name).where(
                        Office.institution_id == user.institution_id,
                        func.lower(Office.name) == body.fallback_office.strip().lower(),
                    )
                )
            ).scalar_one_or_none()
            if office is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"No office is named {body.fallback_office!r}. "
                    "Choose one from the Offices table.",
                )
            body.fallback_office = office
        before = _settings_out(inst, services.settings.institution_disclaimer).model_dump()
        after = body.model_dump()
        diff = {k: {"old": before[k], "new": v} for k, v in after.items() if before[k] != v}
        if diff:
            config = dict(inst.config or {})
            config.update({k: after[k] for k in SETTINGS_KEYS})
            inst.config = config  # a new dict, so SQLAlchemy sees the change
            inst.name = body.name
            await session.flush()
            audit.record(
                session,
                institution_id=user.institution_id,
                action="update",
                table_name="institutions",
                row_id=inst.id,
                diff=diff,
                actor_label=user.label,
                actor_id=user.user_id,
            )
    return _settings_out(inst, services.settings.institution_disclaimer)
