import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.api.deps import Principal, current_user, require_roles
from ttc.api.v1.candidates import require_candidate
from ttc.api.v1.jobs import require_job
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7

router = APIRouter(tags=["assessments"])
hr = require_roles("hr", "admin")
CLAIM_MAP = {
    "skill_coverage": ("skill", "work", "project"),
    "project_depth": ("project", "work"),
    "ownership_clarity": ("project", "work"),
    "problem_solving": ("project", "work"),
    "intent_fit": (),
}


class AssessmentInput(BaseModel):
    job_id: UUID


class RevisionInput(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    dimensions: dict[str, str] = Field(default_factory=dict)


async def require_assessment(session: AsyncSession, user: Principal, assessment_id: UUID):
    row = (await session.execute(text(
        "SELECT a.* FROM assessment a JOIN candidate c ON c.id = a.candidate_id "
        "WHERE a.id = :id AND c.tenant_id = :tenant"
    ), {"id": assessment_id, "tenant": user.tenant_id})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "评估不存在", 404)
    if user.role == "candidate":
        await require_candidate(session, user, row["candidate_id"])
    elif user.role not in ("hr", "admin"):
        raise TTCError("TTC-1002", "无权访问评估", 403)
    return dict(row)


@router.post("/candidates/{candidate_id}/assessments", status_code=201)
async def create_assessment(candidate_id: UUID, body: AssessmentInput,
                            user: Principal = Depends(hr),
                            session: AsyncSession = Depends(get_session)):
    candidate = await require_candidate(session, user, candidate_id)
    job = await require_job(session, user, body.job_id)
    if job["status"] == "archived":
        raise TTCError("TTC-2002", "岗位已归档", 409)
    if candidate["job_id"] and candidate["job_id"] != body.job_id:
        raise TTCError("TTC-2002", "候选人不属于该岗位", 409)
    if not candidate["is_synthetic"]:
        from ttc.api.v1.consents import require_consent
        await require_consent(session, candidate_id, "resume_process")
    version = (await session.execute(text(
        "SELECT v.id FROM resume_version v JOIN resume r ON r.id = v.resume_id "
        "WHERE r.candidate_id = :candidate AND v.status = 'done' "
        "ORDER BY v.parsed_at DESC, v.version_no DESC LIMIT 1"
    ), {"candidate": candidate_id})).scalar_one_or_none()
    if version is None:
        raise TTCError("TTC-2002", "简历未解析完成", 409)
    plan = (await session.execute(text(
        "SELECT id, dimensions FROM weight_plan WHERE job_id = :job "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"job": body.job_id})).mappings().one_or_none()
    if plan is None:
        raise TTCError("TTC-2002", "岗位未配置权重", 409)
    existing = (await session.execute(text(
        "SELECT id FROM assessment WHERE candidate_id = :candidate AND job_id = :job "
        "AND resume_version_id = :version AND weight_plan_id = :plan"
    ), {"candidate": candidate_id, "job": body.job_id, "version": version,
        "plan": plan["id"]})).scalar_one_or_none()
    if existing:
        return await get_assessment(existing, user, session)
    jd = (await session.execute(text(
        "SELECT structured FROM job_version WHERE id = :id"
    ), {"id": job["current_version_id"]})).scalar_one_or_none()
    required_skills = (jd or {}).get("required_skills") or []
    if not isinstance(required_skills, list):
        required_skills = []
    required_skills = [skill.strip().casefold() for skill in required_skills
                       if isinstance(skill, str) and skill.strip()]
    claims = (await session.execute(text(
        "SELECT id, claim_type::text AS type, normalized FROM resume_claim "
        "WHERE resume_version_id = :version"
    ), {"version": version})).mappings().all()
    evidence = (await session.execute(text(
        "SELECT e.id, e.claim_id, e.grade::text AS grade, e.accessed_at "
        "FROM evidence e JOIN resume_claim c ON c.id = e.claim_id "
        "WHERE c.resume_version_id = :version AND e.tenant_id = :tenant"
    ), {"version": version, "tenant": user.tenant_id})).mappings().all()
    by_claim = {}
    for item in evidence:
        by_claim.setdefault(item["claim_id"], []).append(item)
    verifiable = [c for c in claims if c["type"] in ("education", "work", "publication",
                                                      "patent", "award", "project")]
    supported = sum(any(e["grade"] in ("A", "B") for e in by_claim.get(c["id"], []))
                    for c in verifiable)
    grade_weights = {"A": 4, "B": 3, "C": 2, "D": 1}
    grade_quality = (sum(grade_weights[e["grade"]] for e in evidence) /
                     (4 * len(evidence)) if evidence else 0)
    freshness = (sum(1 - min((datetime.now(UTC) - e["accessed_at"]).days / 365, 5) / 5
                     for e in evidence) / len(evidence) if evidence else 0)
    evidence_score = round(100 * (.45 * supported / len(verifiable) if verifiable else 0) +
                           100 * (.30 * grade_quality + .15 * freshness), 2)
    grade = "A" if evidence_score >= 85 else "B" if evidence_score >= 70 else (
        "C" if evidence_score >= 55 else "D")
    dimensions = []
    for spec in plan["dimensions"]:
        if spec["key"] == "skill_coverage":
            matched = [c for c in claims if c["type"] == "skill" and
                       any(str(c["normalized"].get("name", "")).strip().casefold() == skill
                           for skill in required_skills)]
        else:
            matched = [c for c in claims if c["type"] in CLAIM_MAP.get(spec["key"], ())]
        refs = [e for c in matched for e in by_claim.get(c["id"], [])]
        high = [e for e in refs if e["grade"] in ("A", "B")]
        state = ("strong" if len(high) >= 2 else "partial" if high or
                 len([e for e in refs if e["grade"] == "C"]) >= 2 else
                 "self_claim" if matched else "missing")
        ratio = min(1, len(matched) / 2)
        score = (round({"strong": 80, "partial": 60, "self_claim": 40}[state] +
                       {"strong": 15, "partial": 19, "self_claim": 19}[state] * ratio, 2)
                 if state != "missing" else None)
        if spec["key"] != "skill_coverage" or not required_skills:
            score = None
            state = "missing"
        if spec["key"] == "skill_coverage" and required_skills and score is not None:
            ratio = min(1, len({str(c["normalized"].get("name", "")).casefold()
                                for c in matched}) / len(set(required_skills)))
            score = round(40 + 19 * ratio, 2)
        dimensions.append({"key": spec["key"], "label": spec["label"],
                           "weight_pct": float(spec["weight_pct"]), "score": score,
                           "evidence_state": state, "evidence_ids": [e["id"] for e in refs],
                           "source_claim_ids": [c["id"] for c in matched],
                           "reasoning": ("仅对 JD 明确的必备技能做精确字符串匹配；"
                                         "其他维度需岗位专属考核，不做推断")})
    valid = [d for d in dimensions if d["score"] is not None]
    total_weight = sum(d["weight_pct"] for d in valid)
    match_score = (round(sum(d["score"] * d["weight_pct"] for d in valid) / total_weight, 2)
                   if total_weight >= 30 else None)
    report = {"meta": {"assessed_at": datetime.now(UTC).isoformat(),
                       "model_version": "deterministic-v1"},
              "evidence_ledger": {"score": evidence_score, "grade": grade,
                                  "coverage": {"supported": supported,
                                               "verifiable": len(verifiable)},
                                  "breakdown": {key: sum(e["grade"] == key for e in evidence)
                                                for key in grade_weights}},
              "match_ledger": {"score": match_score, "dimensions": dimensions},
              "limitations": ["简历自述不能证明真实性或岗位能力", "未核验一致性不计分",
                              "技能字符串匹配不是技能熟练度测试，其他维度尚未评估",
                              "有效权重不足30%时不出适配分"]}
    assessment_id = uuid7()
    await session.execute(text(
        "INSERT INTO assessment (id, candidate_id, job_id, resume_version_id, weight_plan_id, "
        "evidence_score, evidence_grade, match_score, status, report_json, model_version) "
        "VALUES (:id, :candidate, :job, :version, :plan, :score, CAST(:grade AS evidence_grade), "
        ":match, 'ready', CAST(:report AS jsonb), 'deterministic-v1')"
    ), {"id": assessment_id, "candidate": candidate_id, "job": body.job_id,
        "version": version, "plan": plan["id"], "score": evidence_score, "grade": grade,
        "match": match_score, "report": json.dumps(report, default=str, ensure_ascii=False)})
    for dimension in dimensions:
        await session.execute(text(
            "INSERT INTO dimension_score (id, assessment_id, dimension_key, label, weight_pct, "
            "score, evidence_state, evidence_ids, source_claim_ids, reasoning) VALUES "
            "(:id, :assessment, :key, :label, :weight, :score, CAST(:state AS evidence_state), "
            ":evidence, :claims, :reasoning)"
        ), {"id": uuid7(), "assessment": assessment_id, "key": dimension["key"],
            "label": dimension["label"], "weight": dimension["weight_pct"],
            "score": dimension["score"], "state": dimension["evidence_state"],
            "evidence": dimension["evidence_ids"], "claims": dimension["source_claim_ids"],
            "reasoning": dimension["reasoning"]})
    await session.commit()
    return await get_assessment(assessment_id, user, session)


@router.get("/assessments/{assessment_id}")
async def get_assessment(assessment_id: UUID, user: Principal = Depends(current_user),
                         session: AsyncSession = Depends(get_session)):
    row = await require_assessment(session, user, assessment_id)
    report = dict(row["report_json"] or {})
    if row["status"] == "revised":
        dimensions = (await session.execute(text(
            "SELECT dimension_key, reasoning, status FROM dimension_score "
            "WHERE assessment_id = :id"
        ), {"id": assessment_id})).mappings().all()
        revised = {item["dimension_key"]: item for item in dimensions}
        ledger = dict(report.get("match_ledger") or {})
        ledger["dimensions"] = [
            {**dimension, "reasoning": revised[dimension["key"]]["reasoning"],
             "status": revised[dimension["key"]]["status"]}
            if dimension["key"] in revised else dimension
            for dimension in ledger.get("dimensions", [])
        ]
        report["match_ledger"] = ledger
        report["human_review"] = {"status": "revised"}
    return {"id": row["id"], "candidate_id": row["candidate_id"],
            "job_id": row["job_id"], "status": row["status"],
            "report": report}


@router.get("/assessments/{assessment_id}/export")
async def export_assessment(assessment_id: UUID, user: Principal = Depends(hr),
                            session: AsyncSession = Depends(get_session)):
    assessment = await get_assessment(assessment_id, user, session)
    if not assessment["report"]:
        raise TTCError("TTC-2002", "评估报告尚未就绪", 409)
    return JSONResponse(
        jsonable_encoder(assessment["report"]),
        headers={"Content-Disposition": f'attachment; filename="assessment-{assessment_id}.json"'},
    )


@router.patch("/assessments/{assessment_id}")
async def revise_assessment(assessment_id: UUID, body: RevisionInput,
                            user: Principal = Depends(hr),
                            session: AsyncSession = Depends(get_session)):
    await require_assessment(session, user, assessment_id)
    if not body.dimensions:
        raise TTCError("TTC-4000", "至少提供一个维度的复核结论", 422)
    for key, note in body.dimensions.items():
        result = await session.execute(text(
            "UPDATE dimension_score SET reasoning = :reasoning, status = 'revised' "
            "WHERE assessment_id = :id AND dimension_key = :key RETURNING id"
        ), {"id": assessment_id, "key": key, "reasoning": note})
        if result.scalar_one_or_none() is None:
            await session.rollback()
            raise TTCError("TTC-2001", "维度不存在", 404)
    await session.execute(text(
        "INSERT INTO assessment_revision (id, assessment_id, editor_id, diff, note) "
        "VALUES (:id, :assessment, :editor, CAST(:diff AS jsonb), :note)"
    ), {"id": uuid7(), "assessment": assessment_id, "editor": user.id,
        "diff": json.dumps(body.dimensions, ensure_ascii=False), "note": body.note})
    await session.execute(text(
        "UPDATE assessment SET status = 'revised', updated_at = now() WHERE id = :id"
    ), {"id": assessment_id})
    await session.commit()
    return await get_assessment(assessment_id, user, session)
