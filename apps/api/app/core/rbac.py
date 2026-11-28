"""Role-based access control (AUTH-3, rule 5). The matrix of Architectural.md Section 11.

Enforced on the server in every admin endpoint (app.api.deps). The UI only hides buttons.
"""

import uuid
from typing import Literal, get_args

from app.core.auth import AuthenticatedUser, Role

Action = Literal[
    "chat",  # chat, voice, deadlines
    "edit_own_profile",
    "edit_content",  # create or edit content of the user's own department or office
    "approve_content",
    "manage_users",
    "view_audit",
    "view_metrics",
    "export",
    "edit_settings",
]
ACTIONS: tuple[Action, ...] = get_args(Action)

_EVERYONE: frozenset[Role] = frozenset({"anonymous", "student", "staff", "admin"})
_SIGNED_IN: frozenset[Role] = frozenset({"student", "staff", "admin"})
_STAFF: frozenset[Role] = frozenset({"staff", "admin"})
_ADMIN: frozenset[Role] = frozenset({"admin"})

MATRIX: dict[Action, frozenset[Role]] = {
    "chat": _EVERYONE,
    "edit_own_profile": _SIGNED_IN,
    "edit_content": _STAFF,
    "approve_content": _ADMIN,
    "manage_users": _ADMIN,
    "view_audit": _ADMIN,
    "view_metrics": _ADMIN,
    "export": _ADMIN,
    "edit_settings": _ADMIN,
}


def allowed(role: Role, action: Action) -> bool:
    return role in MATRIX[action]


def can_edit_row(
    user: AuthenticatedUser, *, department_id: uuid.UUID | None, office_id: uuid.UUID | None
) -> bool:
    """Admins edit every row. Staff edit rows of their own department or office only; a row
    with neither belongs to nobody and is admin-only."""
    if user.role == "admin":
        return True
    if user.role != "staff":
        return False
    same_department = user.department_id is not None and department_id == user.department_id
    same_office = user.office_id is not None and office_id == user.office_id
    return same_department or same_office
