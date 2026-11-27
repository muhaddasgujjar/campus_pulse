"""WebSocket `/ws/chat` (CHAT-2, CHAT-9, Architectural.md Section 8).

Client to server: `user_message`, `resume`, `ping`, and `auth` (accepted and ignored until
Supabase JWT verification in M5: everyone chats anonymously, rate-limited by IP).
Server to client: `ack`, `status`, `sources`, `token`, `final`, `error`, `pong`.

Browsers do not apply CORS to WebSockets, so the `Origin` header is checked against
CORS_ORIGINS: other sites cannot open a chat socket on a student's behalf.
"""

import json
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.core.logging import get_logger
from app.services.chat import ChatServices, error_event, replay_missed, run_turn

log = get_logger("ws")
router = APIRouter()

MAX_FRAME_CHARS = 8192


class UserMessage(BaseModel):
    type: Literal["user_message"]
    conversation_id: uuid.UUID | None = None
    text: str = Field(max_length=4000)  # the turn applies CHAT_MAX_MESSAGE_CHARS
    lang_hint: str | None = Field(default=None, max_length=16)
    modality: Literal["text", "voice"] = "text"


class Resume(BaseModel):
    type: Literal["resume"]
    conversation_id: uuid.UUID
    last_message_id: uuid.UUID | None = None


class Ping(BaseModel):
    type: Literal["ping"]


class Auth(BaseModel):
    type: Literal["auth"]
    token: str = Field(max_length=4096)


ClientMessage = TypeAdapter[UserMessage | Resume | Ping | Auth](
    Annotated[UserMessage | Resume | Ping | Auth, Field(discriminator="type")]
)


class Sender:
    """Sends events; after the client has gone, drops them quietly so the turn still
    finishes and commits (the client fetches the answer with `resume`)."""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self.closed = False

    async def __call__(self, event: dict[str, Any]) -> None:
        if self.closed:
            return
        try:
            await self._ws.send_json(event)
        except (WebSocketDisconnect, RuntimeError, OSError):
            self.closed = True


def _origin_allowed(websocket: WebSocket, allowed: list[str]) -> bool:
    if not allowed:  # CORS_ORIGINS unset: local development
        return True
    return websocket.headers.get("origin", "").rstrip("/") in {o.rstrip("/") for o in allowed}


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    services: ChatServices = websocket.app.state.chat
    if not _origin_allowed(websocket, services.settings.cors_origins):
        await websocket.close(code=1008)  # policy violation
        return
    await websocket.accept()
    send = Sender(websocket)
    client_key = websocket.client.host if websocket.client else "unknown"
    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > MAX_FRAME_CHARS:
                await send(error_event("invalid_message", "Message too long."))
                continue
            try:
                message = ClientMessage.validate_python(json.loads(raw))
            except (ValueError, ValidationError):
                await send(error_event("invalid_message", "Unrecognised message."))
                continue
            if isinstance(message, Ping):
                await send({"type": "pong"})
            elif isinstance(message, Auth):
                pass  # M5: verify the Supabase JWT here (AUTH-2). Anonymous until then.
            elif isinstance(message, Resume):
                await replay_missed(
                    services,
                    send,
                    conversation_id=message.conversation_id,
                    last_message_id=message.last_message_id,
                )
            else:
                await run_turn(
                    services,
                    send,
                    client_key=client_key,
                    conversation_id=message.conversation_id,
                    text=message.text,
                    modality=message.modality,
                )
    except WebSocketDisconnect:
        return
