"""Read models for the admin portal: dashboard metrics (ADM-3), needs-review queue (DATA-6),
unanswered questions (DATA-7) and the approval diff (DATA-4).

All read-only. Days are the institution's local days (rule 3), not UTC days.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal
from typing import cast as typed

from sqlalchemy import Date, Integer, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import (
    AuditLog,
    Conversation,
    Document,
    Feedback,
    KbEntry,
    Message,
    UnansweredQuery,
    UsageDaily,
)

REVIEW_WINDOW_DAYS = 14  # DATA-6: entries expiring within 14 days, or already expired
DB_LIMIT_BYTES = 500 * 1024 * 1024  # Supabase free plan


def local_day(column: Any, utc_offset_hours: float) -> ColumnElement[date]:
    """The institution-local date of a timestamptz column."""
    return cast(func.timezone("UTC", column) + timedelta(hours=utc_offset_hours), Date)


@dataclass
class DayPoint:
    day: date
    questions: int = 0
    fallbacks: int = 0


@dataclass
class Metrics:
    days: list[DayPoint]
    questions_today: int
    fallback_rate: float | None  # over the window
    avg_latency_ms: int | None  # over the window
    thumbs_up_rate: float | None  # over the window
    thumbs_down: int
    top_questions: list[tuple[str, int]]
    tool_usage: list[tuple[str, int]]
    open_unanswered: int
    needs_review: int
    recent_thumbs_down: list[dict[str, Any]]
    usage_today: dict[str, int]
    database_bytes: int | None
    database_limit_bytes: int = DB_LIMIT_BYTES
    window_days: int = 14
    notes: list[str] = field(default_factory=list)


async def metrics(
    session: AsyncSession,
    institution_id: uuid.UUID,
    today: date,
    utc_offset_hours: float,
    window_days: int = 14,
) -> Metrics:
    start = today - timedelta(days=window_days - 1)
    msg_day = local_day(Message.created_at, utc_offset_hours)
    in_inst = Conversation.institution_id == institution_id
    joined = (
        select().select_from(Message).join(Conversation, Message.conversation_id == Conversation.id)
    )

    per_day: dict[date, int] = {
        day: int(n)
        for day, n in await session.execute(
            joined.add_columns(msg_day, func.count())
            .where(in_inst, Message.role == "user", msg_day >= start)
            .group_by(msg_day)
        )
    }
    usage_rows = (
        await session.execute(
            select(UsageDaily).where(
                UsageDaily.institution_id == institution_id, UsageDaily.day >= start
            )
        )
    ).scalars()
    usage = {row.day: row for row in usage_rows}
    days = [
        DayPoint(
            day=d,
            questions=int(per_day.get(d, 0)),
            fallbacks=usage[d].fallbacks if d in usage else 0,
        )
        for d in (start + timedelta(days=i) for i in range(window_days))
    ]
    total_questions = sum(p.questions for p in days)
    total_fallbacks = sum(p.fallbacks for p in days)

    avg_latency = await session.scalar(
        joined.add_columns(func.avg(Message.latency_ms)).where(
            in_inst, Message.role == "assistant", msg_day >= start, Message.latency_ms.is_not(None)
        )
    )
    fb_day = local_day(Feedback.created_at, utc_offset_hours)
    feedback_joined = (
        select()
        .select_from(Feedback)
        .join(Message, Feedback.message_id == Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(in_inst, fb_day >= start)
    )
    up, down = (
        await session.execute(
            feedback_joined.add_columns(
                func.coalesce(func.sum(cast(Feedback.rating == 1, Integer)), 0),
                func.coalesce(func.sum(cast(Feedback.rating == -1, Integer)), 0),
            )
        )
    ).one()
    normalized = func.lower(func.btrim(Message.content))
    top_questions = [
        (str(q), int(n))
        for q, n in (
            await session.execute(
                joined.add_columns(normalized, func.count().label("n"))
                .where(in_inst, Message.role == "user", msg_day >= start)
                .group_by(normalized)
                .order_by(text("n desc"), normalized)
                .limit(10)
            )
        )
    ]
    tool_usage = [
        (t or "none", int(n))
        for t, n in await session.execute(
            joined.add_columns(Message.tool_used, func.count().label("n"))
            .where(in_inst, Message.role == "assistant", msg_day >= start)
            .group_by(Message.tool_used)
            .order_by(text("n desc"), Message.tool_used)
        )
    ]
    recent_down = [
        {"message_id": str(m_id), "answer": content[:300], "comment": comment, "at": at.isoformat()}
        for m_id, content, comment, at in (
            await session.execute(
                feedback_joined.add_columns(
                    Message.id, Message.content, Feedback.comment, Feedback.created_at
                )
                .where(Feedback.rating == -1)
                .order_by(Feedback.created_at.desc())
                .limit(5)
            )
        )
    ]
    open_unanswered = await session.scalar(
        select(func.count()).where(
            UnansweredQuery.institution_id == institution_id, UnansweredQuery.status == "open"
        )
    )
    review = await needs_review(session, institution_id, today)
    usage_today = usage.get(today)
    try:
        db_bytes = int(
            await session.scalar(text("select pg_database_size(current_database())")) or 0
        )
    except Exception:  # pragma: no cover - permissions vary by host
        db_bytes = None
    rated = int(up) + int(down)
    return Metrics(
        days=days,
        questions_today=days[-1].questions,
        fallback_rate=(total_fallbacks / total_questions) if total_questions else None,
        avg_latency_ms=int(avg_latency) if avg_latency is not None else None,
        thumbs_up_rate=(int(up) / rated) if rated else None,
        thumbs_down=int(down),
        top_questions=top_questions,
        tool_usage=tool_usage,
        open_unanswered=int(open_unanswered or 0),
        needs_review=len(review),
        recent_thumbs_down=recent_down,
        usage_today={
            "llm_calls": usage_today.llm_calls if usage_today else 0,
            "embed_calls": usage_today.embed_calls if usage_today else 0,
            "cache_hits": usage_today.cache_hits if usage_today else 0,
            "fallbacks": usage_today.fallbacks if usage_today else 0,
        },
        database_bytes=db_bytes,
        window_days=window_days,
    )


# --- needs review (DATA-6) -------------------------------------------------------------------


@dataclass
class ReviewItem:
    kind: Literal["kb", "document"]
    id: uuid.UUID
    title: str
    category: str
    expires_at: date
    expired: bool
    department_id: uuid.UUID | None
    office_id: uuid.UUID | None
    owner_name: str | None


async def needs_review(
    session: AsyncSession, institution_id: uuid.UUID, today: date
) -> list[ReviewItem]:
    """Approved content that has expired or expires within 14 days, soonest first."""
    horizon = today + timedelta(days=REVIEW_WINDOW_DAYS)
    items: list[ReviewItem] = []
    models: tuple[tuple[Literal["kb", "document"], type[KbEntry] | type[Document]], ...] = (
        ("kb", KbEntry),
        ("document", Document),
    )
    for kind, model in models:
        rows = (
            await session.execute(
                select(model).where(
                    model.institution_id == institution_id,
                    model.status == "approved",
                    model.expires_at.is_not(None),
                    model.expires_at <= horizon,
                )
            )
        ).scalars()
        for row in typed(list[KbEntry | Document], list(rows)):
            assert row.expires_at is not None
            items.append(
                ReviewItem(
                    kind=kind,
                    id=row.id,
                    title=row.title,
                    category=row.category,
                    expires_at=row.expires_at,
                    expired=row.expires_at < today,
                    department_id=row.department_id,
                    office_id=row.office_id,
                    owner_name=row.owner_name,
                )
            )
    return sorted(items, key=lambda item: (item.expires_at, item.title))


# --- unanswered questions (DATA-7) ---------------------------------------------------------


@dataclass
class UnansweredGroup:
    id: uuid.UUID  # the newest row; actions apply to every open row with the same text
    query: str
    count: int
    last_seen: datetime
    reason: str | None


def _norm(column: Any) -> ColumnElement[str]:
    return func.lower(func.btrim(column))


async def unanswered_groups(
    session: AsyncSession, institution_id: uuid.UUID, status: str = "open", limit: int = 200
) -> list[UnansweredGroup]:
    rows = (
        await session.execute(
            select(UnansweredQuery)
            .where(
                UnansweredQuery.institution_id == institution_id, UnansweredQuery.status == status
            )
            .order_by(UnansweredQuery.created_at.desc())
            .limit(2000)
        )
    ).scalars()
    groups: dict[str, UnansweredGroup] = {}
    for row in rows:
        key = row.query.strip().lower()
        group = groups.get(key)
        if group is None:
            groups[key] = UnansweredGroup(row.id, row.query, 1, row.created_at, row.reason)
        else:
            group.count += 1
    ordered = sorted(groups.values(), key=lambda g: (-g.count, -g.last_seen.timestamp()))
    return ordered[:limit]


async def same_question_rows(
    session: AsyncSession, institution_id: uuid.UUID, row_id: uuid.UUID
) -> list[UnansweredQuery]:
    """The open rows with the same question text as `row_id`."""
    row = await session.get(UnansweredQuery, row_id)
    if row is None or row.institution_id != institution_id:
        return []
    return list(
        (
            await session.execute(
                select(UnansweredQuery).where(
                    UnansweredQuery.institution_id == institution_id,
                    UnansweredQuery.status == row.status,
                    _norm(UnansweredQuery.query) == row.query.strip().lower(),
                )
            )
        ).scalars()
    )


# --- approval diff (DATA-4) ----------------------------------------------------------------

DIFF_FIELDS = {
    "kb_entries": ("title", "question", "answer", "category", "language", "owner_name",
                   "department_id", "office_id", "last_verified", "expires_at", "source_url"),
    "documents": ("title", "category", "owner_name", "department_id", "office_id",
                  "last_verified", "expires_at", "source_url"),
}  # fmt: skip


def _plain(value: Any) -> Any:
    if isinstance(value, date | datetime | uuid.UUID):
        return str(value) if isinstance(value, uuid.UUID) else value.isoformat()
    return value


async def approval_diff(
    session: AsyncSession, table: str, row: KbEntry | Document
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(current approved version or None if never approved, proposed version).

    The current version is rebuilt from the audit log: the `old` value of the first change to
    each field since the last approval (no snapshot column needed)."""
    proposed = {name: _plain(getattr(row, name)) for name in DIFF_FIELDS[table]}
    if table == "documents":
        proposed["content"] = row.content[:2000] if isinstance(row, Document) else None
    audits = list(
        (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.table_name == table, AuditLog.row_id == row.id)
                .order_by(AuditLog.created_at)
            )
        ).scalars()
    )
    last_approval = max((i for i, a in enumerate(audits) if a.action == "approve"), default=None)
    if last_approval is None:
        return None, proposed
    current = dict(proposed)
    seen: set[str] = set()
    for entry in audits[last_approval + 1 :]:
        for name, change in (entry.diff or {}).items():
            if (
                name in current
                and name not in seen
                and isinstance(change, dict)
                and "old" in change
            ):
                current[name] = change["old"]
                seen.add(name)
    return current, proposed
