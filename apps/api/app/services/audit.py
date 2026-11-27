"""Audit log writes (ADM-2, Memory rule 7).

Call `record()` inside the same session/transaction as the change it describes, so the audit
row and the change commit or roll back together.
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


def _jsonable(value: Any) -> Any:
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def record(
    session: AsyncSession,
    *,
    institution_id: uuid.UUID,
    action: str,
    table_name: str,
    row_id: uuid.UUID | None,
    diff: dict[str, Any],
    actor_label: str,
    actor_id: uuid.UUID | None = None,
) -> None:
    """Stage an audit row in the current transaction."""
    session.add(
        AuditLog(
            institution_id=institution_id,
            actor_id=actor_id,
            actor_label=actor_label,
            action=action,
            table_name=table_name,
            row_id=row_id,
            diff=_jsonable(diff),
        )
    )
