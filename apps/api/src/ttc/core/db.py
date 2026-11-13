from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ttc.core.config import get_settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def database_configured() -> bool:
    return bool(get_settings().database_url)


def get_engine():
    global _engine, _session_factory
    database_url = get_settings().database_url
    if not database_url:
        return None
    if _engine is None:
        _engine = create_async_engine(database_url, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    get_engine()
    if _session_factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with _session_factory() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
