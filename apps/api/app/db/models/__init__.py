"""ORM models (Architectural.md Section 5). Every model is imported here so that
`Base.metadata` is complete for Alembic autogenerate."""

from app.db.models.base import Base
from app.db.models.conversations import Conversation, Feedback, Message, UnansweredQuery
from app.db.models.knowledge import CONTENT_STATUSES, EMBEDDING_DIM, Chunk, Document, KbEntry
from app.db.models.operations import AuditLog, UsageDaily
from app.db.models.structured import Faculty, Fee, KeyDate, LiveSource, Office, Timetable
from app.db.models.tenancy import Department, Institution, Profile

__all__ = [
    "CONTENT_STATUSES",
    "EMBEDDING_DIM",
    "AuditLog",
    "Base",
    "Chunk",
    "Conversation",
    "Department",
    "Document",
    "Faculty",
    "Fee",
    "Feedback",
    "Institution",
    "KbEntry",
    "KeyDate",
    "LiveSource",
    "Message",
    "Office",
    "Profile",
    "Timetable",
    "UnansweredQuery",
    "UsageDaily",
]
