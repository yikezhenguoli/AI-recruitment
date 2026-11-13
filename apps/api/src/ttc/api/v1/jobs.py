import json
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, require_roles
from ttc.core.config import get_settings
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7

router = APIRouter(tags=["jobs"])
hr = require_roles("hr", "admin")
admin = require_roles("admin")

DEFAULT_DIMENSIONS = [
    {"key": "skill_coverage", "label": "岗位技能覆盖", "weight_pct": 30},
    {"key": "project_depth", "label": "项目与工作深度", "weight_pct": 25},
    {"key": "ownership_clarity", "label": "个人贡献清晰度", "weight_pct": 20},
    {"key": "problem_solving", "label": "问题分析与工程能力", "weight_pct": 15},
    {"key": "intent_fit", "label": "求职意愿与条件匹配", "weight_pct": 10},
]


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    department: str | None = None
    headcount: int | None = Field(default=None, gt=0)
    jd_text: str | None = Field(default=None, min_length=20, max_length=20000)


class JobPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    department: str | None = None
    headcount: int | None = Field(default=None, gt=0)


class JDVersionCreate(BaseModel):
    jd_text: str = Field(min_length=20, max_length=20000)
    structured: dict


class JDExtract(BaseModel):
    jd_text: str = Field(min_length=20, max_length=20000)


class JDGenerate(BaseModel):
    prompt: str = Field(min_length=10, max_length=5000)
    polish_first: bool = False
    variants: int = Field(default=1, ge=1, le=3)


async def generate_jd_json(prompt: str, *, mode: str) -> dict:
    settings = get_settings()
    if not all((settings.llm_base_url, settings.llm_api_key, settings.llm_model)):
        raise TTCError("TTC-5004", "尚未配置岗位描述模型", 503)
    task = ("仅从原文抽取岗位要求，缺失项写null并在warnings中说明，不要推断。"
            if mode == "extract" else
            "生成完整招聘JD，需有岗位名称与职责，不补写未提供的公司、薪资、院校、年龄、婚育。")
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={"model": settings.llm_model, "temperature": 0 if mode == "extract" else .7,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": task +
                                    "只输出JSON对象{jd_text:string,structured:"
                                    "{role_title:string,responsibilities:[string]},warnings:[object]}"},
                                   {"role": "user", "content": prompt}]},
            )
            response.raise_for_status()
            result = json.loads(response.json()["choices"][0]["message"]["content"])
            if not isinstance(result["structured"], dict):
                raise ValueError("Invalid structured JSON")
            if mode == "generate" and (not result["structured"].get("role_title") or
                                       not result["structured"].get("responsibilities") or
                                       not 20 <= len(result["jd_text"]) <= 20000):
                raise ValueError("Generated JD failed validation")
            return result
    except (httpx.HTTPError, ValueError, IndexError, KeyError, TypeError) as exc:
        raise TTCError("TTC-5002", "岗位模型不可用或输出不符合契约", 502) from exc


class WeightDimension(BaseModel):
    key: str
    label: str
    weight_pct: Decimal = Field(ge=0, le=100)
    description: str | None = None


class WeightInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    mode: Literal["auto", "template", "custom"] = "custom"
    dimensions: list[WeightDimension] = Field(min_length=1)


async def require_job(session: AsyncSession, user: Principal, job_id: UUID, *, lock=False):
    query = ("SELECT * FROM job WHERE id = :id AND tenant_id = :tenant" +
             (" FOR UPDATE" if lock else ""))
    row = (await session.execute(text(query), {"id": job_id, "tenant": user.tenant_id})).mappings()
    job = row.one_or_none()
    if job is None:
        raise TTCError("TTC-2001", "岗位不存在", 404)
    return dict(job)


async def add_version(session: AsyncSession, job_id: UUID, user_id: UUID,
                      jd_text: str, structured: dict) -> dict:
    number = (await session.execute(
        text("SELECT COALESCE(MAX(version_no), 0) + 1 FROM job_version WHERE job_id = :id"),
        {"id": job_id},
    )).scalar_one()
    version_id = uuid7()
    row = (await session.execute(
        text("INSERT INTO job_version (id, job_id, version_no, jd_text, structured, "
             "source, created_by) VALUES (:id, :job, :number, :jd, CAST(:data AS jsonb), "
             "'manual', :user) RETURNING id, version_no, jd_text, structured, source, created_at"),
        {"id": version_id, "job": job_id, "number": number,
         "jd": jd_text, "data": json.dumps(structured, ensure_ascii=False), "user": user_id},
    )).mappings().one()
    return dict(row)


