"""Database integration tests. Run only when DATABASE_URL is set (CI service container).

CI uses a local `pgvector/pgvector:pg16` container, never Supabase and never secrets.
"""

import os

import pytest
from sqlalchemy import text

from app.db.session import create_engine
from app.main import create_app
from tests.conftest import make_settings, running_client

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set"),
]


async def test_engine_connects_with_pooler_settings() -> None:
    engine = create_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            # Run the same statement twice: fails if prepared statements are cached badly.
            for _ in range(2):
                assert (await conn.execute(text("select 1"))).scalar_one() == 1
    finally:
        await engine.dispose()


async def test_pgvector_extension_is_available() -> None:
    engine = create_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("select count(*) from pg_available_extensions where name = 'vector'")
            )
            assert result.scalar_one() == 1
    finally:
        await engine.dispose()


async def test_readyz_reports_database_ok() -> None:
    app = create_app(make_settings(database_url=DATABASE_URL))
    async with running_client(app) as http:
        response = await http.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "ok"
