"""RBAC matrix (Architectural.md Section 11) and staff scope (AUTH-3). Written before the code.

Every cell of the matrix is pinned, so a change to who may do what fails a test.
"""

import uuid

import pytest

from app.core.auth import AuthenticatedUser, Role
from app.core.rbac import ACTIONS, Action, allowed, can_edit_row

INST = uuid.uuid4()
DEPT_CS, DEPT_EE = uuid.uuid4(), uuid.uuid4()
OFFICE_EXAMS, OFFICE_ACCOUNTS = uuid.uuid4(), uuid.uuid4()

# (action, anonymous, student, staff, admin)
MATRIX: list[tuple[Action, bool, bool, bool, bool]] = [
    ("chat", True, True, True, True),
    ("edit_own_profile", False, True, True, True),
    ("edit_content", False, False, True, True),
    ("approve_content", False, False, False, True),
    ("manage_users", False, False, False, True),
    ("view_audit", False, False, False, True),
    ("view_metrics", False, False, False, True),
    ("export", False, False, False, True),
    ("edit_settings", False, False, False, True),
]
ROLES: tuple[Role, ...] = ("anonymous", "student", "staff", "admin")


def user(
    role: Role, department_id: uuid.UUID | None = None, office_id: uuid.UUID | None = None
) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=uuid.uuid4(),
        role=role,
        is_anonymous=role == "student",
        institution_id=INST,
        department_id=department_id,
        office_id=office_id,
    )


def test_matrix_covers_every_action() -> None:
    assert {row[0] for row in MATRIX} == set(ACTIONS)


@pytest.mark.parametrize(("action", "anonymous", "student", "staff", "admin"), MATRIX)
def test_matrix_cell(
    action: Action, anonymous: bool, student: bool, staff: bool, admin: bool
) -> None:
    expected = dict(zip(ROLES, (anonymous, student, staff, admin), strict=True))
    assert {role: allowed(role, action) for role in ROLES} == expected


def test_admin_may_edit_any_row() -> None:
    admin = user("admin")
    assert can_edit_row(admin, department_id=DEPT_CS, office_id=None)
    assert can_edit_row(admin, department_id=None, office_id=None)


def test_staff_may_edit_rows_of_their_department() -> None:
    staff = user("staff", department_id=DEPT_CS)
    assert can_edit_row(staff, department_id=DEPT_CS, office_id=None)
    assert not can_edit_row(staff, department_id=DEPT_EE, office_id=None)


def test_staff_may_edit_rows_of_their_office() -> None:
    staff = user("staff", office_id=OFFICE_EXAMS)
    assert can_edit_row(staff, department_id=None, office_id=OFFICE_EXAMS)
    assert not can_edit_row(staff, department_id=None, office_id=OFFICE_ACCOUNTS)


def test_staff_with_department_and_office_may_edit_either() -> None:
    staff = user("staff", department_id=DEPT_CS, office_id=OFFICE_EXAMS)
    assert can_edit_row(staff, department_id=DEPT_CS, office_id=None)
    assert can_edit_row(staff, department_id=None, office_id=OFFICE_EXAMS)
    assert not can_edit_row(staff, department_id=DEPT_EE, office_id=OFFICE_ACCOUNTS)


def test_unowned_rows_are_admin_only() -> None:
    """A row with no department and no office belongs to nobody, so only an admin edits it."""
    staff = user("staff", department_id=DEPT_CS, office_id=OFFICE_EXAMS)
    assert not can_edit_row(staff, department_id=None, office_id=None)


def test_staff_without_any_scope_may_edit_nothing() -> None:
    staff = user("staff")
    assert not can_edit_row(staff, department_id=None, office_id=None)
    assert not can_edit_row(staff, department_id=DEPT_CS, office_id=OFFICE_EXAMS)


@pytest.mark.parametrize("role", ["anonymous", "student"])
def test_students_and_anonymous_edit_no_rows(role: Role) -> None:
    person = user(role, department_id=DEPT_CS, office_id=OFFICE_EXAMS)
    assert not can_edit_row(person, department_id=DEPT_CS, office_id=OFFICE_EXAMS)
