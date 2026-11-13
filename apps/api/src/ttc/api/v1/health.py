from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ttc.core.db import database_configured, get_engine

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="进程存活探针")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", summary="服务就绪探针")
async def ready() -> dict[str, str]:
    if not database_configured():
        raise HTTPException(status_code=503, detail="database is not configured")
    engine = get_engine()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database is unavailable") from exc
    return {"status": "ready", "database": "ok"}
