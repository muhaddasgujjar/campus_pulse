"""Database connectivity with the pooler-safe engine settings (pgvector container or pgserver)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import create_app
from tests.conftest import make_settings, running_client

pytestmark = pytest.mark.integration


async def test_engine_connects_with_pooler_settings(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        # Run the same statement twice: fails if prepared statements are cached badly.
        for _ in range(2):
            assert (await conn.execute(text("select 1"))).scalar_one() == 1


async def test_pgvector_extension_is_installed(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("select count(*) from pg_extension where extname = 'vector'")
        )
        assert result.scalar_one() == 1


async def test_readyz_reports_database_ok(db_url: str) -> None:
    app = create_app(make_settings(database_url=db_url))
    async with running_client(app) as http:
        response = await http.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "ok"
