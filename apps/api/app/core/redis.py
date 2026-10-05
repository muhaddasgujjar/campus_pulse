"""Upstash Redis client factory.

Built only when REDIS_URL is set. Session memory, rate limits, the response cache,
`data_version` and quota counters arrive in M3 (budget: at most 10 commands per turn).
"""

from redis.asyncio import Redis

from app.core.config import Settings


def create_redis(settings: Settings) -> Redis | None:
    if not settings.redis_url:
        return None
    return Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
