"""Who is signed in (AUTH-1, AUTH-2, AUTH-4): verified token claims -> profile -> role.

- The role is read from `profiles.role`, never from the token.
- A token whose user has no profile yet gets a `student` profile (Supabase anonymous sign-in,
  AUTH-4). Staff and admin profiles are created only by an admin (ADM-4, app.services.users).
- A deactivated profile is refused, even with a valid token.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, Role, TokenClaims
from app.db.models import Profile


class AccountError(Exception):
    """The account cannot be used (deactivated, other institution). Maps to HTTP 403."""


def to_user(profile: Profile, *, is_anonymous: bool) -> AuthenticatedUser:
    role: Role = profile.role  # type: ignore[assignment]  # check constraint: student|staff|admin
    return AuthenticatedUser(
        user_id=profile.id,
        role=role,
        is_anonymous=is_anonymous,
        institution_id=profile.institution_id,
        department_id=profile.department_id,
        office_id=profile.office_id,
        email=profile.email,
        full_name=profile.full_name,
    )


async def resolve_user(
    session: AsyncSession, claims: TokenClaims, institution_id: uuid.UUID
) -> AuthenticatedUser:
    """Load (or, for a new student, create) the profile. Commits, so the caller's session is
    free to begin its own transaction afterwards."""
    profile = await session.get(Profile, claims.user_id)
    if profile is None:
        profile = Profile(
            id=claims.user_id, institution_id=institution_id, role="student", is_active=True
        )
        session.add(profile)
        await session.flush()
    await session.commit()
    if profile.institution_id != institution_id:
        raise AccountError("this account belongs to another institution")
    if not profile.is_active:
        raise AccountError("this account is deactivated")
    return to_user(profile, is_anonymous=claims.is_anonymous)
