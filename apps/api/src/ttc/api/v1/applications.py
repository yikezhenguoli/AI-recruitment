"""HR 视角的投递列表：创建 Offer / 排期时需要选一条投递。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, require_roles
from ttc.core.db import get_session

router = APIRouter(tags=["applications"])
hr = require_roles("hr", "admin")


@router.get("/applications")
async def list_applications(job_id: UUID | None = None,
                            status: str | None = None,
                            limit: int = Query(default=100, ge=1, le=500),
                            user: Principal = Depends(hr),
                            session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(text(
        "SELECT ap.id, ap.status::text AS status, ap.created_at, ap.updated_at, "
        "ap.candidate_id, c.display_name AS candidate_name, c.source, "
        "j.id AS job_id, j.title AS job_title, j.department, "
        "asmt.match_score, o.id AS offer_id, o.status::text AS offer_status "
        "FROM application ap "
        "JOIN candidate c ON c.id = ap.candidate_id "
        "JOIN job j ON j.id = ap.job_id "
        "LEFT JOIN LATERAL ("
        "  SELECT a2.match_score FROM assessment a2 "
        "  WHERE a2.candidate_id = ap.candidate_id AND a2.job_id = ap.job_id "
        "  ORDER BY a2.updated_at DESC LIMIT 1"
        ") asmt ON true "
        "LEFT JOIN offer o ON o.application_id = ap.id "
        "WHERE ap.tenant_id = :tenant "
        "AND (CAST(:job AS uuid) IS NULL OR ap.job_id = CAST(:job AS uuid)) "
        "AND (CAST(:status AS text) IS NULL OR ap.status::text = CAST(:status AS text)) "
        "ORDER BY ap.created_at DESC LIMIT :limit"
    ), {"tenant": user.tenant_id, "job": job_id, "status": status,
        "limit": limit})).mappings().all()
    return {"items": [dict(row) for row in rows]}
