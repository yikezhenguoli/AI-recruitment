from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, current_user, require_roles
from ttc.api.v1.jobs import require_job
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7

router = APIRouter(tags=["candidates"])
hr = require_roles("hr", "admin")


class CandidateCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    job_id: UUID | None = None
    source: Literal["demo", "invite", "upload"] = "demo"
    is_synthetic: bool = True


async def require_candidate(session: AsyncSession, user: Principal, candidate_id: UUID):
    if user.role not in ("admin", "hr", "candidate"):
        raise TTCError("TTC-1002", "无权访问候选人", 403)
    row = (await session.execute(
        text("SELECT id, tenant_id, user_id, display_name, contact_masked, source, "
             "job_id, is_synthetic, created_at FROM candidate "
             "WHERE id = :id AND tenant_id = :tenant"),
        {"id": candidate_id, "tenant": user.tenant_id},
    )).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "候选人不存在", 404)
    if user.role == "candidate" and row["user_id"] != user.id:
        raise TTCError("TTC-1003", "无法访问其他候选人", 403)
    return dict(row)


@router.post("/candidates", status_code=201)
async def create_candidate(body: CandidateCreate, user: Principal = Depends(hr),
                           session: AsyncSession = Depends(get_session)):
    if not body.is_synthetic:
        raise TTCError("TTC-4001", "真实候选人须先完成知情授权，当前仅允许合成样本", 403)
    if body.job_id:
        job = await require_job(session, user, body.job_id)
        if job["status"] == "archived":
            raise TTCError("TTC-2002", "岗位已归档", 409)
    candidate_id = uuid7()
    row = (await session.execute(
        text("INSERT INTO candidate (id, tenant_id, display_name, source, job_id, "
             "is_synthetic, created_by) VALUES (:id, :tenant, :name, "
             "CAST(:source AS candidate_source), :job, true, :user) "
             "RETURNING id, display_name, job_id, source, is_synthetic, created_at"),
        {"id": candidate_id, "tenant": user.tenant_id, "name": body.display_name,
         "source": body.source, "job": body.job_id, "user": user.id},
    )).mappings().one()
    await session.commit()
    return dict(row)


@router.get("/candidates")
async def list_candidates(job_id: UUID | None = None,
                          limit: int = Query(20, ge=1, le=100),
                          user: Principal = Depends(hr),
                          session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        text("SELECT id, display_name, job_id, source, is_synthetic, created_at "
             "FROM candidate WHERE tenant_id = :tenant "
        "AND (CAST(:job AS uuid) IS NULL OR job_id = CAST(:job AS uuid)) "
             "ORDER BY created_at DESC, id DESC LIMIT :limit"),
        {"tenant": user.tenant_id, "job": job_id, "limit": limit},
    )).mappings().all()
    return {"items": [dict(row) for row in rows], "next_cursor": None}


@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: UUID, user: Principal = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    return await require_candidate(session, user, candidate_id)


@router.get("/candidates/{candidate_id}/resumes")
async def candidate_resumes(candidate_id: UUID, user: Principal = Depends(hr),
                            session: AsyncSession = Depends(get_session)):
    await require_candidate(session, user, candidate_id)
    rows = (await session.execute(
        text("SELECT id, file_name, parse_status, created_at FROM resume "
             "WHERE candidate_id = :candidate ORDER BY created_at DESC, id DESC"),
        {"candidate": candidate_id},
    )).mappings().all()
    return {"items": [dict(row) for row in rows]}
