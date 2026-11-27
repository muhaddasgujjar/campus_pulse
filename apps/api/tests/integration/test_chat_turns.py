"""Chat turns end to end over the real seed rows (CHAT-1 to CHAT-9), with in-process stores,
the fake embedder and FakeLLM. Events are collected instead of sent over a socket."""

import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.cache import InMemoryResponseCache
from app.db.models import KbEntry, Message
from app.services.chat import ChatServices, replay_missed, run_turn, token_chunks
from app.services.embeddings import FakeEmbedder
from app.services.ingestion import index_entry
from app.services.llm import FakeLLM, LLMRouter
from app.services.ratelimit import MemoryRateLimiter
from app.services.seeding import load_seed_dir
from app.services.session_memory import MemorySessionMemory
from tests.conftest import make_settings

pytestmark = pytest.mark.integration

SEED_DIR = Path(__file__).resolve().parents[4] / "seed" / "lgu"


class Events:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    async def __call__(self, event: dict[str, Any]) -> None:
        json.dumps(event)  # every event must be JSON serialisable
        self.items.append(event)

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [e for e in self.items if e["type"] == kind]

    def text(self) -> str:
        return "".join(e["text"] for e in self.of("token"))


@pytest.fixture
async def seeded(db_session: AsyncSession) -> FakeEmbedder:
    embedder = FakeEmbedder()

    async def on_entry(entry: KbEntry) -> None:
        await index_entry(db_session, entry, embedder)

    await load_seed_dir(db_session, SEED_DIR, on_kb_entry=on_entry)
    return embedder


