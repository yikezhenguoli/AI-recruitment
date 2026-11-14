"""历史追问意图分析器（纯规则基础模式，默认不调用任何外部服务）。

输入：RISM-001 的 interview_questions.jsonl 与 question_chains.jsonl（只读）
输出：意图签名、相似问题、相似文本不同意图、过宽一级维度、候选二级方向、追问链分析

所有候选方向一律 status=candidate / annotation_status=pending /
annotation_source=historical_question，绝不自动批准。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from ..utils import core

_QTYPE_CN = {
    "clarification": "信息澄清",
    "contribution_verification": "贡献核实",
    "technical_deep_dive": "技术深挖",
    "result_verification": "成果核实",
    "data_verification": "数据核实",
    "scenario_analysis": "场景分析",
    "decision_analysis": "决策分析",
    "problem_investigation": "问题排查",
    "risk_investigation": "风险核实",
    "reflection": "复盘反思",
}

_DIM_CN = {d["id"]: d["name"] for d in core.load_taxonomy()["primary_dimensions"]}


def normalize_question(text: str) -> str:
    """去除经历标题、引用原文、数字与标点，只保留问题骨架用于相似度比较。"""
    t = re.sub(r"《[^》]*》", "", str(text))
    t = re.sub(r"「[^」]*」", "", t)
    t = re.sub(r"\d+(?:\.\d+)?%?", "", t)
    t = re.sub(r"[\s，。？！、；：\"'“”‘’（）()【】\[\]—\-…·.,!?]", "", t)
    return t


def ngrams(text: str, n: int = 3) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def intent_signature(q: dict[str, Any]) -> str:
    goals = "|".join(sorted(set(q.get("expected_investigation") or [])))
    return f"{q.get('question_type')}::{q.get('dimension')}::{goals}"


def check_external_llm(cfg: dict[str, Any], *, requested: bool, confirmed: bool) -> dict[str, Any]:
    """外部 LLM 门禁。默认关闭；启用时返回将要发送的数据字段与目标服务清单。"""
    llm = cfg["llm"]
    if not llm["enabled"]:
        return {"used": False, "reason": "外部 LLM 默认关闭，本次分析未发送任何数据",
                "fields_to_send": [], "endpoint": None}
    if not requested:
        return {"used": False, "reason": "配置已启用 LLM 但命令行未传 --enable-llm，本次未调用",
                "fields_to_send": llm["fields_to_send"], "endpoint": llm["endpoint"]}
    if llm["require_explicit_confirm"] and not confirmed:
        raise PermissionError(
            "外部 LLM 需要显式确认。将发送字段："
            f"{llm['fields_to_send']}；目标服务：{llm['provider']} / {llm['endpoint']}。"
            "如确认，请追加 --confirm-external，并确保数据已脱敏且获得用户授权。")
    return {"used": False, "reason": "本任务不执行外部调用（占位）",
            "fields_to_send": llm["fields_to_send"], "endpoint": llm["endpoint"]}


def analyze(cfg: dict[str, Any] | None = None, *, llm_requested: bool = False,
            llm_confirmed: bool = False) -> dict[str, Any]:
    cfg = cfg or core.load_config()
    from ..parsers import jsonl as parser  # 延迟导入避免循环

    idx = parser.load_source_index(cfg)
    questions, chains = idx["questions"], idx["chains"]
    tax = core.load_taxonomy(cfg)
    acfg = cfg["analysis"]

    # 1) 意图签名
    sig_map: dict[str, dict[str, Any]] = {}
    for q in questions:
        sig = intent_signature(q)
        rec = sig_map.setdefault(sig, {
            "signature": sig, "count": 0, "question_type": q.get("question_type"),
            "dimension": q.get("dimension"), "goals": [], "sample_question_ids": [],
        })
        rec["count"] += 1
        for g in q.get("expected_investigation") or []:
            if g not in rec["goals"]:
                rec["goals"].append(g)
        if len(rec["sample_question_ids"]) < 5:
            rec["sample_question_ids"].append(q.get("question_id"))
    signatures = sorted(sig_map.values(), key=lambda x: (-x["count"], x["signature"]))

    # 2) 相似问题（同一 question_type 组内比较，字符 n-gram Jaccard）
    n = acfg["ngram"]
    threshold = acfg["similarity_threshold"]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for q in questions:
        groups[q.get("question_type", "unknown")].append(q)
    prepared = [(q, ngrams(normalize_question(q.get("question", "")), n)) for q in questions]
    by_type: dict[str, list[tuple[dict[str, Any], set[str]]]] = defaultdict(list)
    for q, grams in prepared:
        by_type[q.get("question_type", "unknown")].append((q, grams))

    similar_pairs: list[dict[str, Any]] = []
    similar_total = 0
    for qtype, items in by_type.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                score = jaccard(items[i][1], items[j][1])
                if score < threshold:
                    continue
                similar_total += 1
                if len(similar_pairs) < 40:
                    similar_pairs.append({
                        "question_id_1": items[i][0].get("question_id"),
                        "question_id_2": items[j][0].get("question_id"),
                        "question_type": qtype,
                        "similarity": round(score, 4),
                        "same_dimension": items[i][0].get("dimension") == items[j][0].get("dimension"),
                        "note": "语义高度相似、表达不同",
                    })

    # 3) 相似文本但考察目标不同（同一原文锚点 / 同一经历 + 相似问法）
    by_quote: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for q in questions:
        ref = q.get("reference") or {}
        quote = ref.get("original_text") if isinstance(ref, dict) else None
        if isinstance(quote, str) and quote:
            by_quote[quote].append(q)
    same_text_diff_intent: list[dict[str, Any]] = []
    for quote, group in by_quote.items():
        intents = sorted({(q.get("dimension"), q.get("question_type")) for q in group})
        if len(intents) < 2:
            continue
        same_text_diff_intent.append({
            "quote_fingerprint": core.sha256_text(quote)[:12],
            "question_count": len(group),
            "distinct_intents": len(intents),
            "intents": [f"{d}/{t}" for d, t in intents],
            "sample_question_ids": [q.get("question_id") for q in group[:5]],
        })
    same_text_diff_intent.sort(key=lambda x: (-x["distinct_intents"], -x["question_count"]))

    # 3b) 引用同一段经历原文但考察目标不同（文本依据相同、意图不同）
    # 采用可判定信号，不依赖脆弱的文本相似度阈值；附真实问题骨架相似度供参考。
    grams_by_qid = {q.get("question_id"): grams for q, grams in prepared}
    cross_intent_pairs: list[dict[str, Any]] = []
    cross_total = 0
    for quote, group in by_quote.items():
        intents = {(q.get("dimension"), q.get("question_type")) for q in group}
        if len(intents) < 2:
            continue
        fp = core.sha256_text(quote)[:12]
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if (a.get("dimension"), a.get("question_type")) == \
                   (b.get("dimension"), b.get("question_type")):
                    continue
                cross_total += 1
                if len(cross_intent_pairs) < 40:
                    cross_intent_pairs.append({
                        "quote_fingerprint": fp,
                        "experience_id": a.get("experience_id"),
                        "question_id_1": a.get("question_id"),
                        "question_id_2": b.get("question_id"),
                        "dimension_1": a.get("dimension"),
                        "dimension_2": b.get("dimension"),
                        "question_type_1": a.get("question_type"),
                        "question_type_2": b.get("question_type"),
                        "skeleton_similarity": round(jaccard(
                            grams_by_qid.get(a.get("question_id"), set()),
                            grams_by_qid.get(b.get("question_id"), set())), 4),
                        "note": "引用同一段经历原文，但考察维度或问题类型不同",
                    })

    # 4) 一级维度过宽：同维度下出现多种考察目标不同的问题类型
    dim_types: dict[str, Counter] = defaultdict(Counter)
    for q in questions:
        dim_types[q.get("dimension")][q.get("question_type")] += 1
    broad_dimensions = []
    for dim, counter in sorted(dim_types.items()):
        effective = {t: c for t, c in counter.items() if c >= acfg["min_intent_support"]}
        if len(effective) >= 2:
            broad_dimensions.append({
                "dimension": dim,
                "dimension_name": _DIM_CN.get(dim, dim),
                "distinct_question_types": len(effective),
                "question_type_counts": dict(sorted(effective.items())),
                "reason": "同一一级维度下存在多种考察目标不同的问题类型，一级维度无法准确表达具体追问意图",
            })

    # 5) 候选二级方向：(question_type, dimension) 组合 + 真实辅助维度聚合（多对多）
    combos: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for q in questions:
        combos[(q.get("question_type"), q.get("dimension"))].append(q)
    candidates: list[dict[str, Any]] = []
    for (qtype, dim), group in sorted(combos.items(), key=lambda kv: -len(kv[1])):
        if len(group) < acfg["min_intent_support"]:
            continue
        if len(candidates) >= acfg["max_candidate_directions"]:
            break
        parent = [dim]
        secondary_support: Counter = Counter()
        for q in group:
            for s in q.get("secondary_dimensions") or []:
                if s in _DIM_CN and s not in parent:
                    secondary_support[s] += 1
        # 辅助维度只在支持率足够高时纳入，且最多 2 个，避免二级方向退化为宽泛标签
        support_threshold = max(2, int(len(group) * 0.25))
        for s, c in secondary_support.most_common(2):
            if c >= support_threshold:
                parent.append(s)
        goals = Counter(g for q in group for g in (q.get("expected_investigation") or []))
        top_goals = [g for g, _ in goals.most_common(4)]
        reasons = Counter(r for q in group for r in re.split(r"[，。；、]", q.get("reason", "")) if len(r) >= 4)
        did = f"hist_{qtype}__{dim}"
        candidates.append({
            "direction_id": did,
            "direction_name": f"{_QTYPE_CN.get(qtype, qtype)}·{_DIM_CN.get(dim, dim)}",
            "parent_dimensions": parent,
            "definition": f"围绕「{_QTYPE_CN.get(qtype, qtype)}」考察目标，验证候选人在{_DIM_CN.get(dim, dim)}方面的具体事实与依据，重点获取：{'、'.join(top_goals) if top_goals else '可核对的过程信息'}。",
            "inclusion_criteria": [
                f"历史问题类型为 {qtype} 且主维度为 {dim}",
                "问题引用了具体经历原文，且存在可核对的考察目标",
            ],
            "exclusion_criteria": [
                "仅复述简历内容、未指向具体考察目标的问题",
                "跨经历混合或无法追溯到原文的问题",
            ],
            "evidence_types": top_goals or ["可核对的过程记录"],
            "typical_trigger_claims": [g for g, _ in goals.most_common(6)],
            "related_directions": [],
            "applicable_position_families": [],
            "status": "candidate",
            "version": cfg["ontology_version"],
            "origin": {
                "source": "historical_question",
                "question_count": len(group),
                "signature": f"{qtype}::{dim}",
                "secondary_dimension_support": dict(secondary_support),
                "top_reason_phrases": [r for r, _ in reasons.most_common(3)],
                "sample_question_ids": [q.get("question_id") for q in group[:5]],
                "auto_approved": False,
            },
            "review": core.review_block(source="historical_question", status="pending",
                                        review_reason="历史问题仅为方向发现依据，需人工审核后方可批准",
                                        cfg=cfg),
        })

    # 6) 追问链分析（递进、触发条件、难度阶梯）
    level_counter: Counter = Counter()
    trigger_counter: Counter = Counter()
    purpose_counter: Counter = Counter()
    level_sequences: Counter = Counter()
    for c in chains:
        items = c.get("questions") or []
        level_sequences[" → ".join(str(it.get("level")) for it in items)] += 1
        for it in items:
            level_counter[it.get("level")] += 1
            trigger_counter[it.get("trigger_condition", "")] += 1
            purpose_counter[it.get("purpose", "")] += 1
    chain_analysis = {
        "chain_count": len(chains),
        "depth_distribution": dict(sorted(Counter(c.get("chain_depth") for c in chains).items())),
        "level_distribution": dict(level_counter),
        "top_level_sequences": [{"sequence": k, "count": v} for k, v in level_sequences.most_common(8)],
        "distinct_trigger_conditions": len(trigger_counter),
        "top_trigger_conditions": [{"condition": k, "count": v} for k, v in trigger_counter.most_common(8)],
        "distinct_purposes": len(purpose_counter),
        "difficulty_mapping": tax["chain_level_to_difficulty"],
    }

    llm_state = check_external_llm(cfg, requested=llm_requested, confirmed=llm_confirmed)

    summary = {
        "questions_analyzed": len(questions),
        "chains_analyzed": len(chains),
        "distinct_intent_signatures": len(signatures),
        "distinct_question_type_dimension_combinations": len(combos),
        "similar_question_pairs_total": similar_total,
        "cross_dimension_similar_pairs": cross_total,
        "quotes_with_multiple_intents": len(same_text_diff_intent),
        "broad_primary_dimensions": len(broad_dimensions),
        "candidate_directions_generated": len(candidates),
        "candidate_directions_auto_approved": 0,
        "secondary_dimensions_recovered": sum(
            1 for q in questions if q.get("secondary_dimensions")),
        "llm_used": llm_state["used"],
    }

    return {
        "version": cfg["ontology_version"],
        "generated_at": core.now_iso(),
        "mode": "rule_based_baseline",
        "summary": summary,
        "llm": llm_state,
        "intent_signatures": signatures,
        "similar_question_pairs": similar_pairs,
        "cross_intent_similar_pairs": cross_intent_pairs,
        "same_text_different_intent": same_text_diff_intent[:60],
        "broad_dimensions": broad_dimensions,
        "candidate_directions": candidates,
        "chain_analysis": chain_analysis,
    }


def candidate_direction_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    return result["candidate_directions"]