@router.post("/jobs", status_code=201)
async def create_job(body: JobCreate, user: Principal = Depends(hr),
                     session: AsyncSession = Depends(get_session)):
    job_id = uuid7()
    await session.execute(
        text("INSERT INTO job (id, tenant_id, owner_id, title, department, headcount) "
             "VALUES (:id, :tenant, :owner, :title, :department, :headcount)"),
        {"id": job_id, "tenant": user.tenant_id, "owner": user.id,
         "title": body.title, "department": body.department, "headcount": body.headcount},
    )
    current_version = None
    if body.jd_text:
        current_version = await add_version(
            session, job_id, user.id, body.jd_text, {"role_title": body.title}
        )
        await session.execute(
            text("UPDATE job SET current_version_id = :version WHERE id = :id"),
            {"version": current_version["id"], "id": job_id},
        )
    plan_id = uuid7()
    await session.execute(
        text("INSERT INTO weight_plan (id, tenant_id, job_id, name, mode, dimensions) "
             "VALUES (:id, :tenant, :job, '默认岗位权重', 'auto', CAST(:dims AS jsonb))"),
        {"id": plan_id, "tenant": user.tenant_id, "job": job_id,
         "dims": json.dumps(DEFAULT_DIMENSIONS, ensure_ascii=False)},
    )
    await session.commit()
    return {"id": job_id, "title": body.title, "status": "draft",
            "current_version": current_version, "weight_plan": {"id": plan_id,
            "mode": "auto", "dimensions": DEFAULT_DIMENSIONS}}


@router.get("/jobs")
async def list_jobs(status: Literal["draft", "published", "locked", "archived"] | None = None,
                    department: str | None = None, limit: int = Query(20, ge=1, le=100),
                    user: Principal = Depends(hr), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        text("SELECT id, title, department, status, headcount, current_version_id, "
             "created_at, updated_at FROM job WHERE tenant_id = :tenant "
             "AND (CAST(:status AS text) IS NULL OR status::text = CAST(:status AS text)) "
             "AND (CAST(:department AS text) IS NULL OR department = CAST(:department AS text)) "
             "ORDER BY created_at DESC, id DESC LIMIT :limit"),
        {"tenant": user.tenant_id, "status": status, "department": department,
         "limit": limit},
    )).mappings().all()
    return {"items": [dict(row) for row in rows], "next_cursor": None}


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID, user: Principal = Depends(hr),
                  session: AsyncSession = Depends(get_session)):
    job = await require_job(session, user, job_id)
    version = (await session.execute(
        text("SELECT id, version_no, jd_text, structured, source FROM job_version "
             "WHERE id = :id"), {"id": job["current_version_id"]},
    )).mappings().one_or_none()
    job["current_version"] = dict(version) if version else None
    return job


@router.patch("/jobs/{job_id}")
async def patch_job(job_id: UUID, body: JobPatch,
                    if_match: str | None = Header(default=None, alias="If-Match"),
                    user: Principal = Depends(hr), session: AsyncSession = Depends(get_session)):
    job = await require_job(session, user, job_id)
    if job["status"] in ("locked", "archived"):
        raise TTCError("TTC-2002", "岗位已锁定或归档", 409)
    if if_match is None:
        raise TTCError("TTC-2003", "需要 If-Match 版本时间", 409)
    try:
        expected = datetime.fromisoformat(if_match.strip('"'))
    except ValueError as exc:
        raise TTCError("TTC-2003", "版本时间格式无效", 409) from exc
    if expected.tzinfo is None:
        raise TTCError("TTC-2003", "版本时间必须包含时区", 409)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return job
    if "title" in changes and changes["title"] is None:
        raise TTCError("TTC-2002", "岗位名称不能为空", 409)
    changes.update({"id": job_id, "tenant": user.tenant_id, "expected": expected})
    result = await session.execute(
        text("UPDATE job SET title = COALESCE(:title, title), department = :department, "
             "headcount = :headcount, updated_at = now() "
             "WHERE id = :id AND tenant_id = :tenant AND updated_at = :expected "
             "RETURNING id, title, department, headcount, updated_at"),
        {**changes, "title": changes.get("title", job["title"]),
         "department": changes.get("department", job["department"]),
         "headcount": changes.get("headcount", job["headcount"])},
    )
    updated = result.mappings().one_or_none()
    if updated is None:
        raise TTCError("TTC-2003", "岗位版本冲突，请重新获取", 409)
    await session.commit()
    return dict(updated)


