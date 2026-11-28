"""Staff and admin accounts (ADM-4, AUTH-2, D16).

Accounts are created by an admin through the Supabase Admin API with the email already
confirmed, so no email is ever sent. The admin gives the new staff member a temporary password.
The role lives only in `profiles` (never in Supabase user metadata).

Without a Supabase project (DEV_AUTH on a laptop) `LocalAuthAdmin` creates profiles only; the
dev login then signs those users in by email.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import Department, Office, Profile
from app.services import audit
from app.services.content_admin import ContentError

log = get_logger("users")

StaffRole = Literal["staff", "admin"]
BANNED_FOR = "876000h"  # about 100 years: Supabase's way to block sign-in


class AuthAdminError(Exception):
    """The auth provider refused the request. The message is safe to show."""


class AuthAdmin(Protocol):
    async def create_user(self, email: str, password: str) -> uuid.UUID: ...
    async def set_blocked(self, user_id: uuid.UUID, blocked: bool) -> None: ...
    async def delete_user(self, user_id: uuid.UUID) -> None: ...


class SupabaseAuthAdmin:
    """Supabase Auth Admin API (service role key, server only)."""

    def __init__(self, url: str, service_key: str, timeout: float) -> None:
        self._base = f"{url.rstrip('/')}/auth/v1/admin/users"
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self._timeout = timeout

    async def _call(self, method: str, url: str, body: dict[str, Any] | None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(method, url, json=body, headers=self._headers)
        if response.status_code >= 400:
            try:
                detail = response.json().get("msg") or response.json().get("message")
            except ValueError:
                detail = None
            log.warning("supabase_admin_error", status=response.status_code)
            raise AuthAdminError(detail or f"Supabase Auth returned {response.status_code}")
        return response.json() if response.content else {}

    async def create_user(self, email: str, password: str) -> uuid.UUID:
        data = await self._call(
            "POST", self._base, {"email": email, "password": password, "email_confirm": True}
        )
        return uuid.UUID(str(data["id"]))

    async def set_blocked(self, user_id: uuid.UUID, blocked: bool) -> None:
        await self._call(
            "PUT", f"{self._base}/{user_id}", {"ban_duration": BANNED_FOR if blocked else "none"}
        )

    async def delete_user(self, user_id: uuid.UUID) -> None:
        await self._call("DELETE", f"{self._base}/{user_id}", None)


class LocalAuthAdmin:
    """Laptop only (DEV_AUTH): no auth server, so users exist only as profiles."""

    async def create_user(self, email: str, password: str) -> uuid.UUID:
        return uuid.uuid4()

    async def set_blocked(self, user_id: uuid.UUID, blocked: bool) -> None:
        return None

    async def delete_user(self, user_id: uuid.UUID) -> None:
        return None


def build_auth_admin(settings: Settings) -> AuthAdmin | None:
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseAuthAdmin(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
            settings.supabase_timeout_seconds,
        )
    if settings.dev_auth:
        return LocalAuthAdmin()
    return None


@dataclass(frozen=True)
class NewStaff:
    email: str
    password: str
    full_name: str
    role: StaffRole
    department_id: uuid.UUID | None = None
    office_id: uuid.UUID | None = None


async def _check_scope(
    session: AsyncSession,
    institution_id: uuid.UUID,
    department_id: uuid.UUID | None,
    office_id: uuid.UUID | None,
) -> None:
    if department_id is not None:
        dept = await session.get(Department, department_id)
        if dept is None or dept.institution_id != institution_id:
            raise ContentError("Unknown department.")
    if office_id is not None:
        office = await session.get(Office, office_id)
        if office is None or office.institution_id != institution_id:
            raise ContentError("Unknown office.")


def _audit(
    session: AsyncSession,
    actor: AuthenticatedUser,
    action: str,
    row_id: uuid.UUID,
    diff: dict[str, Any],
) -> None:
    audit.record(
        session,
        institution_id=actor.institution_id,
        action=action,
        table_name="profiles",
        row_id=row_id,
        diff=diff,
        actor_label=actor.label,
        actor_id=actor.user_id,
    )


async def create_staff(
    session: AsyncSession, auth_admin: AuthAdmin, actor: AuthenticatedUser, new: NewStaff
) -> Profile:
    email = new.email.strip().lower()
    existing = (
        await session.execute(select(Profile.id).where(Profile.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise ContentError("A user with this email already exists.")
    if new.role == "staff" and new.department_id is None and new.office_id is None:
        raise ContentError("Staff need a department or an office (they edit only that content).")
    await _check_scope(session, actor.institution_id, new.department_id, new.office_id)
    user_id = await auth_admin.create_user(email, new.password)
    profile = Profile(
        id=user_id,
        institution_id=actor.institution_id,
        role=new.role,
        full_name=new.full_name.strip(),
        email=email,
        department_id=new.department_id,
        office_id=new.office_id,
        is_active=True,
    )
    session.add(profile)
    try:
        await session.flush()
    except Exception:
        await auth_admin.delete_user(user_id)  # do not leave an auth user without a profile
        raise
    _audit(session, actor, "create", user_id, {"new": {
        "email": email, "role": new.role, "full_name": profile.full_name,
        "department_id": new.department_id, "office_id": new.office_id,
    }})  # fmt: skip
    return profile


async def update_staff(
    session: AsyncSession,
    auth_admin: AuthAdmin,
    actor: AuthenticatedUser,
    user_id: uuid.UUID,
    changes: dict[str, Any],
) -> Profile:
    profile = await session.get(Profile, user_id)
    if profile is None or profile.institution_id != actor.institution_id:
        raise ContentError("User not found.")
    if user_id == actor.user_id and (
        changes.get("is_active") is False or changes.get("role", "admin") != "admin"
    ):
        raise ContentError("You cannot deactivate or demote your own account.")
    allowed = {"role", "full_name", "department_id", "office_id", "is_active"}
    unknown = set(changes) - allowed
    if unknown:
        raise ContentError(f"Cannot change: {', '.join(sorted(unknown))}")
    if changes.get("role") not in (None, "student", "staff", "admin"):
        raise ContentError("Unknown role.")
    await _check_scope(
        session, actor.institution_id, changes.get("department_id"), changes.get("office_id")
    )
    diff = {
        name: {"old": getattr(profile, name), "new": value}
        for name, value in changes.items()
        if getattr(profile, name) != value
    }
    if not diff:
        return profile
    for name, value in changes.items():
        setattr(profile, name, value)
    if profile.role == "staff" and profile.department_id is None and profile.office_id is None:
        raise ContentError("Staff need a department or an office.")
    await session.flush()
    if "is_active" in diff:
        await auth_admin.set_blocked(user_id, blocked=not profile.is_active)
    action = "deactivate" if diff.get("is_active", {}).get("new") is False else "update"
    _audit(session, actor, action, user_id, diff)
    return profile


async def list_staff(session: AsyncSession, institution_id: uuid.UUID) -> list[Profile]:
    """Staff and admins (students are anonymous and not listed)."""
    rows = await session.execute(
        select(Profile)
        .where(Profile.institution_id == institution_id, Profile.role.in_(("staff", "admin")))
        .order_by(Profile.role, Profile.full_name, Profile.email)
    )
    return list(rows.scalars())
