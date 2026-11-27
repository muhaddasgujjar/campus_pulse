"""audit_log (institution_id, created_at) index: the response cache's data_version is the latest
audit row (every admin write records one, rule 7), read once per uncached turn (COST-3)

Revision ID: 5e1a7c3d2b90
Revises: 9c4d2e7f1a86
Create Date: 2026-11-27
"""
from typing import Sequence, Union

from alembic import op

revision: str = '5e1a7c3d2b90'
down_revision: Union[str, Sequence[str], None] = '9c4d2e7f1a86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_audit_log_institution_id_created_at',
        'audit_log',
        ['institution_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_audit_log_institution_id_created_at', table_name='audit_log')
