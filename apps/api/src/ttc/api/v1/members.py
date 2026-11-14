"""团队成员与角色权限。

成员就是 `app_user`：这里负责邀请（创建账号）、改角色、停用，以及查看/修改
角色权限矩阵。不提供删除，停用即可，避免破坏历史审计与投递记录的外键。
"""

import secrets
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, require_permission
from ttc.core.audit import record_audit
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.permissions import PERMISSIONS, matrix, replace_role
from ttc.core.security import hash_password, uuid7

router = APIRouter(tags=["members"])
member_admin = require_permission("member:manage")


class MemberCreate(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    display_name: str = Field(min_length=1, max_length=80)
    role: Literal["hr", "admin"] = "hr"
    password: str | None = Field(default=None, min_length=12, max_length=128)


class MemberPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    role: Literal["hr", "admin"] | None = None
    status: Literal["active", "disabled", "pending"] | None = None


class PermissionInput(BaseModel):
    role: Literal["hr", "candidate", "guest"]
    permissions: list[str]


@router.get("/admin/members")
async def list_members(user: Principal = Depends(member_admin),
                       session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(text(
        "SELECT id, email, display_name, role::text AS role, status::text AS status, "
        "last_login_at, created_at FROM app_user WHERE tenant_id = :tenant "
        "ORDER BY created_at"
    ), {"tenant": user.tenant_id})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/admin/members", status_code=201)
async def create_member(body: MemberCreate, user: Principal = Depends(member_admin),
                        session: AsyncSession = Depends(get_session)):
    email = body.email.strip().lower()
    exists = (await session.execute(text(
        "SELECT 1 FROM app_user WHERE tenant_id = :tenant AND email = :email"
    ), {"tenant": user.tenant_id, "email": email})).scalar_one_or_none()
    if exists is not None:
        raise TTCError("TTC-2002", "该邮箱已在本租户存在", 409)
    password = body.password or secrets.token_urlsafe(12)
    user_id = uuid7()
    row = (await session.execute(text(
        "INSERT INTO app_user (id, tenant_id, email, display_name, password_hash, role) "
        "VALUES (:id, :tenant, :email, :name, :hash, CAST(:role AS user_role)) "
        "RETURNING id, email, display_name, role::text AS role, status::text AS status, "
        "created_at"
    ), {"id": user_id, "tenant": user.tenant_id, "email": email,
        "name": body.display_name, "hash": hash_password(password),
        "role": body.role})).mappings().one()
    await record_audit(session, user, "member.create", "app_user", user_id)
    await session.commit()
    return {**dict(row), "temporary_password": None if body.password else password}


@router.patch("/admin/members/{member_id}")
async def patch_member(member_id: UUID, body: MemberPatch,
                       user: Principal = Depends(member_admin),
                       session: AsyncSession = Depends(get_session)):
    member = (await session.execute(text(
        "SELECT id, role::text AS role, status::text AS status FROM app_user "
        "WHERE id = :id AND tenant_id = :tenant"
    ), {"id": member_id, "tenant": user.tenant_id})).mappings().one_or_none()
    if member is None:
        raise TTCError("TTC-2001", "成员不存在", 404)
    if member_id == user.id and (body.role not in (None, "admin") or
                                 body.status not in (None, "active")):
        raise TTCError("TTC-2002", "不能降级或停用自己", 409)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return dict(member)
    row = (await session.execute(text(
        "UPDATE app_user SET display_name = COALESCE(:name, display_name), "
        "role = CAST(:role AS user_role), "
        "status = CAST(:status AS user_status) WHERE id = :id AND tenant_id = :tenant "
        "RETURNING id, email, display_name, role::text AS role, status::text AS status"
    ), {"id": member_id, "tenant": user.tenant_id,
        "name": changes.get("display_name"),
        "role": changes.get("role", member["role"]),
        "status": changes.get("status", member["status"])})).mappings().one()
    if changes.get("role") or changes.get("status"):
        await session.execute(text(
            "UPDATE auth_session SET revoked_at = now() WHERE user_id = :id "
            "AND revoked_at IS NULL"
        ), {"id": member_id})
    await record_audit(session, user, "member.update", "app_user", member_id)
    await session.commit()
    return dict(row)


@router.get("/admin/permissions")
async def get_permissions(user: Principal = Depends(member_admin),
                          session: AsyncSession = Depends(get_session)):
    return {"permissions": list(PERMISSIONS),
            "matrix": await matrix(session, user.tenant_id)}


@router.put("/admin/permissions")
async def put_permissions(body: PermissionInput,
                          user: Principal = Depends(member_admin),
                          session: AsyncSession = Depends(get_session)):
    try:
        saved = await replace_role(session, user.tenant_id, body.role, body.permissions)
    except ValueError as exc:
        raise TTCError("TTC-2002", str(exc), 409) from exc
    await record_audit(session, user, "permission.update", "role_permission", None)
    await session.commit()
    return {"role": body.role, "permissions": saved}
