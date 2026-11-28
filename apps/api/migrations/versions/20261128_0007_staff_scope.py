"""Staff scope for RBAC (AUTH-3): office on profiles, kb_entries and documents; department on
timetable; staff email on profiles (shown in the Users screen, ADM-4)

All columns are nullable and additive. Staff may edit rows of their own department or office.

Revision ID: 7a3c9e5f4d12
Revises: 6f2b8d4e3c01
Create Date: 2026-11-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '7a3c9e5f4d12'
down_revision: Union[str, Sequence[str], None] = '6f2b8d4e3c01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OFFICE_TABLES = ('profiles', 'kb_entries', 'documents')


def upgrade() -> None:
    for table in _OFFICE_TABLES:
        op.add_column(table, sa.Column('office_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            op.f(f'fk_{table}_office_id_offices'), table, 'offices', ['office_id'], ['id'],
            ondelete='SET NULL',
        )
    op.add_column('profiles', sa.Column('email', sa.Text(), nullable=True))
    op.add_column('timetable', sa.Column('department_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f('fk_timetable_department_id_departments'), 'timetable', 'departments',
        ['department_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(op.f('fk_timetable_department_id_departments'), 'timetable', type_='foreignkey')
    op.drop_column('timetable', 'department_id')
    op.drop_column('profiles', 'email')
    for table in _OFFICE_TABLES:
        op.drop_constraint(op.f(f'fk_{table}_office_id_offices'), table, type_='foreignkey')
        op.drop_column(table, 'office_id')
