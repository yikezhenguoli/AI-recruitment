"""0~100 质量评分；权重与扣分全部来自 config/scoring_rules.yaml。"""
from __future__ import annotations

from typing import Any

from . import config

_RULES = None


def rules() -> dict[str, Any]:
    global _RULES
    if _RULES is None:
        _RULES = config.get_config("scoring_rules")
    return _RULES


def _weighted(parts: dict[str, float], weights: dict[str, float]) -> int:
    total_w = sum(weights.values()) or 1
    score = sum(parts.get(k, 0.7) * w for k, w in weights.items()) / total_w * 100
    return max(0, min(100, int(round(score))))


def score_resume(resume: dict[str, Any], experiences: list[dict[str, Any]]) -> int:
    r = rules()
    q = resume["resume_quality"]
    qs = resume.get("quality_signals", {})
    n_exp = len(experiences)
    parts = {
        "information_completeness": min(1.0, 0.45 + 0.055 * n_exp),
        "timeline_consistency": 0.95 if q != "contradictory" else 0.80,
        "position_match": 1.0 if resume.get("skills") else 0.5,
        "authenticity_expression": 1.0 if q in ("high", "normal") else 0.82,
        "experience_richness": min(1.0, 0.35 + 0.10 * n_exp),
        "language_naturalness": 0.95 if len(resume.get("resume_text", "")) > 400 else 0.7,
    }
    _ = qs
    return _weighted(parts, r["resume_weights"])


def score_experience(exp: dict[str, Any]) -> int:
    r = rules()
    text = exp.get("original_content", "")
    facts = exp.get("fact_count", max(1, len(text) // 25))
    parts = {
        "description_clarity": 0.6 if "相关工作" in text else 0.95,
        "responsibility_clarity": 0.55 if "参与并配合" in text else 0.92,
        "detail_richness": min(1.0, 0.35 + 0.13 * facts),
        "achievement_verifiability": 1.0 if exp.get("achievements") else 0.65,
        "probe_value": min(1.0, 0.4 + 0.12 * len(exp.get("missing_information", [])) + 0.06 * facts),
    }
    return _weighted(parts, r["experience_weights"])


def score_question(q: dict[str, Any], hard_gate_passed: bool = True) -> int:
    r = rules()
    if not hard_gate_passed:
        return 0
    parts = {
        "experience_link_accuracy": 1.0,
        "reference_accuracy": 1.0,
        "targeting": 0.92 if len(q.get("question", "")) >= 30 else 0.6,
        "probe_depth": 0.9 if len(q.get("expected_investigation", [])) >= 2 else 0.6,
        "position_relevance": 0.9 if q.get("reason") else 0.5,
        "interview_practicality": 0.9,
        "independence": 0.85,
    }
    s = _weighted(parts, r["question_weights"])
    if len(q.get("question", "")) < 20:
        s -= r["deductions"]["too_short_question"]
    return max(0, min(100, s))


def score_chain(chain: dict[str, Any]) -> int:
    r = rules()
    qs = chain.get("questions", [])
    parts = {
        "single_experience": 1.0,
        "progression": 1.0 if len({x["level"] for x in qs}) == len(qs) else 0.6,
        "purpose_clarity": 1.0 if all(x.get("purpose") for x in qs) else 0.5,
        "trigger_condition": 1.0 if all(x.get("trigger_condition") for x in qs) else 0.5,
        "non_repetition": 1.0 if len({x["question"] for x in qs}) == len(qs) else 0.5,
        "evidence_based": 1.0 if all("「" in x["question"] for x in qs) else 0.6,
    }
    return _weighted(parts, r["chain_weights"])
