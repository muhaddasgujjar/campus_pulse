"""Chat REST endpoints (Architectural.md Section 8): conversation history (CHAT-1, CHAT-9) and
feedback (CHAT-4). Anonymous until M5: a conversation id (random UUID, never listed) is what
allows reading its history."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redact import redact
from app.db.models import Conversation, Feedback, Message
from app.db.repositories import conversations as repo
from app.services.chat import ChatServices

router = APIRouter(prefix="/api", tags=["chat"])

FEEDBACK_REASONS = {
    "wrong": "The answer is wrong",
    "outdated": "The information is outdated",
    "not_helpful": "It did not answer my question",
}


def chat_services(request: Request) -> ChatServices:
    services: ChatServices = request.app.state.chat
    return services


async def db_session(
    services: Annotated[ChatServices, Depends(chat_services)],
) -> AsyncIterator[AsyncSession]:
    if services.sessionmaker is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database not configured")
    async with services.sessionmaker() as session:
        yield session


class MessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    modality: Literal["text", "voice"]
    content: str
    sources: list[dict[str, Any]]
    created_at: datetime


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def conversation_messages(
    conversation_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(db_session)],
) -> list[MessageOut]:
    """The latest 100 messages, oldest first (reload and reconnect, CHAT-9)."""
    if await session.get(Conversation, conversation_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
    rows = await repo.list_messages(session, conversation_id)
    return [
        MessageOut(
            id=m.id,
            role=m.role,  # check constraint: user | assistant
            modality=m.modality,  # check constraint: text | voice
            content=m.content,
            sources=list(m.sources or []),
            created_at=m.created_at,
        )
        for m in rows
    ]


class FeedbackIn(BaseModel):
    message_id: uuid.UUID
    rating: Literal[1, -1]
    reason: Literal["wrong", "outdated", "not_helpful"] | None = None
    comment: str | None = Field(default=None, max_length=500)


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def give_feedback(
    body: FeedbackIn,
    request: Request,
    services: Annotated[ChatServices, Depends(chat_services)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> Response:
    """Thumbs up or down on an answer (CHAT-4). A second vote on the same answer replaces the
    first. The comment is redacted before it is stored (SEC-3)."""
    client = request.client.host if request.client else "unknown"
    if not (await services.rate_limiter.hit(f"feedback:{client}")).allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many requests")
    parts = [FEEDBACK_REASONS[body.reason]] if body.reason else []
    if body.comment and body.comment.strip():
        parts.append(redact(body.comment.strip()))
    comment = ": ".join(parts) or None
    async with session.begin():
        message = await session.get(Message, body.message_id)
        if message is None or message.role != "assistant":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "answer not found")
        existing = (
            await session.execute(select(Feedback).where(Feedback.message_id == message.id))
        ).scalar_one_or_none()
        if existing is None:
            session.add(Feedback(message_id=message.id, rating=body.rating, comment=comment))
        else:
            existing.rating, existing.comment = body.rating, comment
    return Response(status_code=status.HTTP_204_NO_CONTENT)
