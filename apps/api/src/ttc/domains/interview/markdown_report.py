"""Render evidence-backed interview reports as portable Markdown.

The renderer is deterministic. It only organizes facts and assessments already
stored for one completed voice interview; it does not create new candidate facts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

ROLE_LABELS = {
    "interviewer": "AI 面试官",
    "candidate": "候选人",
    "hr": "HR",
    "system": "系统",
}
STATUS_LABELS = {
    "created": "待开始",
    "live": "进行中",
    "ended": "已结束",
    "failed": "异常结束",
    "revoked": "已撤回授权",
}
DIMENSION_ROLE_DIRECTIONS = {
    "job_knowledge": "岗位知识证据较强，可关注同领域但更侧重执行的岗位",
    "relevant_experience": "相关经历较深，可关注职责相近、层级匹配的岗位",
    "problem_solving": "问题解决证据较强，可关注排查、方案设计或复杂问题处理岗位",
    "ownership_impact": "个人贡献与结果证据较强，可关注需要独立交付或项目主责的岗位",
    "learning_adaptability": "学习迁移证据较强，可关注有培训周期或相邻领域的可培养岗位",
}


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _text(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return round(float(value), 2)
    return None


def _score(value: Any) -> str:
    number = _number(value)
    return f"{number:g}" if number is not None else "待核验"


def _escape(value: Any, limit: int = 2000) -> str:
    text = _text(value, limit)
    text = text.replace("\\", "\\\\")
    for character in ("`", "*", "_", "{", "}", "[", "]", "<", ">", "#", "|"):
        text = text.replace(character, f"\\{character}")
    return re.sub(r"\s+", " ", text).strip()


def _quote(value: Any, limit: int = 1200) -> list[str]:
    text = _text(value, limit).replace("<", "&lt;").replace(">", "&gt;")
    lines = text.splitlines() or ["—"]
    return [f"> {line}" if line else ">" for line in lines]


def _date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    text = _text(value, 80)
    return text or "—"


def _duration(session: dict) -> str:
    started = session.get("started_at")
    ended = session.get("ended_at")
    if not isinstance(started, datetime) or not isinstance(ended, datetime):
        return "—"
    seconds = max(0, int((ended - started).total_seconds()))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes} 分 {remainder} 秒"


def _unique(values: Iterable[Any], limit: int = 20) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value, 600)
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _dimensions(assessment: dict) -> list[dict]:
    result = []
    for item in _as_list(assessment.get("dimensions")):
        if not isinstance(item, dict):
            continue
        result.append({
            "key": _text(item.get("key"), 80),
            "label": _text(item.get("label") or item.get("key"), 120) or "未命名维度",
            "weight_pct": _number(item.get("weight_pct")),
            "score": _number(item.get("score")),
            "reason": _text(item.get("reason"), 1000),
            "evidence_turn_ids": _unique(item.get("evidence_turn_ids"), 10),
        })
    return result


def _fallback_qa(turns: list[dict]) -> list[dict]:
    """Group persisted turns into a conservative Q&A when model summary is absent."""
    result: list[dict] = []
    question = ""
    answers: list[str] = []

    def flush() -> None:
        nonlocal question, answers
        if question or answers:
            result.append({
                "question": question or "未记录对应问题",
                "answer_summary": " ".join(answers)[:800] or "未记录候选人回答",
            })
        question = ""
        answers = []

    for turn in turns:
        role = _text(turn.get("role"), 40)
        text = _text(turn.get("text"), 2000)
        if not text:
            continue
        if role in ("interviewer", "hr"):
            flush()
            question = text
        elif role == "candidate":
            answers.append(text)
    flush()
    return result[:30]


def _crosscheck_items(crosscheck: dict) -> list[str]:
    labels = {
        "consistent": "与简历或已提供材料一致",
        "supplemented": "补充了材料中未出现的信息",
        "inconsistent": "与已有材料存在不一致",
        "unverified": "尚未完成交叉核验",
    }
    items = []
    for key, label in labels.items():
        values = _as_list(crosscheck.get(key))
        if not values:
            continue
        if key == "unverified":
            items.append(label)
            continue
        for value in values[:10]:
            items.append(f"{label}：{_text(value, 500)}")
    return _unique(items)


def _recommendation(
    capability: dict,
    conduct: dict,
    capability_score: float | None,
) -> tuple[str, str, list[str]]:
    reasons: list[str] = []
    if conduct.get("veto") is True or _text(conduct.get("status")) == "vetoed":
        reasons.append("言行审核存在已绑定原始轮次的严重事件，系统不建议自动推进。")
        return "暂停推进，交 HR 人工复核", "veto", reasons
    if _text(conduct.get("status")) == "unassessed":
        reasons.append("言行审核没有形成可用评分，不能视为已通过。")
    if capability_score is None:
        reasons.append("本次回答不足以形成可靠的能力证据分。")
        return "证据不足，暂缓形成岗位结论", "hold", reasons
    if capability.get("review_required") is True or conduct.get("review_required") is True:
        reasons.append("评估结果要求人工复核，不能直接作为录用决定。")
        return "补充核验后再决定是否推进", "verify", reasons
    if capability_score >= 75:
        reasons.append(f"本次面试能力证据分为 {capability_score:g}，未触发言行否决。")
        return "建议进入下一轮面试（参考）", "advance", reasons
    if capability_score >= 60:
        reasons.append(f"本次面试能力证据分为 {capability_score:g}，存在需要确认的差距。")
        return "补充核验后再决定是否推进", "verify", reasons
    reasons.append(f"本次面试能力证据分为 {capability_score:g}，低于当前岗位的参考阈值。")
    return "暂不建议进入当前岗位下一轮（参考）", "not_recommended", reasons


def _role_directions(
    decision_code: str,
    dimensions: list[dict],
) -> list[str]:
    strong = sorted(
        [
            item for item in dimensions
            if item.get("score") is not None and item["score"] >= 70
        ],
        key=lambda item: item["score"],
        reverse=True,
    )
    directions = [
        DIMENSION_ROLE_DIRECTIONS[item["key"]]
        for item in strong
        if item.get("key") in DIMENSION_ROLE_DIRECTIONS
    ]
    directions = _unique(directions, 3)
    if decision_code in ("advance", "veto"):
        return []
    if directions:
        return [
            *directions,
            "以上是岗位方向，不是具体岗位结论；HR 仍需结合空缺、职级与业务要求筛选。",
        ]
    return [
        "当前单次面试没有足够证据支持可靠的其他岗位推荐。",
        "如业务希望考虑转岗，建议补充与目标岗位直接相关的作品、案例或技能核验后再判断。",
    ]


def _render_info(
    session: dict,
    candidate: dict,
    job: dict,
    report: dict,
    report_id: Any,
) -> list[str]:
    status = STATUS_LABELS.get(
        _text(session.get("status")),
        _escape(session.get("status")),
    )
    return [
        "## 1. 报告信息",
        "",
        "| 字段 | 内容 |",
        "| --- | --- |",
        f"| 报告 ID | `{_escape(report_id, 80)}` |",
        f"| 面试 ID | `{_escape(session.get('id'), 80)}` |",
        f"| 候选人 | {_escape(candidate.get('display_name'), 120) or '—'} |",
        f"| 应聘岗位 | {_escape(job.get('title'), 160) or '—'} |",
        f"| 会话状态 | {status} |",
        f"| 结束原因 | {_escape(session.get('end_reason'), 120) or '—'} |",
        f"| 开始时间 | {_date(session.get('started_at'))} |",
        f"| 结束时间 | {_date(session.get('ended_at'))} |",
        f"| 通话时长 | {_duration(session)} |",
        f"| 转写轮次 | {_text(_as_dict(report.get('summary')).get('turn_count'), 20) or '—'} |",
        f"| 纪要模型 | {_escape(report.get('model_version'), 120) or '—'} |",
        f"| 能力模型 | {_escape(report.get('capability_model_version'), 120) or '—'} |",
        f"| 言行模型 | {_escape(report.get('conduct_model_version'), 120) or '—'} |",
    ]


def _render_dimensions(dimensions: list[dict]) -> list[str]:
    lines = [
        "### 3.3 能力维度明细",
        "",
        "| 维度 | 权重 | 本次证据分 | 引用的原始轮次 | 判断摘要 |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for item in dimensions:
        refs = "<br>".join(f"`{_text(turn_id, 80)}`" for turn_id in item["evidence_turn_ids"])
        weight = f"{item['weight_pct']:g}%" if item["weight_pct"] is not None else "—"
        lines.append(
            f"| {_escape(item['label'], 160)} | {weight} | {_score(item['score'])} | "
            f"{refs or '—'} | {_escape(item['reason'], 1000) or '—'} |"
        )
    return lines


def render_interview_markdown(
    *,
    session: dict,
    candidate: dict,
    job: dict,
    plan: dict,
    report: dict,
    turns: list[dict],
    generated_at: datetime | None = None,
) -> tuple[str, str]:
    """Return ``(markdown, sha256)`` for one completed interview report."""
    generated_at = generated_at or datetime.now(UTC)
    summary = _as_dict(report.get("summary"))
    capability = _as_dict(report.get("capability"))
    conduct = _as_dict(report.get("conduct"))
    crosscheck = _as_dict(report.get("crosscheck"))
    dimensions = _dimensions(capability)
    capability_score = _number(capability.get("score"))
    if capability_score is None:
        capability_score = _number(report.get("capability_score"))
    decision, decision_code, reasons = _recommendation(
        capability, conduct, capability_score
    )
    qa = [
        {
            "question": _text(item.get("question"), 500),
            "answer_summary": _text(item.get("answer_summary"), 1200),
        }
        for item in _as_list(summary.get("qa"))
        if isinstance(item, dict)
    ]
    if not qa:
        qa = _fallback_qa(turns)
    followups = _unique(report.get("followups"), 20)
    verification = _unique(capability.get("verification_questions"), 20)
    confirmations = _unique([*followups, *verification, *capability.get("gaps", [])], 24)
    if not confirmations:
        confirmations = ["暂无系统识别的待确认事项；HR 仍需完成最终复核。"]

    highlights = _unique(capability.get("strengths"), 8)
    for item in sorted(
        [dimension for dimension in dimensions if dimension["score"] is not None],
        key=lambda dimension: dimension["score"],
        reverse=True,
    )[:3]:
        if item["score"] >= 70:
            refs = "、".join(item["evidence_turn_ids"]) or "未提供可用引用"
            highlights.append(
                f"能力维度「{item['label']}」获得 {item['score']:g} 分，"
                f"关联原始轮次：{refs}。"
            )
    highlights = _unique(highlights, 10) or ["暂未识别出可定位到原始回答的突出表现。"]

    doubts = _unique(capability.get("gaps"), 10)
    for dimension in dimensions:
        if dimension["score"] is None:
            doubts.append(f"能力维度「{dimension['label']}」缺少可定位的候选人回答证据。")
    for incident in _as_list(conduct.get("incidents")):
        if not isinstance(incident, dict):
            continue
        label = _text(incident.get("category_label") or incident.get("category"), 120)
        description = _text(incident.get("description"), 800)
        refs = "、".join(_unique(incident.get("evidence_turn_ids"), 10))
        doubts.append(
            f"[{_text(incident.get('severity'), 20) or '待核验'}] "
            f"{label}：{description}（轮次：{refs or '缺失'}）"
        )
    doubts.extend(_crosscheck_items(crosscheck))
    if capability.get("review_required") is True:
        doubts.append("能力评估被标记为需要人工复核。")
    if conduct.get("review_required") is True:
        doubts.append("言行评估被标记为需要人工复核。")
    doubts = _unique(doubts, 18) or ["未识别出明确疑点；未覆盖内容仍需 HR 人工确认。"]

    questions = [
        item for item in _as_list(plan.get("questions"))
        if isinstance(item, dict) and _text(item.get("text"))
    ]
    role_directions = _role_directions(decision_code, dimensions)
    limitations = _unique(
        [
            *_as_list(summary.get("limitations")),
            *_as_list(capability.get("limitations")),
            *_as_list(conduct.get("limitations")),
            "本报告基于单次面试的结构化结果，不替代 HR 或业务面试官的最终判断。",
        ],
        30,
    )
    coverage = _as_dict(capability.get("evidence_coverage"))
    cited_turns = _text(coverage.get("cited_turns"), 20) or "0"
    candidate_turns = _text(coverage.get("candidate_turns"), 20) or "0"
    review_label = (
        "需要"
        if capability.get("review_required") or conduct.get("review_required")
        else "仍需按流程完成"
    )

    lines = [
        f"# 面试报告｜{_escape(candidate.get('display_name'), 120) or '候选人'}"
        f"｜{_escape(job.get('title'), 160) or '未命名岗位'}",
        "",
        f"> 生成时间：{generated_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}  ",
        "> 使用说明：以下内容是招聘参考与人工复核材料，不是自动录用决定。",
        "",
        *_render_info(session, candidate, job, report, report.get("id") or session.get("id")),
        "",
        "## 2. 执行摘要",
        "",
        f"- **参考结论：{decision}。**",
        f"- **能力证据：**{_score(capability_score)} / 100。"
        f"{_escape(capability.get('summary'), 1000) or '能力证据摘要不可用。'}",
        f"- **言行审核：**状态 `{_escape(conduct.get('status'), 80) or '未评估'}`，"
        f"参考分 {_score(conduct.get('score'))}。",
        f"- **总体纪要：**{_escape(summary.get('overview'), 1600) or '本次没有可用的整体纪要。'}",
        "",
        "## 3. 综合表现与能力图谱",
        "",
        "### 3.1 综合表现",
        "",
        "| 观察项 | 当前结论 |",
        "| --- | --- |",
        f"| 岗位相关能力 | {_score(capability_score)} / 100；"
        f"{_escape(capability.get('summary'), 1000) or '待人工复核'} |",
        f"| 言行风险 | {_escape(conduct.get('summary'), 1000) or '尚无可用审核摘要'} |",
        f"| 证据覆盖 | 引用 {cited_turns} 个候选人轮次 / "
        f"有效 {candidate_turns} 个 |",
        f"| 人工复核 | {review_label} |",
        "",
        "### 3.2 能力图谱",
        "",
        "```mermaid",
        "graph LR",
        '  A["本次面试能力证据"]',
    ]
    for index, dimension in enumerate(dimensions, start=1):
        lines.append(
            f'  A --> D{index}["{_escape(dimension["label"], 100)}'
            f'<br/>{_score(dimension["score"])}"]'
        )
    lines.extend([
        "```",
        "",
        *_render_dimensions(dimensions),
        "",
        "## 4. 面试问答概括",
        "",
    ])
    if qa:
        for index, item in enumerate(qa[:30], start=1):
            lines.extend([
                f"### Q{index} {_escape(item['question'], 500)}",
                "",
                _escape(item["answer_summary"], 1400) or "未记录候选人回答。",
                "",
            ])
    else:
        lines.extend(["本次没有可用的问答摘要，需查看原始转写或补充面试材料。", ""])

    lines.extend([
        "## 5. 亮点、重点与疑点",
        "",
        "### 亮点",
        "",
        *[f"- **[亮点]** {_escape(item, 1200)}" for item in highlights],
        "",
        "### 重点",
        "",
    ])
    if questions:
        for item in questions[:10]:
            focus = _text(item.get("focus"), 300)
            lines.append(
                f"- **[重点]** {_escape(item.get('text'), 500)}"
                + (f"（关注：{_escape(focus, 300)}）" if focus else "")
            )
    else:
        lines.append("- **[重点]** 本次问题清单不可用，需结合原始纪要复核考察重点。")
    lines.extend(["", "### 疑点", ""])
    lines.extend(f"- **[疑点]** {_escape(item, 1200)}" for item in doubts)

    lines.extend([
        "",
        "## 6. 待确认事项",
        "",
        "| 待确认事项 | 优先级 | 负责人 |",
        "| --- | --- | --- |",
    ])
    for index, item in enumerate(confirmations, start=1):
        needs_attention = capability_score is None or decision_code != "advance"
        priority = "高" if index <= 3 and needs_attention else "中"
        lines.append(f"| {_escape(item, 1000)} | {priority} | HR |")

    lines.extend([
        "",
        "## 7. HR 进一步调查与提问方向",
        "",
    ])
    investigation = _unique([*verification, *followups], 24)
    if not investigation:
        missing_labels = [item["label"] for item in dimensions if item["score"] is None]
        investigation = [
            f"请候选人围绕「{label}」提供一个完整案例，说明背景、本人动作、判断依据和结果。"
            for label in missing_labels[:5]
        ]
    if not investigation:
        investigation = ["请 HR 结合岗位要求与原始转写，选择一项关键经历做开放式追问。"]
    lines.extend(
        f"{index}. {_escape(item, 1000)}"
        for index, item in enumerate(investigation, start=1)
    )

    lines.extend([
        "",
        "## 8. 参考结论与其他岗位建议",
        "",
        f"**参考结论：{decision}。**",
        "",
        "判断依据：",
        "",
        *[f"- {_escape(reason, 1000)}" for reason in reasons],
        f"- 本次能力证据分为 {_score(capability_score)}；"
        f"言行状态为 `{_escape(conduct.get('status'), 80) or '未评估'}`。",
        "",
    ])
    if role_directions:
        lines.extend([
            "### 其他岗位方向",
            "",
            *[f"- {_escape(item, 1000)}" for item in role_directions],
        ])
    else:
        lines.extend([
            "### 其他岗位方向",
            "",
            "当前证据支持继续评估本岗位，暂不建议主动切换岗位；"
            "如本岗位关闭，应由 HR 结合内部空缺重新评估。",
        ])

    lines.extend(["", "## 9. 证据与报告边界", "", "### 原始回答引用", ""])
    quotes = [
        item for item in _as_list(report.get("quotes"))
        if isinstance(item, dict) and _text(item.get("text"))
    ]
    if quotes:
        for item in quotes[:30]:
            lines.append(f"#### 候选人轮次 `{_text(item.get('turn_id'), 80) or '—'}`")
            lines.append("")
            lines.extend(_quote(item.get("text")))
            lines.append("")
    else:
        lines.extend(["本次报告没有保存可用的候选人原文引用。", ""])
    lines.extend(["### 报告边界", ""])
    lines.extend(f"- {_escape(item, 1200)}" for item in limitations)
    if not _crosscheck_items(crosscheck):
        lines.append("- 本次未完成与简历的交叉核验，未提及的信息不能直接视为不存在。")

    lines.extend([
        "",
        "## 10. 后续行动清单",
        "",
        f"- [{'x' if decision_code == 'advance' else ' '}] HR 复核报告结论与证据引用",
        f"- [ ] 完成 {len(confirmations)} 项待确认事项并记录结论",
        f"- [ ] 确认是否进入下一轮：{_escape(decision, 300)}",
        "- [ ] 如使用其他岗位方向，核验目标岗位的职级、职责与空缺",
        f"- [x] Markdown 报告已生成（"
        f"{generated_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M UTC')}）",
        "",
        "---",
        "",
        "本报告由 TTC 面试证据链生成。AI 结论仅用于辅助，"
        "最终招聘决定由具备权限的 HR 和业务负责人作出。",
        "",
    ])
    markdown = "\n".join(lines)
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return markdown, digest
