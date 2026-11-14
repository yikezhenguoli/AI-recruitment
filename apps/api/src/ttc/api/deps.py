from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.permissions import has_permission
from ttc.core.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    id: UUID
    tenant_id: UUID
    role: str
    display_name: str


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise TTCError("TTC-1001", "请先登录", 401)
    try:
        user_id = decode_access_token(credentials.credentials)
    except (jwt.PyJWTError, ValueError, RuntimeError) as exc:
        raise TTCError("TTC-1001", "令牌无效或已过期", 401) from exc
    result = await session.execute(
        text("SELECT id, tenant_id, role, display_name FROM app_user "
             "WHERE id = :id AND status = 'active'"), {"id": user_id}
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-1001", "账号不存在或已停用", 401)
    return Principal(row["id"], row["tenant_id"], row["role"], row["display_name"])


def require_roles(*allowed: str):
    async def check(user: Principal = Depends(current_user)) -> Principal:
        if user.role not in allowed:
            raise TTCError("TTC-1002", "无权执行该操作", 403)
        return user
    return check


def require_permission(permission: str):
    """按租户的权限矩阵校验；admin 始终通过。"""

    async def check(user: Principal = Depends(current_user),
                    session: AsyncSession = Depends(get_session)) -> Principal:
        if not await has_permission(session, user.tenant_id, user.role, permission):
            raise TTCError("TTC-1002", f"缺少权限：{permission}", 403)
        return user

    return check
