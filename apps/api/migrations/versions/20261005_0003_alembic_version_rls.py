"""enable RLS on alembic_version: on Supabase every public table is exposed to the Data API (D16)

Revision ID: 7b2e4d9a1c35
Revises: 3f6c1a2b9d04
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op

revision: str = '7b2e4d9a1c35'
down_revision: Union[str, Sequence[str], None] = '3f6c1a2b9d04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('alter table alembic_version enable row level security')


def downgrade() -> None:
    op.execute('alter table alembic_version disable row level security')
