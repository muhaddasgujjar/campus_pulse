"""Async SQLAlchemy engine and session for Supabase Postgres.

The app connects through the Supabase **transaction pooler** (Supavisor, PgBouncer
compatible). Prepared statements do not survive across pooled transactions, so:
- asyncpg's statement cache is disabled (`statement_cache_size=0`),
- SQLAlchemy's prepared statement cache is disabled (`prepared_statement_cache_size=0`),
- statement names are unique per prepare (avoids "prepared statement already exists"),
- `NullPool`: the pooler does the pooling, we do not hold connections ourselves.
Alembic uses the session pooler instead (DATABASE_URL_MIGRATIONS), see migrations/env.py.
"""

from collections.abc import AsyncIterator
from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


def to_async_url(url: str) -> str:
    """Supabase shows `postgresql://` URLs. SQLAlchemy needs the asyncpg driver name."""
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    raise ValueError("DATABASE_URL must start with postgresql:// or postgres://")


def pooler_connect_args() -> dict[str, object]:
    return {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        to_async_url(database_url),
        poolclass=NullPool,
        connect_args=pooler_connect_args(),
        pool_pre_ping=False,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_scope(
    maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a session (used as a FastAPI dependency from M2 on)."""
    async with maker() as session:
        yield session
