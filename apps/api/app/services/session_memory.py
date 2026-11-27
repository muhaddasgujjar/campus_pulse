"""Short-term session memory (CHAT-5, Architectural.md Section 10): the last N turns of a
conversation, text only, for 24 hours. Used to resolve follow-up questions ("And semester 2?")
in the planner. Redis: one GET to read and one SET EX to write (2 commands per turn). If Redis
fails, an in-process store is used, so the chat keeps working without memory across restarts.

User text is stored redacted (SEC-3). Postgres `messages` stays the durable log.
"""

import json
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal, Protocol

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.core.redis import REDIS_ERRORS

log = get_logger("session_memory")


@dataclass(frozen=True)
class Turn:
    question: str  # redacted user text
    answer: str


class SessionMemory(Protocol):
    async def recent(self, conversation_id: str) -> list[Turn]: ...

    async def save(self, conversation_id: str, turns: list[Turn]) -> None: ...


def append_turn(turns: list[Turn], turn: Turn, max_turns: int) -> list[Turn]:
    return [*turns, turn][-max_turns:] if max_turns else []


class MemorySessionMemory:
    def __init__(
        self,
        ttl_seconds: int,
        clock: Callable[[], float] = time.monotonic,
        max_sessions: int = 5000,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._max = max_sessions
        self._items: OrderedDict[str, tuple[float, list[Turn]]] = OrderedDict()

    async def recent(self, conversation_id: str) -> list[Turn]:
        item = self._items.get(conversation_id)
        if item is None or self._clock() - item[0] > self._ttl:
            self._items.pop(conversation_id, None)
            return []
        return list(item[1])

    async def save(self, conversation_id: str, turns: list[Turn]) -> None:
        self._items[conversation_id] = (self._clock(), list(turns))
        self._items.move_to_end(conversation_id)
        if len(self._items) > self._max:
            self._items.popitem(last=False)


class RedisSessionMemory:
    def __init__(self, redis: Redis, ttl_seconds: int, fallback: MemorySessionMemory) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._fallback = fallback

    @staticmethod
    def _key(conversation_id: str) -> str:
        return f"sess:{conversation_id}"

    def _warn(self, op: Literal["get", "set"], exc: BaseException) -> None:
        log.warning("session_redis_unavailable", op=op, error=type(exc).__name__)

    async def recent(self, conversation_id: str) -> list[Turn]:
        try:
            raw = await self._redis.get(self._key(conversation_id))
        except REDIS_ERRORS as exc:
            self._warn("get", exc)
            return await self._fallback.recent(conversation_id)
        if raw is None:
            return []
        try:
            return [Turn(**item) for item in json.loads(raw)]
        except (ValueError, TypeError):
            return []

    async def save(self, conversation_id: str, turns: list[Turn]) -> None:
        payload = json.dumps([asdict(t) for t in turns], ensure_ascii=False)
        try:
            await self._redis.set(self._key(conversation_id), payload, ex=self._ttl)
        except REDIS_ERRORS as exc:
            self._warn("set", exc)
            await self._fallback.save(conversation_id, turns)
