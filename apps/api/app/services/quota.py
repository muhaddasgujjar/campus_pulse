"""Quota guard for LLM calls (COST-4, Architectural.md Section 6).

Counts calls per minute and per day. Near the per-minute limit a request waits (with backoff)
for up to QUOTA_MAX_WAIT_SECONDS; if it is still blocked, or the daily limit is reached, it
raises LLMQuotaError so the agent answers from templates or with the busy message.

The per-minute window is in process (one API worker, Architectural.md Section 13). The daily
count can live in Redis (`RedisDayCounter`), so a Render restart after sleeping does not reset
it; if Redis fails, the in-process count is used.
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.core.redis import REDIS_ERRORS
from app.services.llm.base import LLMQuotaError

log = get_logger("quota")


class RedisDayCounter:
    """Calls per provider per UTC day: INCR and EXPIRE NX in one round trip (2 commands)."""

    def __init__(self, redis: Redis, provider: str) -> None:
        self._redis = redis
        self._provider = provider

    async def incr(self, day: date) -> int:
        key = f"quota:{self._provider}:{day.isoformat()}"
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.incr(key)
            pipe.expire(key, 2 * 86400, nx=True)
            count, _ = await pipe.execute()
        return int(count)


class QuotaGuard:
    def __init__(
        self,
        rpm_limit: int | None,
        rpd_limit: int | None,
        max_wait_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        day_counter: RedisDayCounter | None = None,
    ) -> None:
        self.rpm_limit = rpm_limit
        self.rpd_limit = rpd_limit
        self.max_wait = max_wait_seconds
        self._clock = clock
        self._today = today
        self._sleep = sleep
        self._day_counter = day_counter
        self._minute: deque[float] = deque()
        self._day = today()
        self.used_today = 0

    def _prune(self, now: float) -> None:
        while self._minute and now - self._minute[0] >= 60:
            self._minute.popleft()
        if self._today() != self._day:
            self._day, self.used_today = self._today(), 0

    async def acquire(self) -> None:
        """Reserve one call or raise LLMQuotaError."""
        waited = 0.0
        delay = 1.0
        while True:
            now = self._clock()
            self._prune(now)
            if self.rpd_limit is not None and self.used_today >= self.rpd_limit:
                raise LLMQuotaError("daily LLM quota reached")
            if self.rpm_limit is None or len(self._minute) < self.rpm_limit:
                self._minute.append(now)
                await self._count_call()
                return
            if waited >= self.max_wait:
                raise LLMQuotaError("per-minute LLM quota reached")
            step = min(delay, self.max_wait - waited)
            await self._sleep(step)
            waited += step
            delay = min(delay * 2, 8.0)

    async def _count_call(self) -> None:
        if self._day_counter is None:
            self.used_today += 1
            return
        try:
            self.used_today = await self._day_counter.incr(self._day)
        except REDIS_ERRORS as exc:
            log.warning("quota_redis_unavailable", error=type(exc).__name__)
            self.used_today += 1
            return
        if self.rpd_limit is not None and self.used_today > self.rpd_limit:
            # Another process or an earlier run used the day's quota (shared Redis count).
            raise LLMQuotaError("daily LLM quota reached")
