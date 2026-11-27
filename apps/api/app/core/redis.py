"""Upstash Redis client factory.

Built only when REDIS_URL is set. Used for the rate limit, session memory, the response cache
and the daily quota counters (M3). Budget: at most 10 commands per turn (Architectural.md
Section 14): rate limit 2, session 2, cache 2, quota up to 2 per LLM call. If Redis fails, each
feature falls back to in-process state (or no cache) and the chat keeps working.
"""

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings

# What a Redis call can raise when Upstash is down, slow or over its free quota.
REDIS_ERRORS: tuple[type[BaseException], ...] = (RedisError, OSError, TimeoutError)


def create_redis(settings: Settings) -> Redis | None:
    if not settings.redis_url:
        return None
    return Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
