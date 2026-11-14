"""按候选人简历与岗位生成初始面试问题，并构造实时追问策略。

建会话时只生成 3～5 个初始问题。它们用于确定对话主题和岗位相关性，
不是需要机械逐题执行的完整脚本。实时语音模型会根据候选人的实际回答，
在当前岗位相关的主题内继续追问，或进入下一道初始问题。
"""

from __future__ import annotations

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
MIN_QUESTIONS = 3
MAX_QUESTIONS = 5
MAX_CUSTOM_QUESTIONS = 5
MAX_INITIAL_QUESTIONS = 10
MAX_FOLLOWUPS_PER_TOPIC = 2
MAX_TOTAL_QUESTIONS = 10
STRATEGY = "initial-seeds-with-live-followups"
CUSTOM_SECTION = "hr_custom"

FALLBACK_PLAN: dict = {
    "sections_order": ["intro", "experience", "wrap"],
    "questions": [
        {
            "id": "q1",
            "section": "experience",
            "text": "请介绍你最相关的一段经历。",
            "focus": "相关性与表达",
        },
        {
            "id": "q2",
            "section": "experience",
            "text": "这段经历中你亲自负责什么？",
            "focus": "个人贡献",
        },
        {
            "id": "q3",
            "section": "motivation",
            "text": "你目前的求职意愿和到岗时间？",
            "focus": "动机与时间",
        },
    ],
    "language_mode": {"primary": "zh", "mixed": False},
    "strategy": STRATEGY,
}


