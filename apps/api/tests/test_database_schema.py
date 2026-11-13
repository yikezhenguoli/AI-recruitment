import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ttc.core.config import get_settings


def test_postgresql_schema_matches_initial_design() -> None:
    database_url = get_settings().database_url
    if not database_url:
        pytest.skip("Set DATABASE_URL and migrate to run the database integration test")

    async def verify() -> None:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                version = await connection.scalar(text("SHOW server_version_num"))
                assert 160000 <= int(version) < 170000
                tables = await connection.scalar(
                    text("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_schema = 'public' AND table_name <> 'alembic_version'")
                )
                assert tables == 28
                enums = await connection.scalar(
                    text("SELECT count(*) FROM pg_type WHERE typtype = 'e' "
                         "AND typnamespace = 'public'::regnamespace")
                )
                assert enums == 20
                extensions = await connection.execute(
                    text("SELECT extname FROM pg_extension WHERE extname IN ('citext', 'pg_trgm')")
                )
                assert {row[0] for row in extensions} == {"citext", "pg_trgm"}
                assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    "0004_realtime_call"
                )
        finally:
            await engine.dispose()

    asyncio.run(verify())