@router.delete("/jobs/{job_id}")
async def archive_job(job_id: UUID, user: Principal = Depends(admin),
                      session: AsyncSession = Depends(get_session)):
    await require_job(session, user, job_id)
    await session.execute(
        text("UPDATE job SET status = 'archived', archived_at = now(), updated_at = now() "
             "WHERE id = :id AND tenant_id = :tenant"),
        {"id": job_id, "tenant": user.tenant_id},
    )
    await session.commit()
    return {"id": job_id, "status": "archived"}


@router.get("/jobs/{job_id}/jd/versions")
async def versions(job_id: UUID, user: Principal = Depends(hr),
                   session: AsyncSession = Depends(get_session)):
    await require_job(session, user, job_id)
    rows = (await session.execute(
        text("SELECT id, version_no, jd_text, structured, source, is_saved, created_at "
             "FROM job_version WHERE job_id = :id ORDER BY version_no DESC"), {"id": job_id},
    )).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/jobs/{job_id}/jd/extract")
async def extract_jd(job_id: UUID, body: JDExtract, user: Principal = Depends(hr),
                     session: AsyncSession = Depends(get_session)):
    await require_job(session, user, job_id)
    result = await generate_jd_json(body.jd_text, mode="extract")
    return {"structured": result["structured"], "warnings": result.get("warnings", [])}


@router.post("/jobs/{job_id}/jd/generate")
async def generate_jd(job_id: UUID, body: JDGenerate, user: Principal = Depends(hr),
                      session: AsyncSession = Depends(get_session)):
    job = await require_job(session, user, job_id, lock=True)
    if job["status"] in ("locked", "archived"):
        raise TTCError("TTC-2002", "岗位已锁定或归档", 409)
    recent = (await session.execute(text(
        "SELECT count(DISTINCT generation_id) FROM job_version WHERE job_id = :id "
        "AND generation_id IS NOT NULL AND created_at > now() - interval '60 seconds'"
    ), {"id": job_id})).scalar_one()
    if recent >= 3:
        raise TTCError("TTC-4002", "岗位描述生成过于频繁", 429)
    if body.polish_first:
        return {"generation_id": None, "versions": [],
                "suggestions": ["明确岗位职责", "说明必要技能与优先技能", "补充可核验的工作背景"]}
    results = []
    for _ in range(body.variants):
        results.append(await generate_jd_json(body.prompt, mode="generate"))
    generation_id = uuid7()
    versions = []
    for result in results:
        version = await add_version(session, job_id, user.id, result["jd_text"],
                                    result["structured"])
        await session.execute(text(
            "UPDATE job_version SET source = 'ai_generated', generation_id = :generation "
            "WHERE id = :id"
        ), {"generation": generation_id, "id": version["id"]})
        versions.append({**version, "source": "ai_generated", "is_saved": False})
    await session.commit()
    return {"generation_id": generation_id, "versions": versions}


@router.post("/jobs/{job_id}/jd/versions", status_code=201)
async def create_version(job_id: UUID, body: JDVersionCreate, user: Principal = Depends(hr),
                         session: AsyncSession = Depends(get_session)):
    job = await require_job(session, user, job_id, lock=True)
    if job["status"] in ("locked", "archived"):
        raise TTCError("TTC-2002", "岗位已锁定或归档", 409)
    created = await add_version(session, job_id, user.id, body.jd_text, body.structured)
    await session.commit()
    return created


