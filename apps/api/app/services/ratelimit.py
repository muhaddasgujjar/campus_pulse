"""Fixed-window rate limit for anonymous chat (CHAT-7): for example 20 messages per 10 minutes
per IP. Redis when configured (2 commands per message: INCR and EXPIRE NX, one round trip),
otherwise, or when Redis fails, in-process counters."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.core.redis import REDIS_ERRORS

log = get_logger("ratelimit")


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter(Protocol):
    async def hit(self, key: str) -> RateDecision: ...


class MemoryRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._windows: dict[str, tuple[float, int]] = {}

    async def hit(self, key: str) -> RateDecision:
        now = self._clock()
        started, count = self._windows.get(key, (now, 0))
        if now - started >= self.window:
            started, count = now, 0
        count += 1
        if len(self._windows) >= self._max_keys and key not in self._windows:
            # Drop expired windows; memory stays bounded under many IPs.
            self._windows = {k: v for k, v in self._windows.items() if now - v[0] < self.window}
        self._windows[key] = (started, count)
        if count > self.limit:
            return RateDecision(False, max(1, round(self.window - (now - started))))
        return RateDecision(True)


class RedisRateLimiter:
    def __init__(
        self, redis: Redis, limit: int, window_seconds: int, fallback: MemoryRateLimiter
    ) -> None:
        self._redis = redis
        self.limit = limit
        self.window = window_seconds
        self._fallback = fallback

    async def hit(self, key: str) -> RateDecision:
        name = f"rl:{key}"
        try:
            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.incr(name)
                pipe.expire(name, self.window, nx=True)
                count, _ = await pipe.execute()
        except REDIS_ERRORS as exc:
            log.warning("ratelimit_redis_unavailable", error=type(exc).__name__)
            return await self._fallback.hit(key)
        if int(count) > self.limit:
            return RateDecision(False, self.window)
        return RateDecision(True)
