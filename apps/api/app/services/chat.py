"""One chat turn over the WebSocket (CHAT-1 to CHAT-9, Architectural.md Section 8).

A turn: rate limit, store the redacted question and `ack` it, run the agent while sending
`status` events, store the answer, then send `sources`, `token` chunks and `final`.

The answer is streamed only after the agent's post-check (rules 1 and 2): an LLM answer can
be replaced by a template when it contains a number that is not in the data, so its raw
tokens are never sent. `status` events cover the waiting time instead.

A turn always runs to the end and commits, even if the socket closes midway, so the client
can fetch the answer with `resume` after reconnecting (CHAT-9).
"""

import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any, Literal

from redis.asyncio import Redis
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agent.cache import InMemoryResponseCache, RedisResponseCache, ResponseCache
from app.agent.service import AgentAnswer, answer_question, make_deps
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.redact import redact
from app.db.models import Message
from app.db.repositories import conversations as repo
from app.db.session import create_sessionmaker
from app.services.embeddings import Embedder, build_embedder
from app.services.llm import LLMRouter, build_llm
from app.services.ratelimit import MemoryRateLimiter, RateLimiter, RedisRateLimiter
from app.services.session_memory import (
    MemorySessionMemory,
    RedisSessionMemory,
    SessionMemory,
    Turn,
    append_turn,
)

log = get_logger("chat")

Emit = Callable[[dict[str, Any]], Awaitable[None]]
ErrorCode = Literal[
    "rate_limited", "busy", "provider_down", "internal", "invalid_message", "unavailable"
]
WORDS_PER_TOKEN_EVENT = 3


@dataclass
class ChatServices:
    """Built once at startup (app.state.chat). Every member works without Redis."""

    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession] | None
    llm: LLMRouter | None
    embedder: Embedder | None
    cache: ResponseCache
    rate_limiter: RateLimiter
    memory: SessionMemory

    def today(self, now: datetime | None = None) -> date:
        offset = timezone(timedelta(hours=self.settings.institution_utc_offset_hours))
        return (now or datetime.now(UTC)).astimezone(offset).date()


def build_chat_services(
    settings: Settings, engine: AsyncEngine | None, redis: Redis | None
) -> ChatServices:
    limiter = MemoryRateLimiter(
        settings.chat_rate_limit_messages, settings.chat_rate_limit_window_seconds
    )
    memory = MemorySessionMemory(settings.session_memory_ttl_seconds)
    cache: ResponseCache = InMemoryResponseCache(settings.response_cache_ttl_seconds)
    rate_limiter: RateLimiter = limiter
    session_memory: SessionMemory = memory
    if redis is not None:
        cache = RedisResponseCache(redis, settings.response_cache_ttl_seconds)
        rate_limiter = RedisRateLimiter(
            redis,
            settings.chat_rate_limit_messages,
            settings.chat_rate_limit_window_seconds,
            limiter,
        )
        session_memory = RedisSessionMemory(redis, settings.session_memory_ttl_seconds, memory)
    llm = build_llm(settings, redis)
    return ChatServices(
        settings=settings,
        sessionmaker=create_sessionmaker(engine) if engine is not None else None,
        llm=llm if llm.available else None,
        embedder=build_embedder(settings),
        cache=cache,
        rate_limiter=rate_limiter,
        memory=session_memory,
    )


# --- events ------------------------------------------------------------------------------------


def error_event(code: ErrorCode, message: str, **extra: Any) -> dict[str, Any]:
    return {"type": "error", "code": code, "message": message, **extra}


def token_chunks(text: str, words: int = WORDS_PER_TOKEN_EVENT) -> list[str]:
    """Split an answer into small pieces that join back to exactly the same text."""
    pieces = re.findall(r"\s*\S+\s*", text) or ([text] if text else [])
    return ["".join(pieces[i : i + words]) for i in range(0, len(pieces), words)]


def _office(contact: dict[str, Any] | None) -> dict[str, Any] | None:
    """The fallback card's office: name, tap-to-call phones, email, hours (DESIGN.md 4)."""
    if not contact:
        return None
    return {
        "name": contact.get("name"),
        "phones": list(contact.get("phones") or []),
        "email": contact.get("email"),
        "hours": contact.get("hours"),
    }


async def _send_answer(
    emit: Emit,
    *,
    message_id: uuid.UUID,
    conversation_id: uuid.UUID,
    text: str,
    sources: list[dict[str, Any]],
    fallback: bool,
    cache_hit: bool,
    office: dict[str, Any] | None,
    replay: bool = False,
) -> None:
    await emit({"type": "sources", "message_id": str(message_id), "items": sources})
    for piece in token_chunks(text):
        await emit({"type": "token", "message_id": str(message_id), "text": piece})
    await emit(
        {
            "type": "final",
            "message_id": str(message_id),
            "conversation_id": str(conversation_id),
            "fallback": fallback,
            "cache_hit": cache_hit,
            "office": office,
            "replay": replay,
        }
    )


