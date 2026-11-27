"""Shared fixtures. Unit tests never touch the network or real env files."""

import logging
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.db.session import create_engine
from app.devtools.localdb import migrate
from app.main import create_app


def make_settings(**overrides: Any) -> Settings:
    """Settings with no cloud services, ignoring any .env file and env vars for these keys."""
    values: dict[str, Any] = {
        "app_env": "test",
        "database_url": None,
        "database_url_migrations": None,
        "redis_url": None,
        "supabase_url": None,
        "gemini_api_key": None,
        "cors_origins": ["http://localhost:3000"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@asynccontextmanager
async def running_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Run the app lifespan (startup/shutdown) around an in-process HTTP client."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture(scope="session")
def db_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """A migrated Postgres + pgvector database for the whole test session.

    CI: the pgvector service container from DATABASE_URL. Locally: a fresh embedded pgserver
    database (dev dependency), so DB tests need no Docker and no cloud.
    """
    configured = os.environ.get("DATABASE_URL", "").strip()
    if configured:
        migrate(configured)
        yield configured
        return
    pgserver = pytest.importorskip("pgserver")
    logging.getLogger("pgserver").setLevel(logging.WARNING)
    server = pgserver.get_server(str(tmp_path_factory.mktemp("pg")), cleanup_mode="stop")
    server.psql("create database campus_pulse_test;")
    url = server.get_uri(database="campus_pulse_test")  # TCP on Windows, a socket elsewhere
    migrate(url)
    try:
        yield url
    finally:
        server.cleanup()  # stop Postgres now, not at interpreter exit


@pytest.fixture
async def db_engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(db_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Session inside an outer transaction that is always rolled back.

    Code under test may commit: with create_savepoint, its commits become savepoints, so
    nothing persists between tests.
    """
    async with db_engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async with running_client(create_app(settings)) as http:
        yield http
