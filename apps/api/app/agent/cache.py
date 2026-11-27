"""Response cache (COST-3): repeated questions cost no LLM call.

Key: normalized question, language, profile program, today's date and data_version. The data
version is the newest audit_log row (every content write records one, rule 7), so a staff edit
makes every old key unreachable and the change appears immediately, across processes.
`InMemoryResponseCache` backs local development, tests and eval; `RedisResponseCache` is
shared across workers and restarts. A Redis failure is a cache miss: the chat keeps working.
"""

import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Protocol

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.core.redis import REDIS_ERRORS

log = get_logger("cache")


def normalize_query(text: str) -> str:
    return " ".join(text.lower().strip(" ?!.").split())


def cache_key(
    normalized: str, language: str, program: str | None, data_version: str, today: date
) -> str:
    # today: "this date has passed" and upcoming-date answers change at midnight.
    raw = f"{data_version}|{today.isoformat()}|{language}|{(program or '').lower()}|{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class CachedAnswer:
    answer: str
    sources: list[dict[str, Any]]
    tool_used: str | None


class ResponseCache(Protocol):
    async def get(self, key: str) -> CachedAnswer | None: ...

    async def set(self, key: str, value: CachedAnswer) -> None: ...


class InMemoryResponseCache:
    def __init__(
        self,
        ttl_seconds: int,
        max_items: int = 2000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_items
        self._clock = clock
        self._items: OrderedDict[str, tuple[float, CachedAnswer]] = OrderedDict()

    async def get(self, key: str) -> CachedAnswer | None:
        item = self._items.get(key)
        if item is None:
            return None
        stored_at, value = item
        if self._ttl and self._clock() - stored_at > self._ttl:
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return value

    async def set(self, key: str, value: CachedAnswer) -> None:
        if self._ttl == 0:
            return
        self._items[key] = (self._clock(), value)
        self._items.move_to_end(key)
        if len(self._items) > self._max:
            self._items.popitem(last=False)


class RedisResponseCache:
    """One GET per lookup, one SET EX per store (2 Redis commands per turn at most)."""

    def __init__(self, redis: Redis, ttl_seconds: int, prefix: str = "cache:") -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._prefix = prefix

    async def get(self, key: str) -> CachedAnswer | None:
        try:
            raw = await self._redis.get(self._prefix + key)
        except REDIS_ERRORS as exc:
            log.warning("cache_redis_unavailable", op="get", error=type(exc).__name__)
            return None
        if raw is None:
            return None
        try:
            return CachedAnswer(**json.loads(raw))
        except (ValueError, TypeError):
            return None

    async def set(self, key: str, value: CachedAnswer) -> None:
        if self._ttl == 0:
            return
        try:
            await self._redis.set(
                self._prefix + key, json.dumps(asdict(value), ensure_ascii=False), ex=self._ttl
            )
        except REDIS_ERRORS as exc:
            log.warning("cache_redis_unavailable", op="set", error=type(exc).__name__)
