"""Migration 0001: tables, RLS deny-by-default, indexes, hybrid_search (M2, D16)."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import Base

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "institutions",
    "departments",
    "profiles",
    "kb_entries",
    "documents",
    "chunks",
    "faculty",
    "timetable",
    "fees",
    "offices",
    "key_dates",
    "live_sources",
    "conversations",
    "messages",
    "feedback",
    "unanswered_queries",
    "audit_log",
    "usage_daily",
}


async def test_all_tables_exist(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text("select tablename from pg_tables where schemaname = 'public'")
        )
        tables = {r[0] for r in rows} - {"alembic_version"}
    assert tables == EXPECTED_TABLES


async def test_rls_enabled_with_no_policies_on_every_table(db_engine: AsyncEngine) -> None:
    """Including alembic_version: Supabase exposes every public table to the Data API (D16)."""
    async with db_engine.connect() as conn:
        no_rls = await conn.execute(
            text("select tablename from pg_tables where schemaname = 'public' and not rowsecurity")
        )
        policies = await conn.execute(
            text("select count(*) from pg_policies where schemaname = 'public'")
        )
        assert [r[0] for r in no_rls] == []
        assert policies.scalar_one() == 0


async def test_vector_and_fulltext_indexes(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text("select indexname, indexdef from pg_indexes where tablename = 'chunks'")
        )
        defs = {name: definition for name, definition in rows}
    assert "USING hnsw (embedding vector_cosine_ops)" in defs["ix_chunks_embedding_hnsw"]
    assert "USING gin (tsv)" in defs["ix_chunks_tsv"]


async def test_embedding_column_is_768_dimensions(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "select format_type(atttypid, atttypmod) from pg_attribute "
                "where attrelid = 'chunks'::regclass and attname = 'embedding'"
            )
        )
        assert result.scalar_one() == "vector(768)"


async def test_hybrid_search_function_exists(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("select count(*) from pg_proc where proname = 'hybrid_search'")
        )
        assert result.scalar_one() == 1


def _diff(sync_conn: Connection) -> list[object]:
    context = MigrationContext.configure(sync_conn)
    return list(compare_metadata(context, Base.metadata))


async def test_models_match_migrations(db_engine: AsyncEngine) -> None:
    """Fails when a model changes without a migration (run alembic revision --autogenerate)."""
    async with db_engine.connect() as conn:
        diff = await conn.run_sync(_diff)
    assert diff == []


async def test_hybrid_search_has_a_fixed_search_path_and_no_public_execute(
    db_engine: AsyncEngine,
) -> None:
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "select p.proconfig, has_function_privilege('public', p.oid, 'execute') "
                    "from pg_proc p where p.proname = 'hybrid_search'"
                )
            )
        ).one()
    assert row[0] == ["search_path=public"]
    assert row[1] is False
