"""Shared tool types (Architectural.md Section 6): every tool returns
{data, sources[], last_verified, owner}. Arguments are typed Pydantic models, so the planner
LLM only ever chooses a tool and fills fields (D10: the LLM never writes SQL)."""

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class Source:
    """One citation shown as a source chip (CHAT-3)."""

    title: str
    office: str | None = None
    url: str | None = None
    last_verified: date | None = None
    expired: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Source":
        verified = data.get("last_verified")
        return cls(
            title=data["title"],
            office=data.get("office"),
            url=data.get("url"),
            last_verified=date.fromisoformat(verified) if verified else None,
            expired=bool(data.get("expired")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "office": self.office,
            "url": self.url,
            "last_verified": self.last_verified.isoformat() if self.last_verified else None,
            "expired": self.expired,
        }


@dataclass
class ToolResult:
    tool: str
    data: list[dict[str, Any]] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    last_verified: date | None = None
    owner: str | None = None
    score: float | None = None  # retrieval tools only

    @property
    def found(self) -> bool:
        return bool(self.data)


@dataclass(frozen=True)
class ToolContext:
    session: AsyncSession
    institution_id: uuid.UUID
    today: date


def oldest(dates: list[date | None]) -> date | None:
    """The answer is only as fresh as its oldest fact."""
    known = [d for d in dates if d is not None]
    return min(known) if known else None


def dedupe_sources(sources: list[Source]) -> list[Source]:
    seen: set[tuple[str, str | None]] = set()
    unique = []
    for source in sources:
        key = (source.title, source.office)
        if key not in seen:
            seen.add(key)
            unique.append(source)
    return unique
