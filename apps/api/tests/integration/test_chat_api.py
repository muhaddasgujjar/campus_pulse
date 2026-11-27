"""Chat REST endpoints over the real seed rows: history (CHAT-1, CHAT-9), feedback (CHAT-4)
and starter questions in /api/config (CHAT-6)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback
from app.main import create_app
from app.services.chat import ChatServices
from app.services.embeddings import FakeEmbedder
from tests.conftest import make_settings, running_client
from tests.integration.test_chat_turns import Events, make_services, seeded, turn

pytestmark = pytest.mark.integration
__all__ = ["seeded"]  # fixture re-used from test_chat_turns


@pytest.fixture
def services(db_session: AsyncSession, seeded: FakeEmbedder) -> ChatServices:
    return make_services(db_session, seeded)


@pytest.fixture
async def api(services: ChatServices) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings())
    async with running_client(app) as client:
        app.state.chat = services  # bound to the test's rolled-back transaction
        yield client


async def answered(services: ChatServices) -> Events:
    return await turn(services, "What are the fees for BSCS?")


async def test_history_returns_question_and_answer_in_order(
    api: httpx.AsyncClient, services: ChatServices
) -> None:
    events = await answered(services)
    conversation_id = events.of("ack")[0]["conversation_id"]
    response = await api.get(f"/api/conversations/{conversation_id}/messages")
    assert response.status_code == 200
    body = response.json()
    assert [m["role"] for m in body] == ["user", "assistant"]
    assert body[0]["content"] == "What are the fees for BSCS?"
    assert body[1]["id"] == events.of("final")[0]["message_id"]
    assert body[1]["sources"][0]["title"].startswith("LGU website, Fee Structure")


async def test_history_of_an_unknown_conversation_is_404(api: httpx.AsyncClient) -> None:
    response = await api.get(f"/api/conversations/{uuid.uuid4()}/messages")
    assert response.status_code == 404


async def test_feedback_is_stored_redacted_and_a_second_vote_replaces_it(
    api: httpx.AsyncClient, services: ChatServices, db_session: AsyncSession
) -> None:
    events = await answered(services)
    message_id = events.of("final")[0]["message_id"]
    first = await api.post(
        "/api/feedback",
        json={
            "message_id": message_id,
            "rating": -1,
            "reason": "outdated",
            "comment": "call me on 0300-1234567",
        },
    )
    assert first.status_code == 204
    second = await api.post("/api/feedback", json={"message_id": message_id, "rating": 1})
    assert second.status_code == 204
    rows = (await db_session.execute(select(Feedback))).scalars().all()
    assert len(rows) == 1 and rows[0].rating == 1 and rows[0].comment is None


async def test_feedback_comment_is_redacted(
    api: httpx.AsyncClient, services: ChatServices, db_session: AsyncSession
) -> None:
    events = await answered(services)
    await api.post(
        "/api/feedback",
        json={
            "message_id": events.of("final")[0]["message_id"],
            "rating": -1,
            "reason": "wrong",
            "comment": "call me on 0300-1234567",
        },
    )
    row = (await db_session.execute(select(Feedback))).scalar_one()
    assert row.comment is not None and row.comment.startswith("The answer is wrong: ")
    assert "0300-1234567" not in row.comment


@pytest.mark.parametrize(
    "body",
    [
        {"rating": 2},
        {"rating": 1, "reason": "rude"},
        {"rating": 1, "comment": "x" * 501},
    ],
)
async def test_invalid_feedback_is_rejected(
    api: httpx.AsyncClient, services: ChatServices, body: dict[str, object]
) -> None:
    events = await answered(services)
    response = await api.post(
        "/api/feedback", json={"message_id": events.of("final")[0]["message_id"], **body}
    )
    assert response.status_code == 422


async def test_feedback_only_on_answers(api: httpx.AsyncClient, services: ChatServices) -> None:
    events = await answered(services)
    question_id = events.of("ack")[0]["message_id"]
    response = await api.post("/api/feedback", json={"message_id": question_id, "rating": 1})
    assert response.status_code == 404


async def test_config_lists_the_seeded_starter_questions(api: httpx.AsyncClient) -> None:
    body = (await api.get("/api/config")).json()
    assert body["institution_name"] == "Lahore Garrison University"
    assert body["short_name"] == "LGU"
    assert "What are the fees for BSCS?" in body["starter_questions"]
    assert len(body["starter_questions"]) <= 6


async def test_history_needs_a_database() -> None:
    async with running_client(create_app(make_settings())) as client:
        response = await client.get(f"/api/conversations/{uuid.uuid4()}/messages")
    assert response.status_code == 503
