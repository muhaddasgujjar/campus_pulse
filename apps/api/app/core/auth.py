"""Supabase JWT verification (AUTH-2, D16). STUB until M5.

Plan for M5:
- Verify the Supabase access token (JWKS or SUPABASE_JWT_SECRET from env).
- Read the role from `profiles.role` on the server. Never trust user-editable metadata.
- Expose FastAPI dependencies `current_user` and `require_role("staff" | "admin")`.
- RBAC matrix: Architectural.md Section 11. Write the permission tests first.
"""

from dataclasses import dataclass
from typing import Literal

Role = Literal["anonymous", "student", "staff", "admin"]


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    role: Role
    is_anonymous: bool


def verify_supabase_jwt(token: str) -> AuthenticatedUser:
    """Verify a Supabase access token and return the user.

    TODO(M5): check signature, expiry and audience, then load the role from `profiles`.
    Until then every call fails closed.
    """
    raise NotImplementedError("Supabase JWT verification is implemented in M5 (AUTH-2).")
