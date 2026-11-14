"""站内通知的写入工具。

通知是「谁该看到什么」的最小实现：只写库、由前端轮询，不发邮件也不推送。
调用方负责在同一个事务里 commit。
"""

from uuid import UUID

from sqlalchemy import text

from ttc.core.security import uuid7


async def notify(session, *, tenant_id: UUID, user_id: UUID, kind: str, title: str,
                 body: str | None = None, link: str | None = None) -> UUID:
    notification_id = uuid7()
    await session.execute(text(
        "INSERT INTO notification (id, tenant_id, user_id, kind, title, body, link) "
        "VALUES (:id, :tenant, :user, :kind, :title, :body, :link)"
    ), {"id": notification_id, "tenant": tenant_id, "user": user_id, "kind": kind,
        "title": title, "body": body, "link": link})
    return notification_id


async def notify_roles(session, *, tenant_id: UUID, roles: tuple[str, ...], kind: str,
                       title: str, body: str | None = None,
                       link: str | None = None) -> int:
    """通知租户内所有启用中的指定角色，返回写入条数。"""
    user_ids = (await session.execute(text(
        "SELECT id FROM app_user WHERE tenant_id = :tenant AND status = 'active' "
        "AND role::text = ANY(CAST(:roles AS text[]))"
    ), {"tenant": tenant_id, "roles": list(roles)})).scalars().all()
    for user_id in user_ids:
        await notify(session, tenant_id=tenant_id, user_id=user_id, kind=kind,
                     title=title, body=body, link=link)
    return len(user_ids)