# --- turn --------------------------------------------------------------------------------------


async def run_turn(
    services: ChatServices,
    emit: Emit,
    *,
    client_key: str,
    conversation_id: uuid.UUID | None,
    text: str,
    modality: Literal["text", "voice"] = "text",
) -> None:
    settings = services.settings
    decision = await services.rate_limiter.hit(f"chat:{client_key}")
    if not decision.allowed:
        await emit(
            error_event(
                "rate_limited",
                "You're sending messages fast. Please wait a moment.",
                retry_after=decision.retry_after_seconds,
            )
        )
        return
    text = text.strip()
    if not text or len(text) > settings.chat_max_message_chars:
        await emit(
            error_event(
                "invalid_message",
                f"Please send a message between 1 and {settings.chat_max_message_chars} "
                "characters.",
            )
        )
        return
    if services.sessionmaker is None:
        await emit(error_event("unavailable", "The assistant is unavailable right now."))
        return
    try:
        await _answer(services, emit, conversation_id, text, modality)
    except (OperationalError, DBAPIError, OSError) as exc:
        log.error("chat_database_unavailable", error=type(exc).__name__)
        await emit(error_event("unavailable", "The assistant is unavailable right now."))
    except Exception:
        log.exception("chat_turn_failed")
        await emit(error_event("internal", "Something went wrong. Please try again."))


async def _answer(
    services: ChatServices,
    emit: Emit,
    conversation_id: uuid.UUID | None,
    text: str,
    modality: Literal["text", "voice"],
) -> None:
    assert services.sessionmaker is not None
    redacted = redact(text)  # stored, logged and remembered only in redacted form (SEC-3)
    async with services.sessionmaker() as session:
        async with session.begin():
            deps = await make_deps(
                session,
                services.settings,
                llm=services.llm,
                embedder=services.embedder,
                cache=services.cache,
                today=services.today(),
            )
            conversation = await repo.get_or_create_conversation(
                session, deps.institution_id, conversation_id
            )
            question = await repo.add_message(
                session, conversation.id, "user", redacted, modality=modality
            )
        await emit(
            {
                "type": "ack",
                "message_id": str(question.id),
                "conversation_id": str(conversation.id),
            }
        )
        history = await services.memory.recent(str(conversation.id))

        async def on_status(stage: str) -> None:
            await emit({"type": "status", "stage": stage})

        async with session.begin():
            answer = await answer_question(
                deps,
                text,
                modality=modality,
                conversation_id=conversation.id,
                history=history,
                on_status=on_status,
            )
            sources = [s.as_dict() for s in answer.sources]
            reply = await _store_answer(session, conversation.id, answer, sources)
    await services.memory.save(
        str(conversation.id),
        append_turn(history, Turn(redacted, answer.answer), services.settings.session_memory_turns),
    )
    await _send_answer(
        emit,
        message_id=reply.id,
        conversation_id=conversation.id,
        text=answer.answer,
        sources=sources,
        fallback=answer.fallback,
        cache_hit=answer.cache_hit,
        office=_office(answer.office_contact),
    )


async def _store_answer(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    answer: AgentAnswer,
    sources: list[dict[str, Any]],
) -> Message:
    return await repo.add_message(
        session,
        conversation_id,
        "assistant",
        answer.answer,
        sources=sources,
        tool_used=answer.tool_used,
        cache_hit=answer.cache_hit,
        llm_calls=answer.llm_calls,
        latency_ms=answer.latency_ms,
        tokens_in=answer.tokens_in,
        tokens_out=answer.tokens_out,
    )


async def replay_missed(
    services: ChatServices,
    emit: Emit,
    *,
    conversation_id: uuid.UUID,
    last_message_id: uuid.UUID | None,
) -> None:
    """Send the answers stored after `last_message_id` (resume, CHAT-9)."""
    if services.sessionmaker is None:
        return
    async with services.sessionmaker() as session:
        missed: Sequence[Message] = await repo.assistant_messages_after(
            session, conversation_id, last_message_id
        )
    for message in missed:
        await _send_answer(
            emit,
            message_id=message.id,
            conversation_id=conversation_id,
            text=message.content,
            sources=list(message.sources or []),
            fallback=False,
            cache_hit=message.cache_hit,
            office=None,
            replay=True,
        )
