from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, current_user
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import (
    access_token,
    new_refresh_token,
    token_digest,
    uuid7,
    verify_password,
)

router = APIRouter(tags=["auth"])


class LoginInput(BaseModel):
    tenant_slug: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class RefreshInput(BaseModel):
    refresh_token: str


async def issue_tokens(session: AsyncSession, user_id: UUID, family_id: UUID | None = None):
    refresh = new_refresh_token()
    await session.execute(
        text("INSERT INTO auth_session (id, user_id, family_id, token_hash, expires_at) "
             "VALUES (:id, :user_id, :family_id, :digest, :expires_at)"),
        {"id": uuid7(), "user_id": user_id, "family_id": family_id or uuid7(),
         "digest": token_digest(refresh),
         "expires_at": datetime.now(UTC) + timedelta(days=30)},
    )
    return {"access_token": access_token(user_id), "refresh_token": refresh,
            "token_type": "bearer", "expires_in": 900}


@router.post("/auth/login")
async def login(body: LoginInput, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("SELECT u.id, u.password_hash, u.status FROM app_user u "
             "JOIN tenant t ON t.id = u.tenant_id WHERE t.slug = :slug AND u.email = :email"),
        {"slug": body.tenant_slug, "email": body.email},
    )
    row = result.mappings().one_or_none()
    if row is None or not row["password_hash"] or not verify_password(
        body.password, row["password_hash"]
    ) or row["status"] != "active":
        raise TTCError("TTC-1001", "账号或密码错误", 401)
    tokens = await issue_tokens(session, row["id"])
    await session.commit()
    return tokens


@router.post("/auth/refresh")
async def refresh(body: RefreshInput, session: AsyncSession = Depends(get_session)):
    reused = False
    tokens = None
    async with session.begin():
        result = await session.execute(
            text("SELECT s.id, s.user_id, s.family_id, s.expires_at, s.revoked_at, "
                 "u.status FROM auth_session s JOIN app_user u ON u.id = s.user_id "
                 "WHERE s.token_hash = :digest FOR UPDATE OF s"),
            {"digest": token_digest(body.refresh_token)},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise TTCError("TTC-1001", "刷新令牌无效", 401)
        if row["revoked_at"]:
            await session.execute(
                text("UPDATE auth_session SET revoked_at = now() "
                     "WHERE family_id = :family_id AND revoked_at IS NULL"),
                {"family_id": row["family_id"]},
            )
            reused = True
        elif row["expires_at"] <= datetime.now(UTC) or row["status"] != "active":
            raise TTCError("TTC-1001", "令牌已过期", 401)
        else:
            await session.execute(
                text("UPDATE auth_session SET revoked_at = now(), last_used_at = now() "
                     "WHERE id = :id"), {"id": row["id"]},
            )
            tokens = await issue_tokens(session, row["user_id"], row["family_id"])
            await session.execute(
                text("UPDATE auth_session SET replaced_by = "
                     "(SELECT id FROM auth_session WHERE token_hash = :digest) WHERE id = :id"),
                {"digest": token_digest(tokens["refresh_token"]), "id": row["id"]},
            )
    if reused:
        raise TTCError("TTC-1001", "令牌已失效", 401)
    return tokens


@router.post("/auth/logout")
async def logout(body: RefreshInput, user: Principal = Depends(current_user),
                 session: AsyncSession = Depends(get_session)):
    await session.execute(
        text("UPDATE auth_session SET revoked_at = now() WHERE token_hash = :digest "
             "AND user_id = :user_id AND revoked_at IS NULL"),
        {"digest": token_digest(body.refresh_token), "user_id": user.id},
    )
    await session.commit()
    return {"status": "logged_out"}


@router.get("/me")
async def me(user: Principal = Depends(current_user)):
    return {"id": user.id, "tenant_id": user.tenant_id, "role": user.role,
            "display_name": user.display_name}
