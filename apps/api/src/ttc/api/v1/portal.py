"""求职者端（候选人门户）接口。

与 HR 工作台共用同一套认证与数据表；本模块只提供候选人视角的只读视图和
投递动作，不改动既有 `/api/v1` 端点的行为：

- 岗位广场只暴露 `published` 岗位；
- 候选人只能看到 `candidate.user_id = 当前登录人` 的记录；
- 投递复用 `resumes.upload_resume`，因此 MIME、大小、去重与解析队列行为一致；
- 匹配复用 `match.match_resume`，与招聘端看到的是同一份 assessment。
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, require_roles
from ttc.api.v1.auth import issue_tokens
from ttc.api.v1.jobs import require_job
from ttc.api.v1.match import MatchInput, match_resume
from ttc.api.v1.resumes import upload_resume
from ttc.api.v1.voice import require_session
from ttc.core.audit import record_audit
from ttc.core.config import get_settings
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import hash_password, uuid7

router = APIRouter(tags=["portal"])
candidate_role = require_roles("candidate")


class RegisterInput(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class ProfileInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


async def my_candidate(session: AsyncSession, user: Principal) -> dict | None:
    row = (await session.execute(
        text("SELECT id, tenant_id, user_id, display_name, contact_masked, source::text AS source, "
             "job_id, is_synthetic, created_at FROM candidate "
             "WHERE user_id = :user AND tenant_id = :tenant"),
        {"user": user.id, "tenant": user.tenant_id},
    )).mappings().one_or_none()
    return dict(row) if row is not None else None


async def require_my_candidate(session: AsyncSession, user: Principal) -> dict:
    candidate = await my_candidate(session, user)
    if candidate is None:
        raise TTCError("TTC-2001", "请先完善求职档案", 409)
    return candidate


async def ensure_consent(session: AsyncSession, user: Principal, candidate_id: UUID,
                         purpose: str, text_version: str) -> UUID:
    existing = (await session.execute(text(
        "SELECT id FROM consent WHERE candidate_id = :candidate "
        "AND purpose = CAST(:purpose AS consent_purpose) AND status = 'granted' "
        "AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now()) "
        "ORDER BY accepted_at DESC NULLS LAST, created_at DESC LIMIT 1"
    ), {"candidate": candidate_id, "purpose": purpose})).scalar_one_or_none()
    if existing is not None:
        return existing
    consent_id = uuid7()
    await session.execute(text(
        "INSERT INTO consent (id, candidate_id, purpose, status, scope, text_version, "
        "accepted_at) VALUES (:id, :candidate, CAST(:purpose AS consent_purpose), "
        "'granted', CAST(:scope AS jsonb), :version, now())"
    ), {"id": consent_id, "candidate": candidate_id, "purpose": purpose,
        "scope": json.dumps({"channel": "candidate_portal"}, ensure_ascii=False),
        "version": text_version})
    await record_audit(session, user, "consent.grant", "consent", consent_id)
    return consent_id


def job_public_row(row: dict) -> dict:
    structured = row.get("structured") or {}
    skills = structured.get("skills") if isinstance(structured, dict) else None
    if not isinstance(skills, list):
        skills = []
    jd = (row.get("jd_text") or "").strip()
    return {
        "id": row["id"],
        "title": row["title"],
        "department": row["department"],
        "headcount": row["headcount"],
        "published_at": row["published_at"],
        "summary": jd[:180] + ("…" if len(jd) > 180 else ""),
        "skills": [str(item) for item in skills][:6],
    }


@router.post("/portal/register", status_code=201)
async def register(body: RegisterInput, session: AsyncSession = Depends(get_session)):
    tenant = (await session.execute(
        text("SELECT id, name FROM tenant WHERE slug = :slug"), {"slug": body.tenant_slug}
    )).mappings().one_or_none()
    if tenant is None:
        raise TTCError("TTC-2001", "企业标识不存在", 404)
    email = body.email.strip().lower()
    exists = (await session.execute(
        text("SELECT 1 FROM app_user WHERE tenant_id = :tenant AND email = :email"),
        {"tenant": tenant["id"], "email": email},
    )).scalar_one_or_none()
    if exists is not None:
        raise TTCError("TTC-2002", "该邮箱已注册", 409)
    user_id, candidate_id = uuid7(), uuid7()
    await session.execute(text(
        "INSERT INTO app_user (id, tenant_id, email, display_name, password_hash, role) "
        "VALUES (:id, :tenant, :email, :name, :password, 'candidate')"
    ), {"id": user_id, "tenant": tenant["id"], "email": email,
        "name": body.display_name, "password": hash_password(body.password)})
    await session.execute(text(
        "INSERT INTO candidate (id, tenant_id, user_id, display_name, source, is_synthetic) "
        "VALUES (:id, :tenant, :user, :name, 'upload', false)"
    ), {"id": candidate_id, "tenant": tenant["id"], "user": user_id,
        "name": body.display_name})
    tokens = await issue_tokens(session, user_id)
    await session.commit()
    return {"tenant_slug": body.tenant_slug, "candidate_id": candidate_id, **tokens}


@router.get("/portal/profile")
async def profile(user: Principal = Depends(candidate_role),
                  session: AsyncSession = Depends(get_session)):
    account = (await session.execute(text(
        "SELECT u.email, u.display_name, t.slug AS tenant_slug, t.name AS tenant_name "
        "FROM app_user u JOIN tenant t ON t.id = u.tenant_id WHERE u.id = :id"
    ), {"id": user.id})).mappings().one()
    candidate = await my_candidate(session, user)
    consents: list[dict] = []
    privacy: list[dict] = []
    if candidate is not None:
        consents = [dict(row) for row in (await session.execute(text(
            "SELECT id, purpose::text AS purpose, status::text AS status, accepted_at, "
            "revoked_at, expires_at FROM consent WHERE candidate_id = :candidate "
            "ORDER BY created_at DESC"
        ), {"candidate": candidate["id"]})).mappings().all()]
        privacy = [dict(row) for row in (await session.execute(text(
            "SELECT id, request_type::text, status::text, payload, result, created_at, "
            "completed_at FROM privacy_request WHERE requester_id = :user "
            "AND tenant_id = :tenant ORDER BY created_at DESC"
        ), {"user": user.id, "tenant": user.tenant_id})).mappings().all()]
    return {"account": dict(account), "candidate": candidate,
            "consents": consents, "privacy_requests": privacy}


@router.post("/portal/profile")
async def upsert_profile(body: ProfileInput, user: Principal = Depends(candidate_role),
                         session: AsyncSession = Depends(get_session)):
    candidate = await my_candidate(session, user)
    if candidate is None:
        candidate_id = uuid7()
        await session.execute(text(
            "INSERT INTO candidate (id, tenant_id, user_id, display_name, source, is_synthetic) "
            "VALUES (:id, :tenant, :user, :name, 'upload', false)"
        ), {"id": candidate_id, "tenant": user.tenant_id, "user": user.id,
            "name": body.display_name})
    else:
        candidate_id = candidate["id"]
        await session.execute(text(
            "UPDATE candidate SET display_name = :name WHERE id = :id"
        ), {"name": body.display_name, "id": candidate_id})
    await session.commit()
    return await my_candidate(session, user)


@router.get("/portal/jobs")
async def list_public_jobs(user: Principal = Depends(candidate_role),
                           session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(text(
        "SELECT j.id, j.title, j.department, j.headcount, j.published_at, "
        "v.jd_text, v.structured "
        "FROM job j LEFT JOIN LATERAL ("
        "  SELECT vv.id, vv.jd_text, vv.structured FROM job_version vv "
        "  WHERE vv.job_id = j.id "
        "  ORDER BY (vv.id = j.current_version_id) DESC, vv.version_no DESC LIMIT 1"
        ") v ON true "
        "WHERE j.tenant_id = :tenant AND j.status = 'published' "
        "ORDER BY j.published_at DESC NULLS LAST, j.created_at DESC"
    ), {"tenant": user.tenant_id})).mappings().all()
    candidate = await my_candidate(session, user)
    applied: set[UUID] = set()
    if candidate is not None:
        applied = {row[0] for row in (await session.execute(text(
            "SELECT job_id FROM application WHERE candidate_id = :candidate"
        ), {"candidate": candidate["id"]})).all()}
    items = []
    for row in rows:
        item = job_public_row(dict(row))
        item["applied"] = row["id"] in applied
        items.append(item)
    return {"items": items}


@router.get("/portal/jobs/{job_id}")
async def public_job(job_id: UUID, user: Principal = Depends(candidate_role),
                     session: AsyncSession = Depends(get_session)):
    job = await require_job(session, user, job_id)
    if job["status"] != "published":
        raise TTCError("TTC-2001", "岗位不存在或未发布", 404)
    version = (await session.execute(text(
        "SELECT id, jd_text, structured, version_no FROM job_version WHERE job_id = :job "
        "ORDER BY (id = :current) DESC, version_no DESC LIMIT 1"
    ), {"job": job_id, "current": job["current_version_id"]})).mappings().one_or_none()
    candidate = await my_candidate(session, user)
    application_id = None
    if candidate is not None:
        application_id = (await session.execute(text(
            "SELECT id FROM application WHERE candidate_id = :candidate AND job_id = :job"
        ), {"candidate": candidate["id"], "job": job_id})).scalar_one_or_none()
    return {
        "id": job["id"], "title": job["title"], "department": job["department"],
        "headcount": job["headcount"], "published_at": job["published_at"],
        "jd_text": version["jd_text"] if version else "",
        "structured": version["structured"] if version else {},
        "application_id": application_id,
        "has_profile": candidate is not None,
    }


@router.post("/portal/applications", status_code=202)
async def create_application(
    job_id: UUID = Form(),
    file: UploadFile = File(),
    acknowledged: bool = Form(default=False),
    consent_version: str = Form(default="v1"),
    user: Principal = Depends(candidate_role),
    session: AsyncSession = Depends(get_session),
):
    candidate = await require_my_candidate(session, user)
    job = await require_job(session, user, job_id)
    if job["status"] != "published":
        raise TTCError("TTC-2002", "岗位未发布或已关闭", 409)
    if acknowledged:
        await ensure_consent(session, user, candidate["id"], "resume_process", consent_version)
    uploaded = await upload_resume(candidate_id=candidate["id"], job_id=job_id,
                                   file=file, user=user, session=session)
    application_id = (await session.execute(text(
        "INSERT INTO application (id, tenant_id, candidate_id, job_id, resume_id, status) "
        "VALUES (:id, :tenant, :candidate, :job, :resume, 'submitted') "
        "ON CONFLICT (candidate_id, job_id) DO UPDATE SET resume_id = EXCLUDED.resume_id, "
        "status = 'submitted', updated_at = now() RETURNING id"
    ), {"id": uuid7(), "tenant": user.tenant_id, "candidate": candidate["id"],
        "job": job_id, "resume": uploaded["resume_id"]})).scalar_one()
    await session.commit()
    return {"application_id": application_id, **uploaded}


@router.get("/portal/applications")
async def list_applications(user: Principal = Depends(candidate_role),
                            session: AsyncSession = Depends(get_session)):
    candidate = await my_candidate(session, user)
    if candidate is None:
        return {"items": []}
    rows = (await session.execute(text(
        "SELECT ap.id, ap.status, ap.created_at, ap.updated_at, "
        "j.id AS job_id, j.title, j.department, "
        "r.id AS resume_id, r.file_name, r.parse_status, "
        "asmt.match_score, asmt.status AS assessment_status, "
        "vs.id AS interview_id, vs.status AS interview_status "
        "FROM application ap JOIN job j ON j.id = ap.job_id "
        "LEFT JOIN resume r ON r.id = ap.resume_id "
        "LEFT JOIN LATERAL ("
        "  SELECT a2.match_score, a2.status FROM assessment a2 "
        "  WHERE a2.candidate_id = ap.candidate_id AND a2.job_id = ap.job_id "
        "  ORDER BY a2.updated_at DESC LIMIT 1"
        ") asmt ON true "
        "LEFT JOIN LATERAL ("
        "  SELECT v2.id, v2.status::text AS status FROM voice_session v2 "
        "  WHERE v2.candidate_id = ap.candidate_id AND v2.job_id = ap.job_id "
        "  ORDER BY v2.created_at DESC LIMIT 1"
        ") vs ON true "
        "WHERE ap.candidate_id = :candidate ORDER BY ap.created_at DESC"
    ), {"candidate": candidate["id"]})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/portal/applications/{application_id}")
async def application_detail(application_id: UUID,
                             user: Principal = Depends(candidate_role),
                             session: AsyncSession = Depends(get_session)):
    candidate = await require_my_candidate(session, user)
    row = (await session.execute(text(
        "SELECT ap.id, ap.status, ap.created_at, ap.updated_at, ap.candidate_id, "
        "j.id AS job_id, j.title, j.department, j.published_at, "
        "r.id AS resume_id, r.file_name, r.parse_status, r.size_bytes, r.created_at AS uploaded_at "
        "FROM application ap JOIN job j ON j.id = ap.job_id "
        "LEFT JOIN resume r ON r.id = ap.resume_id "
        "WHERE ap.id = :id AND ap.candidate_id = :candidate"
    ), {"id": application_id, "candidate": candidate["id"]})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "投递记录不存在", 404)
    assessment = (await session.execute(text(
        "SELECT id, match_score, evidence_score, status, report_json, model_version, updated_at "
        "FROM assessment WHERE candidate_id = :candidate AND job_id = :job "
        "ORDER BY updated_at DESC LIMIT 1"
    ), {"candidate": candidate["id"], "job": row["job_id"]})).mappings().one_or_none()
    dimensions: list[dict] = []
    if assessment is not None:
        dimensions = [dict(item) for item in (await session.execute(text(
            "SELECT dimension_key, label, weight_pct, score, "
            "evidence_state::text AS evidence_state, "
            "reasoning, status FROM dimension_score WHERE assessment_id = :id "
            "ORDER BY weight_pct DESC"
        ), {"id": assessment["id"]})).mappings().all()]
    sessions = [dict(item) for item in (await session.execute(text(
        "SELECT id, status::text AS status, scenario::text AS scenario, created_at, "
        "started_at, ended_at, end_reason FROM voice_session "
        "WHERE candidate_id = :candidate AND job_id = :job ORDER BY created_at DESC"
    ), {"candidate": candidate["id"], "job": row["job_id"]})).mappings().all()]
    return {**dict(row), "assessment": dict(assessment) if assessment else None,
            "dimensions": dimensions, "interviews": sessions}


@router.post("/portal/applications/{application_id}/match")
async def run_application_match(application_id: UUID,
                                user: Principal = Depends(candidate_role),
                                session: AsyncSession = Depends(get_session)):
    candidate = await require_my_candidate(session, user)
    row = (await session.execute(text(
        "SELECT id, job_id, resume_id FROM application "
        "WHERE id = :id AND candidate_id = :candidate"
    ), {"id": application_id, "candidate": candidate["id"]})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "投递记录不存在", 404)
    if row["resume_id"] is None:
        raise TTCError("TTC-2002", "请先上传简历", 409)
    return await match_resume(row["resume_id"], MatchInput(job_id=row["job_id"]),
                              user=user, session=session)


@router.get("/portal/interviews")
async def list_interviews(user: Principal = Depends(candidate_role),
                          session: AsyncSession = Depends(get_session)):
    candidate = await my_candidate(session, user)
    if candidate is None:
        return {"items": []}
    rows = (await session.execute(text(
        "SELECT v.id, v.status::text AS status, v.scenario::text AS scenario, "
        "v.created_at, v.started_at, v.ended_at, v.end_reason, v.max_seconds, "
        "j.id AS job_id, j.title, "
        "COALESCE(jsonb_array_length(v.plan_json->'questions'), 0) AS question_count "
        "FROM voice_session v JOIN job j ON j.id = v.job_id "
        "WHERE v.candidate_id = :candidate ORDER BY v.created_at DESC"
    ), {"candidate": candidate["id"]})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/portal/interviews/{session_id}")
async def interview_detail(session_id: UUID, user: Principal = Depends(candidate_role),
                           session: AsyncSession = Depends(get_session)):
    row = await require_session(session, user, session_id)
    settings = get_settings()
    if settings.realtime_api_key and settings.realtime_model:
        live_transport = "sdp"
    elif settings.dashscope_api_key:
        live_transport = "relay"
    else:
        live_transport = None
    return {
        "id": row["id"], "job_id": row["job_id"], "scenario": row["scenario"],
        "status": row["status"], "plan": row["plan_json"], "max_seconds": row["max_seconds"],
        "created_at": row["created_at"], "started_at": row["started_at"],
        "ended_at": row["ended_at"], "end_reason": row["end_reason"],
        "live_ready": live_transport is not None,
        "live_transport": live_transport,
    }
