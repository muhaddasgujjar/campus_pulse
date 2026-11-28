"""WebSocket protocol without a database: origin check, ping, validation, rate limit and the
'unavailable' error (CHAT-2, CHAT-7, SEC-2). Full turns are in tests/integration."""

import uuid
from typing import Any

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.auth import TokenVerifier
from app.main import create_app
from tests.conftest import make_settings

ORIGIN = {"origin": "http://localhost:3000"}


def client(**settings: Any) -> TestClient:
    return TestClient(create_app(make_settings(**settings)))


def test_ping_is_answered_with_pong() -> None:
    with client() as http, http.websocket_connect("/ws/chat", headers=ORIGIN) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_other_origins_are_refused() -> None:
    evil = {"origin": "https://evil.example"}
    with (
        client() as http,
        pytest.raises(WebSocketDisconnect) as refused,
        http.websocket_connect("/ws/chat", headers=evil) as ws,
    ):
        ws.receive_json()
    assert refused.value.code == 1008


def test_any_origin_is_allowed_when_cors_origins_is_unset() -> None:
    with client(cors_origins=[]) as http, http.websocket_connect("/ws/chat") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


@pytest.mark.parametrize(
    "frame",
    ["not json", '{"type": "shout"}', '{"type": "user_message"}', "x" * 9000],
)
def test_bad_frames_get_an_error_and_the_socket_stays_open(frame: str) -> None:
    with client() as http, http.websocket_connect("/ws/chat", headers=ORIGIN) as ws:
        ws.send_text(frame)
        assert ws.receive_json()["code"] == "invalid_message"
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_a_bad_auth_token_is_reported_and_the_chat_stays_anonymous() -> None:
    with client() as http, http.websocket_connect("/ws/chat", headers=ORIGIN) as ws:
        ws.send_json({"type": "auth", "token": "anything"})
        assert ws.receive_json()["code"] == "auth_failed"
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_a_valid_auth_token_is_accepted_quietly() -> None:
    secret = "test-only-secret-for-hs256-tokens-0123456789"
    settings = make_settings(dev_auth=True, supabase_jwt_secret=secret)
    token = TokenVerifier(settings).issue_dev_token(uuid.uuid4(), email=None, is_anonymous=True)
    with (
        TestClient(create_app(settings)) as http,
        http.websocket_connect("/ws/chat", headers=ORIGIN) as ws,
    ):
        ws.send_json({"type": "auth", "token": token})
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}  # no error event before the pong


def test_without_a_database_the_turn_reports_unavailable() -> None:
    with client() as http, http.websocket_connect("/ws/chat", headers=ORIGIN) as ws:
        ws.send_json({"type": "user_message", "text": "What are the fees for BSCS?"})
        assert ws.receive_json()["code"] == "unavailable"


def test_empty_and_too_long_messages_are_rejected() -> None:
    with (
        client(chat_max_message_chars=20) as http,
        http.websocket_connect("/ws/chat", headers=ORIGIN) as ws,
    ):
        ws.send_json({"type": "user_message", "text": "   "})
        assert ws.receive_json()["code"] == "invalid_message"
        ws.send_json({"type": "user_message", "text": "x" * 21})
        assert ws.receive_json()["code"] == "invalid_message"


def test_messages_over_the_rate_limit_are_refused() -> None:
    with (
        client(chat_rate_limit_messages=1) as http,
        http.websocket_connect("/ws/chat", headers=ORIGIN) as ws,
    ):
        ws.send_json({"type": "user_message", "text": "hello"})
        assert ws.receive_json()["code"] == "unavailable"  # counted, then no database
        ws.send_json({"type": "user_message", "text": "hello"})
        error = ws.receive_json()
        assert error["code"] == "rate_limited" and error["retry_after"] > 0
