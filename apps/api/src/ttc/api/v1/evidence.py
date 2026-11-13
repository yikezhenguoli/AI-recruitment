import hashlib
import json
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, require_roles
from ttc.api.v1.candidates import require_candidate
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7

router = APIRouter(tags=["evidence"])
hr = require_roles("hr", "admin")


class SearchInput(BaseModel):
    claim_ids: list[UUID] = Field(default_factory=list, max_length=30)
    sources: list[str] = Field(default_factory=lambda: ["crossref"])
    max_per_entity: int = Field(default=5, ge=1, le=10)


async def require_evidence(session, user, evidence_id):
    row = (await session.execute(text(
        "SELECT e.* FROM evidence e WHERE e.id = :id AND e.tenant_id = :tenant"
    ), {"id": evidence_id, "tenant": user.tenant_id})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "证据不存在", 404)
    return dict(row)


@router.post("/candidates/{candidate_id}/evidence-search", status_code=202)
async def search_evidence(candidate_id: UUID, body: SearchInput,
                          user: Principal = Depends(hr),
                          session: AsyncSession = Depends(get_session)):
    candidate = await require_candidate(session, user, candidate_id)
    if not candidate["is_synthetic"]:
        from ttc.api.v1.consents import require_consent
        await require_consent(session, candidate_id, "resume_process")
    if set(body.sources) != {"crossref"}:
        raise TTCError("TTC-4000", "目前只支持 Crossref DOI 精确检索", 422)
    policy = (await session.execute(text(
        "SELECT enabled, rate_limit FROM data_source "
        "WHERE tenant_id = :tenant AND name = 'crossref'"
    ), {"tenant": user.tenant_id})).mappings().one_or_none()
    if policy and not policy["enabled"]:
        raise TTCError("TTC-4001", "Crossref 数据源已停用", 403)
    recent = (await session.execute(text(
        "SELECT count(*) FROM task WHERE tenant_id = :tenant "
        "AND type = 'evidence_search' AND created_at > now() - interval '60 seconds'"
    ), {"tenant": user.tenant_id})).scalar_one()
    if recent >= (policy["rate_limit"] if policy else 30):
        raise TTCError("TTC-4002", "证据检索请求过于频繁", 429)
    rows = (await session.execute(text(
        "SELECT c.id, c.normalized, c.raw_text FROM resume_claim c "
        "JOIN resume_version v ON v.id = c.resume_version_id "
        "JOIN resume r ON r.id = v.resume_id "
        "WHERE r.candidate_id = :candidate AND c.claim_type = 'publication' "
        "AND v.id = (SELECT v2.id FROM resume_version v2 "
        "JOIN resume r2 ON r2.id = v2.resume_id WHERE r2.candidate_id = :candidate "
        "AND v2.status = 'done' ORDER BY v2.parsed_at DESC LIMIT 1)"
    ), {"candidate": candidate_id})).mappings().all()
    claims = [row for row in rows if (not body.claim_ids or row["id"] in body.claim_ids)
              and row["normalized"].get("doi") and
              str(row["normalized"]["doi"]).casefold() in row["raw_text"].casefold()]
    if body.claim_ids and len({row["id"] for row in rows} & set(body.claim_ids)) != len(
        set(body.claim_ids)
    ):
        raise TTCError("TTC-2001", "部分论文陈述不存在或不属于候选人", 404)
    if not claims:
        raise TTCError("TTC-2002", "没有可用 DOI 的论文陈述；不能凭名称推断匹配", 409)
    task_id = uuid7()
    await session.execute(text(
        "INSERT INTO task (id, tenant_id, type, resource_type, resource_id, payload) "
        "VALUES (:id, :tenant, 'evidence_search', 'candidate', :candidate, "
        "CAST(:payload AS jsonb))"
    ), {"id": task_id, "tenant": user.tenant_id, "candidate": candidate_id,
        "payload": json.dumps({"claim_ids": [str(row["id"]) for row in claims],
                               "sources": ["crossref"]})})
    await session.commit()
    return {"task_id": task_id, "entities": len(claims), "status": "queued"}


