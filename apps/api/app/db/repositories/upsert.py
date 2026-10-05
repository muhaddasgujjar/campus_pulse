"""Idempotent upsert by natural key, with an audit row per change (used by seeds and imports)."""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Base
from app.services import audit

ModelT = TypeVar("ModelT", bound=Base)
Outcome = Literal["created", "updated", "unchanged"]


@dataclass
class UpsertStats:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    ids: list[uuid.UUID] = field(default_factory=list)

    def add(self, outcome: Outcome, row_id: uuid.UUID) -> None:
        setattr(self, outcome, getattr(self, outcome) + 1)
        self.ids.append(row_id)


def _same(current: Any, new: Any) -> bool:
    if isinstance(current, Decimal) and new is not None:
        return current == Decimal(str(new))
    return bool(current == new)


async def upsert(
    session: AsyncSession,
    model: type[ModelT],
    *,
    key: dict[str, Any],
    values: dict[str, Any],
    institution_id: uuid.UUID,
    actor_label: str,
) -> tuple[ModelT, Outcome]:
    """Insert the row identified by `key`, or update the columns in `values` that changed."""
    stmt = select(model).filter_by(**key).limit(1)
    row = (await session.execute(stmt)).scalar_one_or_none()
    table = model.__tablename__

    if row is None:
        row = model(**key, **values)
        session.add(row)
        await session.flush()
        audit.record(
            session,
            institution_id=institution_id,
            action="create",
            table_name=table,
            row_id=row.id,  # type: ignore[attr-defined]
            diff={"new": {**key, **values}},
            actor_label=actor_label,
        )
        return row, "created"

    changes = {
        name: {"old": getattr(row, name), "new": value}
        for name, value in values.items()
        if not _same(getattr(row, name), value)
    }
    if not changes:
        return row, "unchanged"
    for name, change in changes.items():
        setattr(row, name, change["new"])
    await session.flush()
    audit.record(
        session,
        institution_id=institution_id,
        action="update",
        table_name=table,
        row_id=row.id,  # type: ignore[attr-defined]
        diff=changes,
        actor_label=actor_label,
    )
    return row, "updated"
