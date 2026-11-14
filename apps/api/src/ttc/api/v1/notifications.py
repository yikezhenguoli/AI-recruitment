"""站内通知：招聘端与候选人端共用，按登录账号（`app_user`）隔离。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, current_user
from ttc.core.db import get_session
from ttc.core.errors import TTCError

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
async def list_notifications(unread_only: bool = Query(default=False),
                             limit: int = Query(default=50, ge=1, le=200),
                             user: Principal = Depends(current_user),
                             session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(text(
        "SELECT id, kind, title, body, link, read_at, created_at FROM notification "
        "WHERE user_id = :user AND tenant_id = :tenant "
        "AND (NOT CAST(:unread AS boolean) OR read_at IS NULL) "
        "ORDER BY created_at DESC, id DESC LIMIT :limit"
    ), {"user": user.id, "tenant": user.tenant_id, "unread": unread_only,
        "limit": limit})).mappings().all()
    unread = (await session.execute(text(
        "SELECT count(*) FROM notification WHERE user_id = :user "
        "AND tenant_id = :tenant AND read_at IS NULL"
    ), {"user": user.id, "tenant": user.tenant_id})).scalar_one()
    return {"items": [dict(row) for row in rows], "unread": unread}


@router.post("/notifications/{notification_id}/read")
async def mark_read(notification_id: UUID, user: Principal = Depends(current_user),
                    session: AsyncSession = Depends(get_session)):
    row = (await session.execute(text(
        "UPDATE notification SET read_at = COALESCE(read_at, now()) "
        "WHERE id = :id AND user_id = :user AND tenant_id = :tenant "
        "RETURNING id, read_at"
    ), {"id": notification_id, "user": user.id, "tenant": user.tenant_id})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "通知不存在", 404)
    await session.commit()
    return dict(row)


@router.post("/notifications/read-all")
async def mark_all_read(user: Principal = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    result = await session.execute(text(
        "UPDATE notification SET read_at = now() WHERE user_id = :user "
        "AND tenant_id = :tenant AND read_at IS NULL"
    ), {"user": user.id, "tenant": user.tenant_id})
    await session.commit()
    return {"marked": result.rowcount}