async def fetch_crossref(session: AsyncSession, task: dict) -> int:
    payload = task["payload"]
    count = 0
    candidate = (await session.execute(text(
        "SELECT is_synthetic FROM candidate WHERE id = :id AND tenant_id = :tenant"
    ), {"id": task["resource_id"], "tenant": task["tenant_id"]})).mappings().one_or_none()
    if candidate is None:
        raise TTCError("TTC-2001", "候选人不存在", 404)
    policy = (await session.execute(text(
        "SELECT enabled FROM data_source WHERE tenant_id = :tenant AND name = 'crossref'"
    ), {"tenant": task["tenant_id"]})).scalar_one_or_none()
    if policy is False:
        raise TTCError("TTC-4001", "Crossref 数据源已停用", 403)
    if not candidate["is_synthetic"]:
        from ttc.api.v1.consents import require_consent
        await require_consent(session, task["resource_id"], "resume_process")
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        for claim_id in payload["claim_ids"]:
            claim = (await session.execute(text(
                "SELECT c.normalized, c.raw_text FROM resume_claim c JOIN resume_version v "
                "ON v.id = c.resume_version_id JOIN resume r ON r.id = v.resume_id "
                "JOIN candidate p ON p.id = r.candidate_id WHERE c.id = :id "
                "AND p.id = :candidate AND p.tenant_id = :tenant"
            ), {"id": UUID(claim_id), "candidate": task["resource_id"],
                "tenant": task["tenant_id"]})).mappings().one_or_none()
            if claim is None:
                continue
            doi = str(claim["normalized"].get("doi", "")).strip().lower()
            if (not doi.startswith("10.") or len(doi) > 255 or any(c.isspace() for c in doi)
                    or doi not in claim["raw_text"].casefold()):
                continue
            from urllib.parse import quote
            try:
                response = await client.get("https://api.crossref.org/works/" +
                                            quote(doi, safe="/"))
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                item = response.json()["message"]
                if str(item.get("DOI", "")).lower() != doi:
                    continue
                title = (item.get("title") or [doi])[0][:500]
                collision = (await session.execute(text(
                    "SELECT external_ids FROM entity WHERE tenant_id = :tenant "
                    "AND entity_type = 'paper' AND canonical_name = :name"
                ), {"tenant": task["tenant_id"], "name": title})).scalar_one_or_none()
                if collision and collision.get("doi") != doi:
                    title = f"{title[:400]} [{doi}]"
                entity_id = (await session.execute(text(
                    "INSERT INTO entity (id, tenant_id, entity_type, canonical_name, external_ids) "
                    "VALUES (:id, :tenant, 'paper', :name, CAST(:external AS jsonb)) "
                    "ON CONFLICT (tenant_id, entity_type, canonical_name) "
                    "DO UPDATE SET canonical_name = excluded.canonical_name RETURNING id"
                ), {"id": uuid7(), "tenant": task["tenant_id"], "name": title,
                    "external": json.dumps({"doi": doi})})).scalar_one()
                url = "https://doi.org/" + quote(doi, safe="/")
                snapshot = json.dumps({"DOI": doi, "title": title}, ensure_ascii=False)
                await session.execute(text(
                    "INSERT INTO evidence (id, tenant_id, entity_id, claim_id, source_type, "
                    "source_name, source_url, title, snippet, accessed_at, grade, "
                    "content_hash, match_method, match_confidence) "
                    "SELECT :id, :tenant, :entity, :claim, 'api', 'Crossref', :url, :title, "
                    ":snippet, now(), 'B', :hash, 'doi', 0.990 "
                    "WHERE NOT EXISTS (SELECT 1 FROM evidence WHERE claim_id = :claim "
                    "AND source_name = 'Crossref' AND source_url = :url)"
                ), {"id": uuid7(), "tenant": task["tenant_id"], "entity": entity_id,
                    "claim": UUID(claim_id), "url": url, "title": title,
                    "snippet": "DOI 对应作品元数据；不证明候选人为作者",
                    "hash": hashlib.sha256(snapshot.encode()).digest()})
                count += 1
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                raise TTCError("TTC-5004", "Crossref 检索失败", 503) from exc
    return count


@router.get("/candidates/{candidate_id}/evidence")
async def list_evidence(candidate_id: UUID, limit: int = Query(100, ge=1, le=200),
                        user: Principal = Depends(hr),
                        session: AsyncSession = Depends(get_session)):
    await require_candidate(session, user, candidate_id)
    rows = (await session.execute(text(
        "SELECT e.id, e.claim_id, e.entity_id, e.source_name, e.source_url, e.title, "
        "e.snippet, e.grade, e.match_method, e.match_confidence, e.accessed_at "
        "FROM evidence e JOIN resume_claim c ON c.id = e.claim_id "
        "JOIN resume_version v ON v.id = c.resume_version_id "
        "JOIN resume r ON r.id = v.resume_id WHERE r.candidate_id = :candidate "
        "AND e.tenant_id = :tenant ORDER BY e.accessed_at DESC LIMIT :limit"
    ), {"candidate": candidate_id, "tenant": user.tenant_id,
        "limit": limit})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/evidence/{evidence_id}")
async def get_evidence(evidence_id: UUID, user: Principal = Depends(hr),
                       session: AsyncSession = Depends(get_session)):
    row = await require_evidence(session, user, evidence_id)
    row.pop("content_hash")
    row.pop("snapshot_uri")
    return row


@router.post("/evidence/{evidence_id}/confirm")
async def confirm_evidence(evidence_id: UUID, user: Principal = Depends(hr),
                           session: AsyncSession = Depends(get_session)):
    await require_evidence(session, user, evidence_id)
    await session.execute(text(
        "UPDATE evidence SET verified_by = :user WHERE id = :id"
    ), {"id": evidence_id, "user": user.id})
    await session.commit()
    return {"id": evidence_id, "confirmed_by": user.id,
            "note": "人工确认仅代表复核匹配，不证明候选人个人贡献"}
