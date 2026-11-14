"""人才库：向量索引重建、检索与相似候选人。

只对招聘端开放；候选人门户没有对应接口。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.adapters.storage import Storage
from ttc.api.deps import Principal, require_roles
from ttc.core.audit import record_audit
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.domains.talent.index import index_candidate, search_candidates, similar_to

router = APIRouter(tags=["talent"])
hr = require_roles("hr", "admin")


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100)
    backend: str | None = Field(default=None, pattern="^(embedding|lexical)$")


@router.post("/talent/reindex")
async def reindex(limit: int = Query(default=200, ge=1, le=2000),
                  user: Principal = Depends(hr),
                  session: AsyncSession = Depends(get_session)):
    """为租户内每个候选人的最新已完成简历版本建立/更新索引。

    文本快照取不到（对象存储里文件缺失）的候选人计入 `skipped`，不中断整批。
    """
    rows = (await session.execute(text(
        "SELECT c.id AS candidate_id, v.id AS version_id, v.text_uri, c.display_name "
        "FROM candidate c JOIN LATERAL ("
        "  SELECT rv.id, rv.text_uri FROM resume_version rv "
        "  JOIN resume r ON r.id = rv.resume_id "
        "  WHERE r.candidate_id = c.id AND rv.status = 'done' AND rv.text_uri IS NOT NULL "
        "  ORDER BY rv.parsed_at DESC NULLS LAST, rv.version_no DESC LIMIT 1"
        ") v ON true WHERE c.tenant_id = :tenant ORDER BY c.created_at DESC LIMIT :limit"
    ), {"tenant": user.tenant_id, "limit": limit})).mappings().all()
    storage = Storage()
    indexed, skipped, warnings = 0, [], []
    for row in rows:
        try:
            raw = await storage.get(row["text_uri"])
        except Exception:
            skipped.append({"candidate_id": row["candidate_id"], "reason": "文本快照不可读"})
            continue
        content = raw.decode("utf-8-sig", errors="ignore").strip()
        if not content:
            skipped.append({"candidate_id": row["candidate_id"], "reason": "文本为空"})
            continue
        await index_candidate(session, tenant_id=user.tenant_id,
                              candidate_id=row["candidate_id"],
                              resume_version_id=row["version_id"], content=content,
                              warning_sink=warnings)
        indexed += 1
    await record_audit(session, user, "talent.reindex", "talent_index", None)
    await session.commit()
    unique_warnings = list(dict.fromkeys(warnings))
    return {"indexed": indexed, "skipped": skipped, "scanned": len(rows),
            "warnings": unique_warnings}


@router.post("/talent/search")
async def search(body: SearchInput, user: Principal = Depends(hr),
                 session: AsyncSession = Depends(get_session)):
    result = await search_candidates(session, tenant_id=user.tenant_id,
                                     query=body.query, limit=body.top_k,
                                     backend_filter=body.backend)
    if result["indexed"] == 0:
        result["hint"] = "尚未建立索引，请先调用 POST /talent/reindex"
    return result


@router.get("/talent/candidates/{candidate_id}/similar")
async def similar(candidate_id: UUID, limit: int = Query(default=10, ge=1, le=50),
                  user: Principal = Depends(hr),
                  session: AsyncSession = Depends(get_session)):
    exists = (await session.execute(text(
        "SELECT 1 FROM candidate WHERE id = :id AND tenant_id = :tenant"
    ), {"id": candidate_id, "tenant": user.tenant_id})).scalar_one_or_none()
    if exists is None:
        raise TTCError("TTC-2001", "候选人不存在", 404)
    return await similar_to(session, tenant_id=user.tenant_id,
                            candidate_id=candidate_id, limit=limit)
