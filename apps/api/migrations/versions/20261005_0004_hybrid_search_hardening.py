"""hybrid_search: fixed search_path, and not callable by anon/authenticated (D16, Supabase advisor)

All data access goes through FastAPI, which connects as the table owner, so revoking EXECUTE
from PUBLIC (and Supabase's anon and authenticated roles, when present) changes nothing for it.

Revision ID: 9c4d2e7f1a86
Revises: 7b2e4d9a1c35
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op

revision: str = '9c4d2e7f1a86'
down_revision: Union[str, Sequence[str], None] = '7b2e4d9a1c35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SIGNATURE = 'hybrid_search(text, vector, integer, uuid, text, integer)'


def upgrade() -> None:
    op.execute(f'alter function {SIGNATURE} set search_path = public')
    op.execute(f'revoke execute on function {SIGNATURE} from public')
    op.execute(f"""
        do $$
        begin
          if exists (select 1 from pg_roles where rolname = 'anon') then
            revoke execute on function {SIGNATURE} from anon, authenticated;
          end if;
        end
        $$;
    """)


def downgrade() -> None:
    op.execute(f'grant execute on function {SIGNATURE} to public')
    op.execute(f'alter function {SIGNATURE} reset search_path')
