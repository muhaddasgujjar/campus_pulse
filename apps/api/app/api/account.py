"""Signed-in user endpoints (AUTH-1, AUTH-4, PRIV-2) and the deadlines card (CHAT-7).

- GET /api/me: who am I (role from `profiles`, never from the token).
- PUT /api/me/profile: program, semester, section, language (students personalise answers).
- DELETE /api/me/data: "Delete my data": the user's conversations (messages and feedback
  cascade) and profile details. Content a staff member wrote stays (it belongs to the office).
- POST /api/auth/dev-login: laptop only (DEV_AUTH). Production sign-in is Supabase Auth in the
  browser (staff: email and password; students: anonymous sign-in).
- GET /api/deadlines: upcoming key dates, public.
"""

import datetime as dt
import uuid
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select

from app.api.deps import CurrentUser, Session, chat_services, institution_id, token_verifier
from app.core.auth import AuthError, TokenVerifier
from app.core.config import Settings, get_settings
from app.core.rbac import ACTIONS, allowed
from app.db.models import Conversation, KeyDate, Profile
from app.services import audit
from app.services.chat import ChatServices

router = APIRouter(prefix="/api", tags=["account"])
Services = Annotated[ChatServices, Depends(chat_services)]
Verifier = Annotated[TokenVerifier, Depends(token_verifier)]
Institution = Annotated[uuid.UUID, Depends(institution_id)]


class MeOut(BaseModel):
    id: uuid.UUID
    role: str
    is_anonymous: bool
    email: str | None
    full_name: str | None
    department_id: uuid.UUID | None
    office_id: uuid.UUID | None
    program: str | None
    semester: int | None
    section: str | None
    language_pref: str | None
    permissions: list[str]  # what the UI may show; the server checks every call anyway


async def _me(session: Session, user_id: uuid.UUID, is_anonymous: bool) -> MeOut:
    profile = await session.get(Profile, user_id)
    if profile is None:  # pragma: no cover - resolve_user creates it
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    role = profile.role
    return MeOut(
        id=profile.id,
        role=role,
        is_anonymous=is_anonymous,
        email=profile.email,
        full_name=profile.full_name,
        department_id=profile.department_id,
        office_id=profile.office_id,
        program=profile.program,
        semester=profile.semester,
        section=profile.section,
        language_pref=profile.language_pref,
        permissions=[a for a in ACTIONS if allowed(role, a)],  # type: ignore[arg-type]
    )


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser, session: Session) -> MeOut:
    return await _me(session, user.user_id, user.is_anonymous)


class ProfileIn(BaseModel):
    program: str | None = Field(default=None, max_length=40)
    semester: int | None = Field(default=None, ge=1, le=12)
    section: str | None = Field(default=None, max_length=10)
    language_pref: Literal["en", "ur"] | None = None


@router.put("/me/profile", response_model=MeOut)
async def update_profile(body: ProfileIn, user: CurrentUser, session: Session) -> MeOut:
    async with session.begin():
        profile = await session.get(Profile, user.user_id)
        if profile is None:  # pragma: no cover
            raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
        for name, value in body.model_dump().items():
            if isinstance(value, str):
                value = value.strip() or None
            setattr(profile, name, value)
    return await _me(session, user.user_id, user.is_anonymous)


class DeletedOut(BaseModel):
    conversations: int


@router.delete("/me/data", response_model=DeletedOut)
async def delete_my_data(user: CurrentUser, session: Session) -> DeletedOut:
    """Deletes the user's chats and clears their profile details. The audit row records only
    that it happened and how many chats, never their content (PRIV-2)."""
    async with session.begin():
        result = await session.execute(
            delete(Conversation).where(
                Conversation.user_id == user.user_id,
                Conversation.institution_id == user.institution_id,
            )
        )
        removed = int(getattr(result, "rowcount", 0) or 0)
        profile = await session.get(Profile, user.user_id)
        if profile is not None:
            profile.program = profile.semester = profile.section = None
            profile.language_pref = None
            if profile.role == "student":
                profile.full_name = None
        audit.record(
            session,
            institution_id=user.institution_id,
            action="delete_my_data",
            table_name="conversations",
            row_id=user.user_id,
            diff={"conversations": removed},
            actor_label=user.label,
            actor_id=user.user_id,
        )
    return DeletedOut(conversations=removed)


# --- local sign-in (DEV_AUTH only) ---------------------------------------------------------


class DevLoginIn(BaseModel):
    email: str | None = Field(default=None, max_length=254)  # empty = new anonymous student


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth token type, not a secret


@router.post("/auth/dev-login", response_model=TokenOut)
async def dev_login(
    body: DevLoginIn,
    session: Session,
    verifier: Verifier,
    inst: Institution,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenOut:
    """A laptop has no Supabase Auth: sign in as an existing staff or admin profile by email,
    or as a new anonymous student. Refused unless DEV_AUTH (APP_ENV local or test only)."""
    if not settings.dev_auth:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    if not body.email:
        token = verifier.issue_dev_token(uuid.uuid4(), email=None, is_anonymous=True)
        return TokenOut(access_token=token)
    profile = (
        await session.execute(
            select(Profile).where(
                Profile.institution_id == inst,
                func.lower(Profile.email) == body.email.strip().lower(),
            )
        )
    ).scalar_one_or_none()
    if profile is None or not profile.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown or inactive account")
    try:
        token = verifier.issue_dev_token(profile.id, email=profile.email, is_anonymous=False)
    except AuthError as exc:  # pragma: no cover - dev_auth without a secret
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return TokenOut(access_token=token)


# --- deadlines card (CHAT-7) --------------------------------------------------------------


class DeadlineOut(BaseModel):
    id: uuid.UUID
    title: str
    date: dt.date
    kind: str
    program_scope: str | None
    office_name: str | None
    days_left: int
    last_verified: dt.date | None


@router.get("/deadlines", response_model=list[DeadlineOut])
async def deadlines(
    session: Session,
    services: Services,
    inst: Institution,
    program: Annotated[str | None, Query(max_length=40)] = None,
    days: Annotated[int, Query(ge=1, le=365)] = 60,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> list[DeadlineOut]:
    """Key dates from today (institution-local) up to `days` ahead, soonest first. With a
    program, dates for every program are included too."""
    today = services.today()
    stmt = select(KeyDate).where(
        KeyDate.institution_id == inst,
        KeyDate.date >= today,
        KeyDate.date <= today + timedelta(days=days),
    )
    if program:
        stmt = stmt.where(
            or_(KeyDate.program_scope.is_(None), KeyDate.program_scope.ilike(f"%{program}%"))
        )
    rows = await session.execute(stmt.order_by(KeyDate.date, KeyDate.title).limit(limit))
    return [
        DeadlineOut(
            id=k.id,
            title=k.title,
            date=k.date,
            kind=k.kind,
            program_scope=k.program_scope,
            office_name=k.office_name,
            days_left=(k.date - today).days,
            last_verified=k.last_verified,
        )
        for k in rows.scalars()
    ]