def make_services(
    db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM | None = None, **settings: Any
) -> ChatServices:
    # Sessions bound to the test's connection: their transactions become savepoints of the
    # test's outer transaction, which is rolled back afterwards.
    maker = async_sessionmaker(
        bind=db_session.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    config = make_settings(**settings)
    return ChatServices(
        settings=config,
        sessionmaker=maker,
        llm=LLMRouter([llm]) if llm is not None else None,
        embedder=embedder,
        cache=InMemoryResponseCache(ttl_seconds=3600),
        rate_limiter=MemoryRateLimiter(100, 600),
        memory=MemorySessionMemory(86400),
    )


async def turn(services: ChatServices, text: str, conversation_id: Any = None) -> Events:
    events = Events()
    await run_turn(
        services, events, client_key="1.2.3.4", conversation_id=conversation_id, text=text
    )
    return events


def test_token_chunks_join_back_to_the_same_text() -> None:
    text = "Exam Office: phone 042-37181828;\nhours Monday to Friday, 08:00 to 16:00"
    chunks = token_chunks(text)
    assert "".join(chunks) == text and len(chunks) > 1
    assert token_chunks("") == []


async def test_a_turn_streams_ack_status_sources_tokens_and_final(
    db_session: AsyncSession, seeded: FakeEmbedder
) -> None:
    services = make_services(db_session, seeded)
    events = await turn(services, "What are the fees for BSCS?")
    kinds = [e["type"] for e in events.items]
    assert kinds[0] == "ack" and kinds[-1] == "final"
    assert kinds.index("status") < kinds.index("sources") < kinds.index("token")
    assert events.of("status")[0]["stage"] == "searching"
    assert "Rs 7,744 per credit hour" in events.text()
    assert events.of("sources")[0]["items"][0]["title"].startswith("LGU website, Fee Structure")
    final = events.of("final")[0]
    assert (final["fallback"], final["cache_hit"], final["office"]) == (False, False, None)
    stored = (
        await db_session.execute(select(Message).where(Message.role == "assistant"))
    ).scalar_one()
    assert str(stored.id) == final["message_id"] and stored.content == events.text()
    assert stored.tool_used == "get_fee" and stored.sources[0]["office"] is None


async def test_user_text_is_stored_and_remembered_redacted(
    db_session: AsyncSession, seeded: FakeEmbedder
) -> None:
    services = make_services(db_session, seeded)
    events = await turn(services, "My CNIC is 35202-1234567-1. What are the fees for BSCS?")
    question = (
        await db_session.execute(select(Message).where(Message.role == "user"))
    ).scalar_one()
    assert "35202-1234567-1" not in question.content
    memory = await services.memory.recent(events.of("ack")[0]["conversation_id"])
    assert len(memory) == 1 and "35202-1234567-1" not in memory[0].question


async def test_the_conversation_continues_and_unknown_ids_start_a_new_one(
    db_session: AsyncSession, seeded: FakeEmbedder
) -> None:
    services = make_services(db_session, seeded)
    first = await turn(services, "What are the fees for BSCS?")
    conversation_id = first.of("ack")[0]["conversation_id"]
    second = await turn(services, "Exam office phone number?", uuid.UUID(conversation_id))
    assert second.of("ack")[0]["conversation_id"] == conversation_id
    stranger = await turn(services, "Exam office phone number?", uuid.uuid4())
    assert stranger.of("ack")[0]["conversation_id"] != conversation_id


async def test_a_fallback_carries_the_office_for_the_fallback_card(
    db_session: AsyncSession, seeded: FakeEmbedder
) -> None:
    services = make_services(db_session, seeded)
    events = await turn(services, "Is there a swimming pool on campus?")
    final = events.of("final")[0]
    assert final["fallback"] is True
    assert final["office"]["name"] == "Admission Office"
    assert "0322-2757543" in final["office"]["phones"]
    assert events.of("sources")[0]["items"] == []


async def test_follow_ups_reach_the_planner_with_history_and_skip_the_cache(
    db_session: AsyncSession, seeded: FakeEmbedder
) -> None:
    bscs = {"intent": "structured", "tool": "get_fee", "args": {"program_group": "BSCS"}}
    bba = {"intent": "structured", "tool": "get_fee", "args": {"program_group": "BBA"}}
    llm = FakeLLM([json.dumps(bscs), json.dumps(bba)])
    services = make_services(db_session, seeded, llm)
    first = await turn(services, "What are the fees for BSCS?")  # template: 0 LLM calls
    conversation_id = uuid.UUID(first.of("ack")[0]["conversation_id"])
    follow_up = await turn(services, "And for BBA?", conversation_id)
    assert "<history>" not in llm.calls[0][1]  # first turn: nothing to remember yet
    planner_prompt = llm.calls[1][1]
    assert "<history>" in planner_prompt and "What are the fees for BSCS?" in planner_prompt
    assert "Rs 7,392 per credit hour" in follow_up.text()
    again = await turn(services, "And for BBA?", conversation_id)
    assert again.of("final")[0]["cache_hit"] is False  # follow-ups are never cached


async def test_resume_replays_answers_after_the_last_seen_message(
    db_session: AsyncSession, seeded: FakeEmbedder
) -> None:
    services = make_services(db_session, seeded)
    first = await turn(services, "What are the fees for BSCS?")
    conversation_id = uuid.UUID(first.of("ack")[0]["conversation_id"])
    seen = uuid.UUID(first.of("final")[0]["message_id"])
    missed = await turn(services, "Exam office phone number?", conversation_id)
    replayed = Events()
    await replay_missed(services, replayed, conversation_id=conversation_id, last_message_id=seen)
    finals = replayed.of("final")
    assert [f["message_id"] for f in finals] == [missed.of("final")[0]["message_id"]]
    assert finals[0]["replay"] is True and replayed.text() == missed.text()
    nothing = Events()
    await replay_missed(
        services,
        nothing,
        conversation_id=conversation_id,
        last_message_id=uuid.UUID(finals[0]["message_id"]),
    )
    assert nothing.items == []


async def test_the_answer_is_stored_even_if_the_client_has_gone(
    db_session: AsyncSession, seeded: FakeEmbedder
) -> None:
    services = make_services(db_session, seeded)

    async def gone(event: dict[str, Any]) -> None:
        return None  # like Sender after a disconnect: events are dropped

    await run_turn(
        services, gone, client_key="ip", conversation_id=None, text="Exam office phone number?"
    )
    roles = (await db_session.execute(select(Message.role))).scalars().all()
    assert sorted(roles) == ["assistant", "user"]


async def test_history_order_survives_one_transaction(
    db_session: AsyncSession, seeded: FakeEmbedder
) -> None:
    """clock_timestamp(): the answer sorts after its question even in one transaction."""
    from app.db.repositories import conversations as repo

    services = make_services(db_session, seeded)
    events = await turn(services, "Exam office phone number?")
    conversation_id = uuid.UUID(events.of("ack")[0]["conversation_id"])
    messages = await repo.list_messages(db_session, conversation_id)
    assert [m.role for m in messages] == ["user", "assistant"]


def test_today_is_the_institution_date_not_the_server_date() -> None:
    services = ChatServices(
        settings=make_settings(institution_utc_offset_hours=5),
        sessionmaker=None,
        llm=None,
        embedder=None,
        cache=InMemoryResponseCache(0),
        rate_limiter=MemoryRateLimiter(1, 1),
        memory=MemorySessionMemory(60),
    )
    # 20:00 UTC on 4 Oct is 01:00 on 5 Oct in Lahore (UTC+5): the deadline day is the 5th.
    assert services.today(datetime(2026, 10, 4, 20, 0, tzinfo=UTC)) == date(2026, 10, 5)
