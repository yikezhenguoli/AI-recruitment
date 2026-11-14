import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ttc.core.config import get_settings


def alembic_head() -> str:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


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
                assert tables == 36
                enums = await connection.scalar(
                    text("SELECT count(*) FROM pg_type WHERE typtype = 'e' "
                         "AND typnamespace = 'public'::regnamespace")
                )
                assert enums == 20
                extensions = await connection.execute(
                    text("SELECT extname FROM pg_extension WHERE extname IN ('citext', 'pg_trgm')")
                )
                assert {row[0] for row in extensions} == {"citext", "pg_trgm"}
                # 迁移头由 ScriptDirectory 读出，避免每加一版迁移就要手改字面量。
                assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    alembic_head()
                )
        finally:
            await engine.dispose()

    asyncio.run(verify())
