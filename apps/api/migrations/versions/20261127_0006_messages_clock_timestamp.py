"""messages.created_at uses clock_timestamp(): a question and its answer saved in one transaction
keep their order in the history (CHAT-1) and in resume (CHAT-9)

Revision ID: 6f2b8d4e3c01
Revises: 5e1a7c3d2b90
Create Date: 2026-11-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '6f2b8d4e3c01'
down_revision: Union[str, Sequence[str], None] = '5e1a7c3d2b90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('messages', 'created_at', server_default=sa.text('clock_timestamp()'))


def downgrade() -> None:
    op.alter_column('messages', 'created_at', server_default=sa.text('now()'))
