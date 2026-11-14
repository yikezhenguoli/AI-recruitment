"""Normalize evidence-backed interview conduct assessments.

The conduct score is deliberately separate from job-fit scoring. It evaluates
observable communication behavior in the transcript only; it does not infer
appearance, accent, emotion, disability, or any other sensitive trait.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

CONDUCT_DIMENSIONS = (
    ("respect", "尊重与边界", 30),
    ("order", "秩序与配合", 30),
    ("integrity", "诚信与作答态度", 25),
    ("professionalism", "职业化表达", 15),
)
DIMENSION_META = {
    key: {"label": label, "weight_pct": weight}
    for key, label, weight in CONDUCT_DIMENSIONS
}

SEVERE_CATEGORIES = {
    "disruption": "故意扰乱秩序",
    "intentional_non_answer": "故意不正常作答",
    "hostility": "顶撞、辱骂或威胁",
    "inappropriate_speech": "不当言论",
}
SEVERITIES = {"minor", "moderate", "severe"}
CONDUCT_LIMITATION = (
    "言行审核仅依据已提交的文字转写，不评价外貌、声线、口音、情绪或任何敏感属性。"
)

# These patterns are intentionally narrow. They are a deterministic safety net
# for unambiguous abuse when the LLM is unavailable, not a general sentiment or
# personality classifier.
_SEVERE_RULES = (
    (
        "hostility",
        re.compile(
            r"(傻逼|傻b|脑残|废物|垃圾面试官|去你妈|操你妈|滚出去|"
            r"你算什么东西|你懂个屁|闭嘴|弄死你|杀了你|找人收拾你)",
            re.IGNORECASE,
        ),
    ),
    (
        "inappropriate_speech",
        re.compile(
            r"(弄死你们|炸死你们|强奸你|性骚扰你|让你们公司倒闭)",
            re.IGNORECASE,
        ),
    ),
)
_INTERVIEWER_INAPPROPRIATE = re.compile(
    r"(?:言行|言语|言论|行为)[^。！？\n]{0,30}(?:不当|违规|失礼|不礼貌)",
    re.IGNORECASE,
)
_INTERVIEWER_ENDING = re.compile(
    r"(?:结束|终止|到此为止|不再继续)",
    re.IGNORECASE,
)


def _text(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _candidate_turn_map(turns: Iterable[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for turn in turns:
        if turn.get("role") != "candidate":
            continue
        turn_id = str(turn.get("id") or "").strip()
        text = _text(turn.get("text"), 20_000)
        if turn_id and text:
            result[turn_id] = {**dict(turn), "id": turn_id, "text": text}
    return result


def _evidence_ids(value: Any, candidate_turns: dict[str, dict]) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for raw in value:
        turn_id = str(raw).strip()
        if turn_id in candidate_turns and turn_id not in result:
            result.append(turn_id)
    return result[:10]


def rule_incidents(turns: Iterable[dict]) -> list[dict]:
    """Find only unambiguous severe abuse in candidate-authored turns."""
    incidents: list[dict] = []
    for turn in _candidate_turn_map(turns).values():
        text = turn["text"]
        for category, pattern in _SEVERE_RULES:
            match = pattern.search(text)
            if match is None:
                continue
            incidents.append(
                {
                    "category": category,
                    "category_label": SEVERE_CATEGORIES[category],
                    "severity": "severe",
                    "description": f"候选人原句包含明确的不当表达：“{match.group(0)}”。",
                    "evidence_turn_ids": [turn["id"]],
                    "quotes": [{"turn_id": turn["id"], "text": text[:1000]}],
                    "source": "rule",
                }
            )
            break
    return incidents


def has_live_candidate_violation(text: str) -> bool:
    """Return true only for unambiguous abuse that can stop a live call."""
    if not isinstance(text, str) or not text.strip():
        return False
    return bool(
        rule_incidents(
            [{"id": "live-candidate", "role": "candidate", "text": text}]
        )
    )


def interviewer_announces_conduct_termination(text: str) -> bool:
    """Recognize the interviewer's explicit conduct-related termination warning."""
    if not isinstance(text, str):
        return False
    return bool(
        _INTERVIEWER_INAPPROPRIATE.search(text)
        and _INTERVIEWER_ENDING.search(text)
    )


def _normalize_dimensions(
    raw_dimensions: Any,
    candidate_turns: dict[str, dict],
) -> list[dict]:
    by_key: dict[str, dict] = {}
    if isinstance(raw_dimensions, list):
        for raw in raw_dimensions[:20]:
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
            reason = _text(raw.get("reason"), 500)
            evidence_ids = _evidence_ids(raw.get("evidence_turn_ids"), candidate_turns)
            by_key[key] = {
                "key": key,
                "label": DIMENSION_META[key]["label"],
                "weight_pct": DIMENSION_META[key]["weight_pct"],
                "score": score_value,
                "reason": reason or "转写中未观察到足够依据。",
                "evidence_turn_ids": evidence_ids,
            }

    result = []
    for key, label, weight in CONDUCT_DIMENSIONS:
        result.append(
            by_key.get(key)
            or {
                "key": key,
                "label": label,
                "weight_pct": weight,
                "score": None,
                "reason": "转写中未观察到足够依据。",
                "evidence_turn_ids": [],
            }
        )
    return result


