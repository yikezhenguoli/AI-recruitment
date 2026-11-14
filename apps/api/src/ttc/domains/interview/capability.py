"""Normalize evidence-backed interview capability scoring.

This score captures observed capability evidence from answers in one interview.
It is not a global ability test and cannot replace skills assessments or expert
review.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

CAPABILITY_DIMENSIONS = (
    ("job_knowledge", "岗位知识与技能", 20),
    ("relevant_experience", "相关经历深度", 25),
    ("problem_solving", "分析与问题解决", 20),
    ("ownership_impact", "个人贡献与结果", 20),
    ("learning_adaptability", "学习与迁移", 15),
)
DIMENSION_META = {
    key: {"label": label, "weight_pct": weight}
    for key, label, weight in CAPABILITY_DIMENSIONS
}
CAPABILITY_LIMITATION = (
    "能力分仅代表候选人在本次面试回答中展示出的岗位相关证据，"
    "不是通用智力、人格、学习风格或长期绩效测评。"
)


def _text(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _candidate_turns(turns: Iterable[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for raw in turns:
        turn = dict(raw)
        if turn.get("role") != "candidate":
            continue
        turn_id = str(turn.get("id") or "").strip()
        text = _text(turn.get("text"), 20_000)
        if turn_id and text:
            result[turn_id] = {"id": turn_id, "text": text}
    return result


def _evidence_ids(value: Any, candidate_turns: dict[str, dict]) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        turn_id = str(item).strip()
        if turn_id in candidate_turns and turn_id not in result:
            result.append(turn_id)
    return result[:10]


def _texts(value: Any, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:limit]:
        text = _text(item, 500)
        if text and text not in result:
            result.append(text)
    return result


def _dimensions(
    value: Any,
    candidate_turns: dict[str, dict],
) -> list[dict]:
    by_key: dict[str, dict] = {}
    if isinstance(value, list):
        for raw in value[:20]:
            if not isinstance(raw, dict):
                continue
            key = raw.get("key")
            if key not in DIMENSION_META or key in by_key:
                continue
            score = raw.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                score_value = None
            else:
                score_value = round(max(0.0, min(100.0, float(score))), 2)
            evidence_ids = _evidence_ids(raw.get("evidence_turn_ids"), candidate_turns)
            reason = _text(raw.get("reason"), 600)
            # A capability dimension needs an explicit answer quote. A model
            # score with no traceable candidate turn is not persisted as fact.
            if not evidence_ids:
                score_value = None
                reason = "回答中没有可定位到原始轮次的充分能力证据。"
            by_key[key] = {
                "key": key,
                "label": DIMENSION_META[key]["label"],
                "weight_pct": DIMENSION_META[key]["weight_pct"],
                "score": score_value,
                "reason": reason or "回答中没有足够依据。",
                "evidence_turn_ids": evidence_ids,
            }

    return [
        by_key.get(key)
        or {
            "key": key,
            "label": label,
            "weight_pct": weight,
            "score": None,
            "reason": "回答中没有足够依据。",
            "evidence_turn_ids": [],
        }
        for key, label, weight in CAPABILITY_DIMENSIONS
    ]


def normalize_capability(
    data: Any,
    turns: Iterable[dict],
    failure: str | None = None,
) -> dict:
    """Validate an interview capability assessment and attach exact answers."""
    turns = [dict(turn) for turn in turns]
    candidate_turns = _candidate_turns(turns)
    if not candidate_turns:
        return {
            "status": "unassessed",
            "score": None,
            "review_required": True,
            "summary": "本次通话没有候选人回答，无法评估能力证据。",
            "dimensions": _dimensions([], {}),
            "evidence": [],
            "evidence_coverage": {"cited_turns": 0, "candidate_turns": 0, "ratio": 0},
            "strengths": [],
            "gaps": [],
            "verification_questions": [],
            "limitations": [CAPABILITY_LIMITATION, "没有候选人回答内容。"],
        }

    payload = data if isinstance(data, dict) else {}
    dimensions = _dimensions(payload.get("dimensions"), candidate_turns)
    available = [item for item in dimensions if item["score"] is not None]
    available_weight = sum(item["weight_pct"] for item in available)
    score = (
        round(
            sum(item["score"] * item["weight_pct"] for item in available)
            / available_weight,
            2,
        )
        if available_weight >= 50
        else None
    )

    evidence_ids = []
    for dimension in available:
        for turn_id in dimension["evidence_turn_ids"]:
            if turn_id not in evidence_ids:
                evidence_ids.append(turn_id)
    substantive_turns = [
        turn_id for turn_id, turn in candidate_turns.items()
        if len(turn["text"]) >= 4
    ]
    coverage = (
        len(evidence_ids) / len(substantive_turns)
        if substantive_turns
        else 0.0
    )

    limitations = [CAPABILITY_LIMITATION]
    if failure:
        limitations.append(f"能力模型未完成评估：{failure[:300]}")
    for item in _texts(payload.get("limitations")):
        if item not in limitations:
            limitations.append(item)

    summary = _text(payload.get("summary"), 800)
    if not summary:
        summary = (
            "已完成基于本次面试回答的能力证据评估。"
            if score is not None
            else "本次回答不足以形成可靠的能力评分，需补充或人工复核。"
        )
    review_required = (
        score is None
        or len(evidence_ids) < 2
        or coverage < 0.5
        or len(available) < 3
        or payload.get("review_required") is True
    )
    return {
        "status": "assessed" if score is not None else "unassessed",
        "score": score,
        "review_required": review_required,
        "summary": summary,
        "dimensions": dimensions,
        "evidence": [
            {"turn_id": turn_id, "text": candidate_turns[turn_id]["text"][:1200]}
            for turn_id in evidence_ids
        ],
        "evidence_coverage": {
            "cited_turns": len(evidence_ids),
            "candidate_turns": len(substantive_turns),
            "ratio": round(coverage, 3),
        },
        "strengths": _texts(payload.get("strengths")),
        "gaps": _texts(payload.get("gaps")),
        "verification_questions": _texts(payload.get("verification_questions")),
        "limitations": limitations[:20],
    }