def _text(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def normalize_plan(data: dict) -> dict | None:
    """校验模型输出；只接受 3～5 个初始问题，不合格时由调用方回退。"""
    if not isinstance(data, dict):
        return None
    questions: list[dict] = []
    for raw in data.get("questions", []) if isinstance(data.get("questions"), list) else []:
        if not isinstance(raw, dict):
            continue
        text_value = _text(raw.get("text"), 200)
        if len(text_value) < 4:
            continue
        section = raw.get("section")
        section = section if section in SECTIONS else "experience"
        question = {
            "id": f"q{len(questions) + 1}",
            "section": section,
            "text": text_value,
            "focus": _text(raw.get("focus"), 80),
        }
        # 这两个字段用于实时模型判断是否值得继续深挖。旧模型不返回时保持兼容。
        for key, limit in (("job_relevance", 160), ("resume_anchor", 160)):
            value = _text(raw.get(key), limit)
            if value:
                question[key] = value
        questions.append(question)
        if len(questions) == MAX_QUESTIONS:
            break
    if len(questions) < MIN_QUESTIONS:
        return None
    profile = _text(data.get("profile"), 200)
    return {
        "sections_order": list(
            dict.fromkeys(["intro", *(q["section"] for q in questions), "wrap"])
        ),
        "questions": questions,
        "profile": profile,
        "language_mode": {"primary": "zh", "mixed": False},
        "strategy": STRATEGY,
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
    """读取已有会话的初始问题；旧会话缺失或损坏时回退固定问题。"""
    plan = parse_plan(value)
    return plan if plan.get("questions") else FALLBACK_PLAN


def merge_custom_questions(plan: dict, custom_questions: list[str]) -> dict:
    """把 HR 指定问题置于初始问题之前，并让 AI 问题补足剩余主题。"""
    if not isinstance(plan, dict):
        plan = _fallback_with_context(None)
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in custom_questions:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        folded = text.casefold()
        if not text or folded in seen:
            continue
        seen.add(folded)
        cleaned.append(text[:200])
        if len(cleaned) == MAX_CUSTOM_QUESTIONS:
            break
    if not cleaned:
        return plan

    custom_texts = {text.casefold() for text in cleaned}
    generated = [
        {
            **dict(item),
            "source": item.get("source", "ai"),
        }
        for item in plan.get("questions", [])
        if isinstance(item, dict) and _text(item.get("text"), 200)
        and _text(item.get("text"), 200).casefold() not in custom_texts
    ]
    custom = [
        {
            "id": f"hr{index}",
            "section": CUSTOM_SECTION,
            "text": text,
            "focus": "HR指定必问",
            "source": "hr",
            "required": True,
        }
        for index, text in enumerate(cleaned, 1)
    ]
    remaining = max(0, MAX_INITIAL_QUESTIONS - len(custom))
    merged = custom + generated[:remaining]
    sections = [
        "intro",
        *(item["section"] for item in merged),
        "wrap",
    ]
    return {
        **plan,
        "questions": merged,
        "sections_order": list(dict.fromkeys(sections)),
        "custom_question_count": len(custom),
        "strategy": "hr-required-with-ai-followups",
    }


def session_instructions(plan: dict, job_title: str | None = None) -> str:
    """把初始问题和动态追问规则拼成实时语音系统指令。"""
    if not isinstance(plan, dict):
        plan = FALLBACK_PLAN
    questions = [
        item
        for item in plan.get("questions", [])
        if isinstance(item, dict) and _text(item.get("text"), 200)
    ][:MAX_INITIAL_QUESTIONS]
    if not questions:
        return session_instructions(FALLBACK_PLAN, job_title)

    lines = [
        "你是招聘初筛沟通助手。开场用一句话说明这是一轮初步沟通，不做录用决定，"
        "然后从第一道初始问题开始。",
        "初始问题只用于确定对话主题，不是必须逐字朗读的固定脚本。每次只问一个问题，"
        "根据候选人的实际回答实时决定继续深挖、澄清、切换话题或收尾。",
    ]
    title = _text(job_title, 160)
    profile = _text(plan.get("profile"), 200)
    if title:
        lines.append(f"应聘岗位：{title}")
    if profile:
        lines.append(f"候选人简历要点（仅供你组织提问，不要逐字念出）：{profile}")

    job_context = plan.get("job_context")
    if isinstance(job_context, dict):
        required_skills = job_context.get("required_skills")
        responsibilities = job_context.get("responsibilities")
        preferred_skills = job_context.get("preferred_skills")
        jd_excerpt = _text(job_context.get("jd_text"), 6000)
        if isinstance(required_skills, list) and required_skills:
            lines.append(
                "岗位必备技能："
                + "、".join(
                    str(item).strip()[:80] for item in required_skills[:20] if str(item).strip()
                )
            )
        if isinstance(preferred_skills, list) and preferred_skills:
            lines.append(
                "岗位优先技能："
                + "、".join(
                    str(item).strip()[:80] for item in preferred_skills[:20] if str(item).strip()
                )
            )
        if isinstance(responsibilities, list) and responsibilities:
            lines.append(
                "岗位核心职责："
                + "；".join(
                    str(item).strip()[:200] for item in responsibilities[:8] if str(item).strip()
                )
            )
        if jd_excerpt:
            lines.append(f"岗位原文快照（判断相关性时参考）：\n{jd_excerpt}")

    lines.append("初始问题：")
    for index, item in enumerate(questions, 1):
        details = []
        focus = _text(item.get("focus"), 80)
        relevance = _text(item.get("job_relevance"), 160)
        anchor = _text(item.get("resume_anchor"), 160)
        if focus:
            details.append(f"关注：{focus}")
        if relevance:
            details.append(f"岗位关联：{relevance}")
        if anchor:
            details.append(f"简历锚点：{anchor}")
        if item.get("source") == "hr":
            details.append("来源：HR指定必问")
        suffix = f"（{'；'.join(details)}）" if details else ""
        lines.append(f"{index}. {_text(item.get('text'), 200)}{suffix}")

    lines.extend(
        [
            "HR指定问题属于必须覆盖的问题，应优先于 AI 生成的非必问题；"
            "时间不足时压缩 AI 生成问题，不得静默跳过 HR 指定问题。",
            "来源只决定排序和必问标记。所有初始问题不论来自 HR 还是 AI，"
            "都必须使用完全相同的回答充分性判断、追问条件、每主题追问层数、"
            "切换话题和收尾规则，不另设简化流程。",
            "动态推进规则：",
            "1. 候选人回答充分覆盖当前问题的岗位要求、个人贡献、过程和可验证结果时，"
            "进入下一道初始问题，避免为了追问而追问。",
            "2. 回答与岗位高度相关但过于笼统、缺少个人职责、技术实现、指标依据、"
            "关键决策或异常处理时，先围绕当前主题提出一个更具体的问题。",
            "3. 回答偏离岗位或答非所问时，可以简短澄清后把话题拉回当前招聘要求，"
            "不要把面试扩展成无关聊天。",
            "4. 回答中出现矛盾、模糊指标或无法确认的事实时应继续核实；结论记为待核实，"
            "不要当场指控或推断动机。",
            f"5. 每道初始问题，包括 HR 指定问题，都最多追问 "
            f"{MAX_FOLLOWUPS_PER_TOPIC} 层；初始问题和追问合计不超过 "
            f"{MAX_TOTAL_QUESTIONS} 个。",
            "6. 信息已经充分、追问预算用尽或通话接近时限时，简短总结并礼貌收尾。",
            "硬性边界：",
            "- 每次开口只提出一个问题，把问题完整说完，不要只报题号或停在半句。",
            "- 不重复候选人已经完整回答过的问题，不虚构简历和回答中不存在的事实。",
            "- 不要求身份证、住址等敏感信息，不询问性别、年龄、婚育、民族、宗教、残障。",
            "- 只围绕当前岗位和候选人经历开展追问，不做录用决定，表达流畅度不能替代能力判断。",
            "- 候选人沉默或说没听清时，换一种说法重述当前问题，不要直接跳到下一题。",
            "- 候选人短暂停顿、紧张、回答简短或表示不知道时，保持耐心并澄清一次；"
            "不得据此推断故意不配合或负面品性。",
            "- 若候选人明确辱骂、威胁、发表严重不当言论或持续故意扰乱沟通，"
            "不争辩、不模仿、不反击；简短说明相关言行将被如实记录，然后礼貌结束本轮沟通。",
        ]
    )
    return "\n".join(lines)


async def latest_resume_text(session: AsyncSession, candidate_id: UUID) -> str:
    row = (
        (
            await session.execute(
                text(
                    "SELECT v.text_uri FROM resume_version v "
                    "JOIN resume r ON r.id = v.resume_id "
                    "WHERE r.candidate_id = :candidate AND v.status = 'done' "
                    "AND v.text_uri IS NOT NULL "
                    "ORDER BY v.version_no DESC, v.parsed_at DESC NULLS LAST LIMIT 1"
                ),
                {"candidate": candidate_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return ""
    data = await Storage().get(row["text_uri"])
    return data.decode("utf-8", errors="replace")


def _string_list(value, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip()[:200]
        for item in value[:limit]
        if isinstance(item, (str, int, float)) and str(item).strip()
    ]


async def current_job_context(session: AsyncSession, job_id: UUID) -> dict:
    """冻结本次会话使用的岗位版本、职责和技能快照。"""
    row = (
        (
            await session.execute(
                text(
                    "SELECT j.title, j.current_version_id, v.id AS version_id, "
                    "v.jd_text, v.structured FROM job j "
                    "LEFT JOIN job_version v ON v.id = j.current_version_id "
                    "WHERE j.id = :job"
                ),
                {"job": job_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return {}
    structured = row["structured"]
    if isinstance(structured, str):
        try:
            structured = json.loads(structured)
        except ValueError:
            structured = {}
    if not isinstance(structured, dict):
        structured = {}
    version_id = row["version_id"] or row["current_version_id"]
    return {
        "job_version_id": str(version_id) if version_id is not None else None,
        "title": _text(row["title"], 160),
        "jd_text": _text(row["jd_text"], 6000),
        "responsibilities": _string_list(structured.get("responsibilities")),
        "required_skills": _string_list(structured.get("required_skills")),
        "preferred_skills": _string_list(structured.get("preferred_skills")),
        "education_requirements": structured.get("education_requirements"),
    }


async def current_jd(session: AsyncSession, job_id: UUID) -> str:
    """兼容旧调用：返回岗位标题和当前 JD 文本。"""
    context = await current_job_context(session, job_id)
    if not context:
        return ""
    return f"{context.get('title', '')}\n{context.get('jd_text', '')}".strip()


def _fallback_with_context(job_context: dict | None) -> dict:
    plan = {
        **FALLBACK_PLAN,
        "questions": [{**item} for item in FALLBACK_PLAN["questions"]],
        "source": "fallback",
        "strategy": STRATEGY,
    }
    if job_context:
        plan["job_context"] = job_context
    return plan


async def build_plan(
    session: AsyncSession, candidate_id: UUID, job_id: UUID, scenario: str = "screen"
) -> dict:
    """简历 + 岗位 -> 3～5 个初始问题；后续追问由实时模型按对话生成。"""
    job_context = await current_job_context(session, job_id)
    resume_text = await latest_resume_text(session, candidate_id)
    if not resume_text.strip():
        logger.warning("候选人 %s 没有可用的简历文本，面试使用固定初始问题", candidate_id)
        return _fallback_with_context(job_context)
    jd_text = (
        f"{job_context.get('title', '')}\n{job_context.get('jd_text', '')}".strip()
        if job_context
        else ""
    )
    try:
        data = await LLMAdapter().build_interview_plan(
            resume_text, jd_text, scenario, job_context=job_context
        )
    except TTCError as exc:
        logger.warning("面试初始问题生成失败，回退固定问题: %s", exc.message)
        return _fallback_with_context(job_context)
    plan = normalize_plan(data)
    if plan is None:
        logger.warning(
            "面试初始问题未达到 3～5 道门槛，回退固定问题：%s",
            json.dumps(data, ensure_ascii=False)[:300],
        )
        return _fallback_with_context(job_context)
    plan["source"] = "llm"
    plan["job_context"] = job_context
    return plan
