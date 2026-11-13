"""轻量简历-岗位匹配端点：小模型打分 + LLM 解释 + 落库。

与 `assessments.py` 的确定性评估互不影响：本端点只写 assessment / dimension_score，
不修改既有端点的行为。重复调用按唯一键覆盖同一条评估（幂等）。
"""

import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.adapters.llm import LLMAdapter
from ttc.adapters.matcher import CATEGORY_CODES, ResumeMatchAdapter
from ttc.adapters.storage import Storage
from ttc.api.deps import Principal, require_roles
from ttc.api.v1.candidates import require_candidate
from ttc.api.v1.jobs import require_job
from ttc.api.v1.resumes import require_resume
from ttc.core.config import get_settings
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7
from ttc.domains.resume.service import extract_text

router = APIRouter(tags=["assessments"])
hr = require_roles("hr", "admin")


class MatchInput(BaseModel):
    job_id: UUID
    explain: bool = True
    top_k: int = Field(default=5, ge=1, le=len(CATEGORY_CODES))


def _empty_explanation(status: str, reason: str | None = None) -> dict:
    return {"status": status, "summary": "", "strengths": [], "gaps": [],
            "suggestions": [], "risk_notes": [], "reason": reason}


async def load_resume_text(
    session: AsyncSession, user: Principal, resume: dict
) -> tuple[str, UUID]:
    """优先取已解析文本快照，取不到再回落到原始文件；都没有文本则 409。

    返回 (文本, resume_version_id)；没有版本时写入文本快照并补一条 done 版本，
    以满足 assessment.resume_version_id 的非空外键。
    """
    storage = Storage()
    version = (await session.execute(text(
        "SELECT id, text_uri FROM resume_version WHERE resume_id = :id "
        "ORDER BY version_no DESC LIMIT 1"
    ), {"id": resume["id"]})).mappings().one_or_none()
    value = None
    if version is not None and version["text_uri"]:
        try:
            value = (await storage.get(version["text_uri"])).decode("utf-8-sig").strip()
        except Exception:  # 快照丢失时回落到原始文件，不影响主流程
            value = None
    if not value:
        try:
            data = await storage.get(resume["file_uri"])
            value, _ = extract_text(data, resume["mime"])
        except TTCError as exc:
            raise TTCError("TTC-2002", "简历尚未解析完成，无法提取文本", 409) from exc
        except Exception as exc:
            raise TTCError("TTC-2002", "简历文件不可读取，请先完成解析", 409) from exc
    if not value:
        raise TTCError("TTC-2002", "简历尚未解析完成", 409)
    if version is not None:
        return value, version["id"]
    snapshot = await storage.put(
        f"text/{user.tenant_id}/{resume['candidate_id']}/{resume['id']}/match.txt",
        value.encode(), "text/plain; charset=utf-8",
    )
    number = (await session.execute(text(
        "SELECT COALESCE(MAX(version_no), 0) + 1 FROM resume_version WHERE resume_id = :id"
    ), {"id": resume["id"]})).scalar_one()
    version_id = uuid7()
    await session.execute(text(
        "INSERT INTO resume_version (id, resume_id, version_no, extractor_model, "
        "prompt_version, text_uri, status, parsed_at) VALUES "
        "(:id, :resume, :no, 'raw-text', 'match-v1', :uri, 'done', now())"
    ), {"id": version_id, "resume": resume["id"], "no": number, "uri": snapshot})
    return value, version_id


async def build_explanation(resume_text: str, jd_text: str | None, match: dict,
                            explain: bool) -> dict:
    """LLM 解释绝不阻塞主链路：未配置 / 超时 / 报错都降级返回。"""
    if not explain:
        return _empty_explanation("skipped", "本次请求未要求生成解释")
    if not jd_text:
        return _empty_explanation("unavailable", "岗位尚未配置岗位描述")
    settings = get_settings()
    if not all((settings.llm_base_url, settings.llm_api_key, settings.llm_model)):
        return _empty_explanation("unavailable", "尚未配置匹配解释模型")
    try:
        result = await LLMAdapter().explain_match(resume_text, jd_text, match)
    except TTCError as exc:
        return _empty_explanation("failed", exc.message)
    except Exception:
        # 代理配置错误等非 HTTP 异常也不能拖垮整条链路
        return _empty_explanation("failed", "解释模型调用异常（配置或网络问题）")
    return {"status": "ready", **result, "reason": None}


