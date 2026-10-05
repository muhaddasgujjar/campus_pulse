"""Response cache (COST-3): repeated questions cost no LLM call.

Key: normalized question, language, profile program and data_version. Bumping data_version
(on any content write) makes every old key unreachable, so staff edits appear immediately.
This in-process version backs local development, tests and eval; M3 adds the Redis version
(shared across workers and restarts) behind the same interface.
"""

import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


def normalize_query(text: str) -> str:
    return " ".join(text.lower().strip(" ?!.").split())


def cache_key(normalized: str, language: str, program: str | None, data_version: int) -> str:
    raw = f"{data_version}|{language}|{(program or '').lower()}|{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class CachedAnswer:
    answer: str
    sources: list[dict[str, Any]]
    tool_used: str | None


class ResponseCache(Protocol):
    data_version: int

    async def get(self, key: str) -> CachedAnswer | None: ...

    async def set(self, key: str, value: CachedAnswer) -> None: ...

    async def bump_version(self) -> int: ...


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
        self.data_version = 1

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

    async def bump_version(self) -> int:
        self.data_version += 1
        return self.data_version
