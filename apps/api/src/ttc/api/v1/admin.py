from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, require_roles
from ttc.core.config import get_settings
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7

router = APIRouter(tags=["admin", "integrations"])
admin = require_roles("admin")
hr = require_roles("hr", "admin")


class SourcePatch(BaseModel):
    enabled: bool | None = None
    rate_limit: int | None = Field(default=None, ge=1, le=300)


@router.get("/admin/data-sources")
async def sources(user: Principal = Depends(admin),
                  session: AsyncSession = Depends(get_session)):
    row = (await session.execute(text(
        "SELECT id, name, enabled, rate_limit FROM data_source "
        "WHERE tenant_id = :tenant AND name = 'crossref'"
    ), {"tenant": user.tenant_id})).mappings().one_or_none()
    return {"items": [dict(row) if row else {"id": None, "name": "crossref",
                                           "enabled": True, "rate_limit": 30}]}


@router.patch("/admin/data-sources/{source_id}")
async def update_source(source_id: UUID, body: SourcePatch,
                        user: Principal = Depends(admin),
                        session: AsyncSession = Depends(get_session)):
    row = (await session.execute(text(
        "UPDATE data_source SET enabled = COALESCE(:enabled, enabled), "
        "rate_limit = COALESCE(:rate, rate_limit) WHERE id = :id "
        "AND tenant_id = :tenant AND name = 'crossref' "
        "RETURNING id, name, enabled, rate_limit"
    ), {"id": source_id, "tenant": user.tenant_id,
        "enabled": body.enabled, "rate": body.rate_limit})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "数据源不存在", 404)
    await session.commit()
    return dict(row)


@router.post("/admin/data-sources/crossref", status_code=201)
async def enable_crossref(user: Principal = Depends(admin),
                          session: AsyncSession = Depends(get_session)):
    row = (await session.execute(text(
        "INSERT INTO data_source (id, tenant_id, name) VALUES (:id, :tenant, 'crossref') "
        "ON CONFLICT (tenant_id, name) DO UPDATE SET enabled = true "
        "RETURNING id, name, enabled, rate_limit"
    ), {"id": uuid7(), "tenant": user.tenant_id})).mappings().one()
    await session.commit()
    return dict(row)


@router.get("/admin/audit-logs")
async def audit_logs(limit: int = Query(default=50, ge=1, le=200),
                     user: Principal = Depends(admin),
                     session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(text(
        "SELECT id, actor_id, action, resource_type, resource_id, request_id, detail, "
        "created_at FROM audit_log WHERE tenant_id = :tenant "
        "ORDER BY id DESC LIMIT :limit"
    ), {"tenant": user.tenant_id, "limit": limit})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/admin/metrics")
async def metrics(user: Principal = Depends(admin),
                  session: AsyncSession = Depends(get_session)):
    counts = (await session.execute(text(
        "SELECT status::text, count(*) FROM task WHERE tenant_id = :tenant GROUP BY status"
    ), {"tenant": user.tenant_id})).all()
    return {"tasks": dict(counts), "scope": "tenant"}


@router.get("/integrations/status")
async def integrations_status(user: Principal = Depends(hr)):
    settings = get_settings()
    return {"openats": {"configured": bool(settings.openats_base_url and
                                           settings.openats_api_key),
                        "status": "not_implemented"},
            "vekt": {"configured": bool(settings.vekt_base_url and settings.vekt_api_key),
                     "status": "not_implemented", "fallback": "PostgreSQL"}}


@router.get("/integrations/openats/status")
async def openats_status(user: Principal = Depends(hr)):
    return {"status": "not_implemented", "last_synced_at": None, "failures": 0}


@router.post("/integrations/openats/sync")
async def openats_sync(user: Principal = Depends(admin)):
    raise TTCError("TTC-5004", "尚无 OpenATS API 协议及租户凭证，不能执行真实同步", 503)


@router.post("/integrations/vekt/rebuild")
async def vekt_rebuild(user: Principal = Depends(admin)):
    raise TTCError("TTC-5004", "尚无 Vekt API 协议及 embedding 模型，不能重建索引", 503)
