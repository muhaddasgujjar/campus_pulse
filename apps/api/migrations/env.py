"""Alembic environment (async).

Migrations run against the Supabase **session pooler** URL in DATABASE_URL_MIGRATIONS
(DDL and long transactions are safe there). The app itself uses the transaction pooler
(DATABASE_URL). Schema changes go only through migrations (Memory conventions).
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import Base
from app.db.session import pooler_connect_args, to_async_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migrations_url() -> str:
    url = os.environ.get("DATABASE_URL_MIGRATIONS", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL_MIGRATIONS is not set. Use the Supabase session pooler URL "
            "(Project Settings > Database > Connection string > Session pooler)."
        )
    return to_async_url(url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a database connection (`alembic upgrade head --sql`)."""
    context.configure(
        url=_migrations_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Pooler-safe connect args also work on the session pooler and on plain Postgres (CI).
    engine = create_async_engine(
        _migrations_url(), poolclass=NullPool, connect_args=pooler_connect_args()
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
