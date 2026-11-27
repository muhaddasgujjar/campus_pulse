"""Redis-backed chat stores and their in-process fallbacks (CHAT-5, CHAT-7, COST-3, COST-4).

fakeredis stands in for Upstash; a refused connection (port 1) stands in for Redis being down.
"""

from collections.abc import AsyncIterator
from datetime import date

import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis

from app.agent.cache import CachedAnswer, RedisResponseCache
from app.services.llm.base import LLMQuotaError
from app.services.quota import QuotaGuard, RedisDayCounter
from app.services.ratelimit import MemoryRateLimiter, RedisRateLimiter
from app.services.session_memory import (
    MemorySessionMemory,
    RedisSessionMemory,
    Turn,
    append_turn,
)


@pytest.fixture
async def redis() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def down() -> AsyncIterator[Redis]:
    client = Redis.from_url("redis://127.0.0.1:1", socket_connect_timeout=0.5)
    try:
        yield client
    finally:
        await client.aclose()


# --- rate limit (CHAT-7) -----------------------------------------------------------------------


async def test_memory_rate_limit_blocks_after_the_limit_and_resets() -> None:
    now = [0.0]
    limiter = MemoryRateLimiter(limit=2, window_seconds=600, clock=lambda: now[0])
    assert (await limiter.hit("ip")).allowed
    assert (await limiter.hit("ip")).allowed
    blocked = await limiter.hit("ip")
    assert not blocked.allowed and blocked.retry_after_seconds == 600
    assert (await limiter.hit("other-ip")).allowed
    now[0] = 600
    assert (await limiter.hit("ip")).allowed


async def test_redis_rate_limit_counts_in_redis_with_an_expiry(redis: FakeAsyncRedis) -> None:
    limiter = RedisRateLimiter(redis, 2, 600, MemoryRateLimiter(2, 600))
    assert (await limiter.hit("1.2.3.4")).allowed
    assert (await limiter.hit("1.2.3.4")).allowed
    assert not (await limiter.hit("1.2.3.4")).allowed
    assert 0 < await redis.ttl("rl:1.2.3.4") <= 600


async def test_rate_limit_falls_back_to_memory_when_redis_is_down(down: Redis) -> None:
    limiter = RedisRateLimiter(down, 1, 600, MemoryRateLimiter(1, 600))
    assert (await limiter.hit("ip")).allowed
    assert not (await limiter.hit("ip")).allowed


# --- session memory (CHAT-5) -------------------------------------------------------------------


def test_append_turn_keeps_the_last_n() -> None:
    turns = [Turn(f"q{i}", f"a{i}") for i in range(6)]
    kept = append_turn(turns, Turn("q6", "a6"), 6)
    assert [t.question for t in kept] == ["q1", "q2", "q3", "q4", "q5", "q6"]
    assert append_turn(turns, Turn("q", "a"), 0) == []


async def test_redis_session_memory_round_trip_with_ttl(redis: FakeAsyncRedis) -> None:
    memory = RedisSessionMemory(redis, 86400, MemorySessionMemory(86400))
    assert await memory.recent("c1") == []
    await memory.save("c1", [Turn("What are the fees for BSCS?", "Rs 7,744 per credit hour")])
    assert await memory.recent("c1") == [
        Turn("What are the fees for BSCS?", "Rs 7,744 per credit hour")
    ]
    assert 0 < await redis.ttl("sess:c1") <= 86400


async def test_session_memory_expires_in_process() -> None:
    now = [0.0]
    memory = MemorySessionMemory(ttl_seconds=10, clock=lambda: now[0])
    await memory.save("c1", [Turn("q", "a")])
    now[0] = 11
    assert await memory.recent("c1") == []


async def test_session_memory_falls_back_to_memory_when_redis_is_down(down: Redis) -> None:
    memory = RedisSessionMemory(down, 86400, MemorySessionMemory(86400))
    await memory.save("c1", [Turn("q", "a")])
    assert await memory.recent("c1") == [Turn("q", "a")]


# --- response cache (COST-3) -------------------------------------------------------------------


async def test_redis_response_cache_round_trip(redis: FakeAsyncRedis) -> None:
    cache = RedisResponseCache(redis, ttl_seconds=60)
    value = CachedAnswer("answer", [{"title": "Fee Structure"}], "get_fee")
    assert await cache.get("k") is None
    await cache.set("k", value)
    assert await cache.get("k") == value
    assert 0 < await redis.ttl("cache:k") <= 60


async def test_redis_response_cache_is_a_miss_when_redis_is_down(down: Redis) -> None:
    cache = RedisResponseCache(down, ttl_seconds=60)
    await cache.set("k", CachedAnswer("answer", [], None))  # no exception
    assert await cache.get("k") is None


async def test_redis_response_cache_off_with_zero_ttl(redis: FakeAsyncRedis) -> None:
    cache = RedisResponseCache(redis, ttl_seconds=0)
    await cache.set("k", CachedAnswer("answer", [], None))
    assert await redis.get("cache:k") is None


# --- quota day counter (COST-4) ----------------------------------------------------------------


async def test_daily_quota_is_shared_through_redis(redis: FakeAsyncRedis) -> None:
    day = date(2026, 11, 27)

    def guard() -> QuotaGuard:
        return QuotaGuard(None, 2, 0, today=lambda: day, day_counter=RedisDayCounter(redis, "groq"))

    await guard().acquire()
    await guard().acquire()  # a new process (Render restart) sees the same count
    with pytest.raises(LLMQuotaError):
        await guard().acquire()
    assert await redis.get("quota:groq:2026-11-27") == b"3"


async def test_daily_quota_counts_in_process_when_redis_is_down(down: Redis) -> None:
    quota = QuotaGuard(None, 1, 0, day_counter=RedisDayCounter(down, "groq"))
    await quota.acquire()
    with pytest.raises(LLMQuotaError):
        await quota.acquire()
