"""按候选人简历与岗位生成面试问题清单。

清单在建会话时生成一次并落进 ``voice_session.plan_json``：候选人门户据此
展示「本轮问什么」，实时语音中继层据此拼系统指令。生成失败一律回退固定
清单——建会话这一步不能因为模型不可用而失败。
"""
import json
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.adapters.llm import LLMAdapter
from ttc.adapters.storage import Storage
from ttc.core.errors import TTCError

logger = logging.getLogger(__name__)

SECTIONS = ("experience", "skill", "gap", "motivation")
MAX_QUESTIONS = 6

FALLBACK_PLAN: dict = {
    "sections_order": ["intro", "experience", "wrap"],
    "questions": [
        {"id": "q1", "section": "experience", "text": "请介绍你最相关的一段经历。",
         "focus": "相关性与表达"},
        {"id": "q2", "section": "experience", "text": "这段经历中你亲自负责什么？",
         "focus": "个人贡献"},
        {"id": "q3", "section": "wrap", "text": "你目前的求职意愿和到岗时间？",
         "focus": "动机与时间"},
    ],
    "language_mode": {"primary": "zh", "mixed": False},
}


def normalize_plan(data: dict) -> dict | None:
    """校验模型输出；不合格返回 None，由调用方回退固定清单。"""
    if not isinstance(data, dict):
        return None
    questions: list[dict] = []
    for raw in data.get("questions", []) if isinstance(data.get("questions"), list) else []:
        if not isinstance(raw, dict):
            continue
        text_value = raw.get("text")
        if not isinstance(text_value, str):
            continue
        text_value = text_value.strip()
        if not 4 <= len(text_value) <= 200:
            continue
        section = raw.get("section")
        section = section if section in SECTIONS else "experience"
        focus = raw.get("focus")
        focus = focus.strip()[:40] if isinstance(focus, str) else ""
        questions.append({"id": f"q{len(questions) + 1}", "section": section,
                          "text": text_value, "focus": focus})
        if len(questions) == MAX_QUESTIONS:
            break
    if not questions:
        return None
    profile = data.get("profile")
    profile = profile.strip()[:200] if isinstance(profile, str) else ""
    return {
        "sections_order": list(dict.fromkeys(["intro", *(q["section"] for q in questions), "wrap"])),
        "questions": questions,
        "profile": profile,
        "language_mode": {"primary": "zh", "mixed": False},
    }


def parse_plan(value) -> dict:
    """asyncpg 把 jsonb 读成字符串；解析不出对象就返回空字典。"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def plan_from_db(value) -> dict:
    """从库里读问题清单；缺失或不合法就回退固定清单。"""
    plan = parse_plan(value)
    return plan if plan.get("questions") else FALLBACK_PLAN


def session_instructions(plan: dict) -> str:
    """把清单拼成实时语音的系统指令。"""
    if not isinstance(plan, dict):
        plan = FALLBACK_PLAN
    questions = [item for item in plan.get("questions", [])
                 if isinstance(item, dict) and str(item.get("text", "")).strip()]
    if not questions:
        return session_instructions(FALLBACK_PLAN)
    lines = [
        "你是招聘初筛沟通助手。开场用一句话说明这是一轮初步沟通，不做录用决定。",
        "只按顺序询问下面的问题；每题问完可以追问一次细节，但不要引入清单之外的新主题。",
        "不要要求身份证、住址等敏感信息，也不要询问性别、年龄、婚育、民族、宗教、残障。",
        "候选人说的内容与简历不一致时记为待核实，不要当场下结论。",
    ]
    profile = plan.get("profile")
    if isinstance(profile, str) and profile.strip():
        lines.append(f"候选人简历要点（仅供你组织提问，不要逐字念出）：{profile.strip()}")
    lines.append("问题清单：")
    for index, item in enumerate(questions, 1):
        focus = str(item.get("focus", "")).strip()
        suffix = f"（关注：{focus}）" if focus else ""
        lines.append(f"{index}. {str(item['text']).strip()}{suffix}")
    return "\n".join(lines)


async def latest_resume_text(session: AsyncSession, candidate_id: UUID) -> str:
    row = (await session.execute(
        text("SELECT v.text_uri FROM resume_version v JOIN resume r ON r.id = v.resume_id "
             "WHERE r.candidate_id = :candidate AND v.status = 'done' AND v.text_uri IS NOT NULL "
             "ORDER BY v.version_no DESC, v.parsed_at DESC NULLS LAST LIMIT 1"),
        {"candidate": candidate_id},
    )).mappings().one_or_none()
    if row is None:
        return ""
    data = await Storage().get(row["text_uri"])
    return data.decode("utf-8", errors="replace")


async def current_jd(session: AsyncSession, job_id: UUID) -> str:
    row = (await session.execute(
        text("SELECT j.title, v.jd_text FROM job j "
             "LEFT JOIN job_version v ON v.id = j.current_version_id WHERE j.id = :job"),
        {"job": job_id},
    )).mappings().one_or_none()
    if row is None:
        return ""
    return f"{row['title']}\n{row['jd_text'] or ''}".strip()


async def build_plan(session: AsyncSession, candidate_id: UUID, job_id: UUID,
                     scenario: str = "screen") -> dict:
    """简历 + 岗位 → 问题清单；任何失败都回退固定清单。"""
    resume_text = await latest_resume_text(session, candidate_id)
    if not resume_text.strip():
        logger.warning("候选人 %s 没有可用的简历文本，面试使用固定问题清单", candidate_id)
        return {**FALLBACK_PLAN, "source": "fallback"}
    jd_text = await current_jd(session, job_id)
    try:
        data = await LLMAdapter().build_interview_plan(resume_text, jd_text, scenario)
    except TTCError as exc:
        logger.warning("面试问题生成失败，回退固定清单: %s", exc.message)
        return {**FALLBACK_PLAN, "source": "fallback"}
    plan = normalize_plan(data)
    if plan is None:
        logger.warning("面试问题生成结果不符合契约，回退固定清单: %s",
                       json.dumps(data, ensure_ascii=False)[:300])
        return {**FALLBACK_PLAN, "source": "fallback"}
    plan["source"] = "llm"
    return plan