@router.post("/resumes/{resume_id}/match")
async def match_resume(resume_id: UUID, body: MatchInput,
                       user: Principal = Depends(hr),
                       session: AsyncSession = Depends(get_session)):
    resume = await require_resume(session, user, resume_id)
    job = await require_job(session, user, body.job_id)
    if job["status"] == "archived":
        raise TTCError("TTC-2002", "岗位已归档", 409)
    candidate = await require_candidate(session, user, resume["candidate_id"])
    if not candidate["is_synthetic"]:
        from ttc.api.v1.consents import require_consent
        await require_consent(session, resume["candidate_id"], "resume_process")
    jd_text = None
    if job["current_version_id"]:
        jd_text = (await session.execute(text(
            "SELECT jd_text FROM job_version WHERE id = :id"
        ), {"id": job["current_version_id"]})).scalar_one_or_none()
    resume_text, version_id = await load_resume_text(session, user, resume)
    match = await ResumeMatchAdapter().predict(resume_text, jd_text=jd_text)
    explanation = await build_explanation(resume_text, jd_text, match, body.explain)

    plan_id = (await session.execute(text(
        "SELECT id FROM weight_plan WHERE job_id = :job AND tenant_id = :tenant "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"job": body.job_id, "tenant": user.tenant_id})).scalar_one_or_none()
    if plan_id is None:
        raise TTCError("TTC-2002", "岗位未配置权重模板", 409)

    # pair 模型给的是「简历 × 这个 JD」的配对概率，这才是 match_score 应有的含义；
    # 旧分类模型没有该字段，退回 24 类里最高那一类的概率。
    jd_match_score = match.get("jd_match_score")
    scoring = float(jd_match_score) if jd_match_score is not None else float(match["confidence"])
    match_score = round(scoring * 100, 2)
    top = match["top_k"][:body.top_k]
    total = sum(item["score"] for item in top) or 1.0
    dimensions = []
    for index, item in enumerate(top):
        # evidence_state 取既有枚举：只有榜首且可信度 >=0.5 视为部分证据，其余仅为简历自述
        state = "partial" if index == 0 and float(match["confidence"]) >= 0.5 else "self_claim"
        reasoning = (
            f"小模型将简历归入 {item['code']}（类别得分 {item['score']:.3f}，"
            f"confidence {float(match['confidence']):.3f}）；该结果是简历文本与岗位类别的"
            "语义相似度，不是面试结论，也不证明经历真实性。"
        )
        if index == 0 and explanation["status"] == "ready" and explanation["summary"]:
            reasoning = explanation["summary"] + " " + reasoning
        dimensions.append({"key": item["code"], "label": item["code"],
                           "weight_pct": round(item["score"] / total * 100, 2),
                           "score": round(item["score"] * 100, 2),
                           "evidence_state": state, "reasoning": reasoning})
    report = {
        "meta": {"assessed_at": datetime.now(UTC).isoformat(),
                 "model_version": match["model_version"], "source": "resume-match"},
        "match_ledger": {"score": match_score, "category": match["category"],
                         "confidence": float(match["confidence"]), "top_k": top,
                         "scores": match["scores"], "dimensions": dimensions},
        "explanation": explanation,
        "limitations": ["匹配分为简历文本与岗位类别的模型相似度，不代表真实能力",
                        "简历自述未经核验，不能证明经历真实性",
                        "LLM 解释仅依据给定简历与 JD，缺失信息一律写“简历未体现”",
                        "结论仅供 HR 参考，须人工复核"],
    }
    report_json = json.dumps(report, default=str, ensure_ascii=False)
    existing = (await session.execute(text(
        "SELECT id FROM assessment WHERE candidate_id = :candidate AND job_id = :job "
        "AND resume_version_id = :version AND weight_plan_id = :plan"
    ), {"candidate": resume["candidate_id"], "job": body.job_id,
        "version": version_id, "plan": plan_id})).scalar_one_or_none()
    if existing is not None:
        assessment_id = existing
        created_at = (await session.execute(text(
            "UPDATE assessment SET match_score = :match, status = 'ready', "
            "report_json = CAST(:report AS jsonb), model_version = :version, "
            "updated_at = now() WHERE id = :id RETURNING created_at"
        ), {"match": match_score, "report": report_json,
            "version": match["model_version"], "id": assessment_id})).scalar_one()
        await session.execute(text(
            "DELETE FROM dimension_score WHERE assessment_id = :id"), {"id": assessment_id})
    else:
        assessment_id = uuid7()
        created_at = (await session.execute(text(
            "INSERT INTO assessment (id, candidate_id, job_id, resume_version_id, "
            "weight_plan_id, match_score, status, report_json, model_version) "
            "VALUES (:id, :candidate, :job, :version, :plan, :match, 'ready', "
            "CAST(:report AS jsonb), :model) RETURNING created_at"
        ), {"id": assessment_id, "candidate": resume["candidate_id"], "job": body.job_id,
            "version": version_id, "plan": plan_id, "match": match_score,
            "report": report_json, "model": match["model_version"]})).scalar_one()
    for dimension in dimensions:
        await session.execute(text(
            "INSERT INTO dimension_score (id, assessment_id, dimension_key, label, "
            "weight_pct, score, evidence_state, reasoning) VALUES "
            "(:id, :assessment, :key, :label, :weight, :score, "
            "CAST(:state AS evidence_state), :reasoning)"
        ), {"id": uuid7(), "assessment": assessment_id, "key": dimension["key"],
            "label": dimension["label"], "weight": dimension["weight_pct"],
            "score": dimension["score"], "state": dimension["evidence_state"],
            "reasoning": dimension["reasoning"]})
    await session.commit()
    return {"assessment_id": str(assessment_id), "match_score": match_score,
            "category": match["category"], "confidence": float(match["confidence"]),
            "jd_match_score": jd_match_score,
            "top_k": top, "explanation": explanation,
            "model_version": match["model_version"],
            "fallback_reason": match.get("fallback_reason"),
            "created_at": created_at}
