"""Quota guard for LLM calls (COST-4, Architectural.md Section 6).

Counts calls per minute and per day. Near the per-minute limit a request waits (with backoff)
for up to QUOTA_MAX_WAIT_SECONDS; if it is still blocked, or the daily limit is reached, it
raises LLMQuotaError so the agent answers from templates or with the busy message.
In-process counters now; M3 moves them to Redis (shared across restarts) and usage_daily.
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

from app.services.llm.base import LLMQuotaError


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
    ) -> None:
        self.rpm_limit = rpm_limit
        self.rpd_limit = rpd_limit
        self.max_wait = max_wait_seconds
        self._clock = clock
        self._today = today
        self._sleep = sleep
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
                self.used_today += 1
                return
            if waited >= self.max_wait:
                raise LLMQuotaError("per-minute LLM quota reached")
            step = min(delay, self.max_wait - waited)
            await self._sleep(step)
            waited += step
            delay = min(delay * 2, 8.0)