def _normalize_incidents(
    raw_incidents: Any,
    candidate_turns: dict[str, dict],
) -> list[dict]:
    incidents: list[dict] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    if isinstance(raw_incidents, list):
        for raw in raw_incidents[:20]:
            if not isinstance(raw, dict):
                continue
            category = raw.get("category")
            severity = raw.get("severity")
            if category not in SEVERE_CATEGORIES or severity not in SEVERITIES:
                continue
            evidence_ids = _evidence_ids(raw.get("evidence_turn_ids"), candidate_turns)
            # A conduct incident is not persisted as fact unless it can be
            # traced to the candidate's exact stored turn.
            if not evidence_ids:
                continue
            incident_key = (category, tuple(evidence_ids))
            if incident_key in seen:
                continue
            seen.add(incident_key)
            description = _text(raw.get("description"), 500)
            incidents.append(
                {
                    "category": category,
                    "category_label": SEVERE_CATEGORIES[category],
                    "severity": severity,
                    "description": description or "模型在候选人转写中识别到相关行为。",
                    "evidence_turn_ids": evidence_ids,
                    "quotes": [
                        {"turn_id": turn_id, "text": candidate_turns[turn_id]["text"][:1000]}
                        for turn_id in evidence_ids
                    ],
                    "source": "model",
                }
            )

    for incident in rule_incidents(candidate_turns.values()):
        incident_key = (incident["category"], tuple(incident["evidence_turn_ids"]))
        if incident_key not in seen:
            incidents.append(incident)
            seen.add(incident_key)
    return incidents


def _normalize_texts(value: Any, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for raw in value[:limit]:
        text = _text(raw, 500)
        if text and text not in result:
            result.append(text)
    return result


def normalize_conduct(
    data: Any,
    turns: Iterable[dict],
    failure: str | None = None,
) -> dict:
    """Validate model output and attach exact transcript evidence.

    Model verdicts never become a severe incident without at least one matching
    candidate turn ID. Any validated severe incident forces a veto.
    """
    turns = [dict(turn) for turn in turns]
    candidate_turns = _candidate_turn_map(turns)
    if not candidate_turns:
        return {
            "status": "unassessed",
            "score": None,
            "veto": False,
            "review_required": True,
            "summary": "本次通话没有候选人转写，无法审核言行。",
            "dimensions": _normalize_dimensions([], {}),
            "incidents": [],
            "veto_reasons": [],
            "limitations": [CONDUCT_LIMITATION, "没有候选人转写内容。"],
        }

    payload = data if isinstance(data, dict) else {}
    dimensions = _normalize_dimensions(payload.get("dimensions"), candidate_turns)
    incidents = _normalize_incidents(payload.get("incidents"), candidate_turns)
    severe = [item for item in incidents if item["severity"] == "severe"]

    available = [item for item in dimensions if item["score"] is not None]
    weight = sum(item["weight_pct"] for item in available)
    computed_score = (
        round(sum(item["score"] * item["weight_pct"] for item in available) / weight, 2)
        if weight
        else None
    )
    veto = bool(severe)
    score = 0.0 if veto else computed_score
    if score is not None and not veto:
        # Keep an explicit behavioral incident visible in the numeric result,
        # even when the model's dimension scores are unusually generous.
        if any(item["severity"] == "moderate" for item in incidents):
            score = min(score, 59.0)
        elif any(item["severity"] == "minor" for item in incidents):
            score = min(score, 79.0)

    limitations = [CONDUCT_LIMITATION]
    if failure:
        limitations.append(f"模型审核未完成：{failure[:300]}")
    for item in _normalize_texts(payload.get("limitations")):
        if item not in limitations:
            limitations.append(item)
    if payload.get("veto") is True and not severe:
        limitations.append("模型提出否决，但没有提供可定位到候选人原始转写的严重事件，系统未自动否决。")

    veto_reasons = _normalize_texts(payload.get("veto_reasons"))
    if severe:
        for incident in severe:
            reason = f"{incident['category_label']}：{incident['description']}"
            if reason not in veto_reasons:
                veto_reasons.append(reason)
    else:
        veto_reasons = []

    summary = _text(payload.get("summary"), 800)
    if not summary:
        summary = (
            "识别到需一票否决的严重言行，详见原始转写证据。"
            if veto
            else (
                "已完成基于转写的言行审核。"
                if score is not None
                else "模型未返回可用的言行评分，需人工复核。"
            )
        )

    review_required = (
        score is None
        or (score is not None and score < 60)
        or veto
        or payload.get("review_required") is True
        or any(item["severity"] in {"moderate", "severe"} for item in incidents)
    )
    status = "vetoed" if veto else ("assessed" if score is not None else "unassessed")
    return {
        "status": status,
        "score": score,
        "veto": veto,
        "review_required": review_required,
        "summary": summary,
        "dimensions": dimensions,
        "incidents": incidents,
        "veto_reasons": veto_reasons[:10],
        "limitations": limitations[:20],
    }
