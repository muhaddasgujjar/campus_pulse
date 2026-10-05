"""audit_log.created_at uses clock_timestamp() so actions within one transaction keep their order

Revision ID: 3f6c1a2b9d04
Revises: de29bee228d2
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '3f6c1a2b9d04'
down_revision: Union[str, Sequence[str], None] = 'de29bee228d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('audit_log', 'created_at', server_default=sa.text('clock_timestamp()'))


def downgrade() -> None:
    op.alter_column('audit_log', 'created_at', server_default=sa.text('now()'))