@router.post("/jobs/{job_id}/jd/versions/{version_id}/select")
async def select_version(job_id: UUID, version_id: UUID, user: Principal = Depends(hr),
                         session: AsyncSession = Depends(get_session)):
    job = await require_job(session, user, job_id, lock=True)
    if job["status"] in ("locked", "archived"):
        raise TTCError("TTC-2002", "岗位已锁定或归档", 409)
    version = (await session.execute(
        text("SELECT id FROM job_version WHERE id = :id AND job_id = :job"),
        {"id": version_id, "job": job_id},
    )).scalar_one_or_none()
    if version is None:
        raise TTCError("TTC-2001", "岗位版本不存在", 404)
    await session.execute(
        text("UPDATE job SET current_version_id = :version, updated_at = now() WHERE id = :job"),
        {"version": version_id, "job": job_id},
    )
    await session.execute(text("UPDATE job_version SET is_saved = true WHERE id = :id"),
                          {"id": version_id})
    await session.commit()
    return {"id": job_id, "current_version_id": version_id}


@router.post("/jobs/{job_id}/publish")
async def publish(job_id: UUID, user: Principal = Depends(hr),
                  session: AsyncSession = Depends(get_session)):
    job = await require_job(session, user, job_id, lock=True)
    if job["status"] != "draft" or not job["current_version_id"]:
        raise TTCError("TTC-2002", "需要草稿岗位及已选定 JD 版本", 409)
    await session.execute(
        text("UPDATE job SET status = 'published', published_at = now(), "
             "updated_at = now() WHERE id = :id"), {"id": job_id},
    )
    await session.commit()
    return {"id": job_id, "status": "published",
            "current_version_id": job["current_version_id"]}


@router.get("/jobs/{job_id}/stats")
async def stats(job_id: UUID, user: Principal = Depends(hr),
                session: AsyncSession = Depends(get_session)):
    await require_job(session, user, job_id)
    result = (await session.execute(
        text("SELECT (SELECT count(*) FROM candidate WHERE job_id = :id) AS candidates, "
             "(SELECT count(*) FROM assessment WHERE job_id = :id) AS assessments, "
             "(SELECT count(*) FROM voice_session WHERE job_id = :id) AS voice_sessions"),
        {"id": job_id},
    )).mappings().one()
    return dict(result)


@router.get("/weight-plans/templates")
async def weight_templates(user: Principal = Depends(hr)):
    return {"items": [{"name": "默认岗位权重", "mode": "auto",
                       "dimensions": DEFAULT_DIMENSIONS}]}


@router.put("/jobs/{job_id}/weight-plan")
async def set_weight_plan(job_id: UUID, body: WeightInput, user: Principal = Depends(hr),
                          session: AsyncSession = Depends(get_session)):
    job = await require_job(session, user, job_id, lock=True)
    if job["status"] in ("locked", "archived"):
        raise TTCError("TTC-2002", "岗位已锁定或归档", 409)
    if len({dim.key for dim in body.dimensions}) != len(body.dimensions) or sum(
        (dim.weight_pct for dim in body.dimensions), Decimal(0)
    ) != 100:
        raise TTCError("TTC-2002", "权重键不可重复，且权重合计必须为 100", 409)
    await session.execute(
        text("UPDATE weight_plan SET is_active = false, updated_at = now() "
             "WHERE job_id = :job AND tenant_id = :tenant AND is_active"),
        {"job": job_id, "tenant": user.tenant_id},
    )
    plan_id = uuid7()
    await session.execute(
        text("INSERT INTO weight_plan (id, tenant_id, job_id, name, mode, dimensions) "
             "VALUES (:id, :tenant, :job, :name, CAST(:mode AS weight_mode), "
             "CAST(:dims AS jsonb))"),
        {"id": plan_id, "tenant": user.tenant_id, "job": job_id, "name": body.name,
         "mode": body.mode,
         "dims": json.dumps([dim.model_dump(mode="json", exclude_none=True)
                             for dim in body.dimensions], ensure_ascii=False)},
    )
    await session.commit()
    return {"id": plan_id, "job_id": job_id, "mode": body.mode,
            "dimensions": body.dimensions}


@router.get("/jobs/{job_id}/interview-plans")
async def interview_plans(job_id: UUID, user: Principal = Depends(hr),
                          session: AsyncSession = Depends(get_session)):
    await require_job(session, user, job_id)
    rows = (await session.execute(
        text("SELECT id, name, duration_min, rounds, dimensions FROM interview_plan "
             "WHERE tenant_id = :tenant AND (job_id = :job OR job_id IS NULL) "
             "AND is_active ORDER BY created_at DESC LIMIT 100"),
        {"tenant": user.tenant_id, "job": job_id},
    )).mappings().all()
    return {"items": [dict(row) for row in rows]}
