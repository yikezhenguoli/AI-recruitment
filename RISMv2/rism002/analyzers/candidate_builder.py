"""从真实经历原文派生 Claim / Evidence Gap / Strategy 候选（全部 pending）。

核心约束：
- 所有 source_text 必须是 resume_experiences.original_content 的真实子串
- Evidence Gap 仅表示「简历未提供足够信息」，不推断能力缺失或经历造假
- 候选一律 annotation_status=pending / reviewed=false，不自动进入正式数据集
- 不虚构候选人回答；Strategy 的 expected_answer_signals 只描述「应出现的信息类型」
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from ..utils import core
from ..parsers import jsonl as parser

CLAIM_PRIORITY = [
    "quantified_achievement", "technical_method", "decision", "problem_resolution",
    "leadership", "collaboration", "innovation", "responsibility", "qualitative_achievement",
]
GAP_DEFAULT = "missing_process"


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？；])", str(text))
    return [p.strip() for p in parts if p.strip()]


def sentence_spans(text: str) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    pos = 0
    for s in split_sentences(text):
        start = text.find(s, pos)
        if start < 0:
            continue
        out.append((s, start, start + len(s)))
        pos = start + len(s)
    return out


def classify_claim(sentence: str, tax: dict[str, Any]) -> str:
    if re.search(r"\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?\s*倍|从\s*\d|降至\s*\d|提升至\s*\d", sentence):
        return "quantified_achievement"
    cues = {c["id"]: c["cues"] for c in tax["claim_types"]}
    scored = []
    for cid in CLAIM_PRIORITY:
        hits = sum(1 for cue in cues.get(cid, []) if cue in sentence)
        if hits:
            scored.append((hits, -CLAIM_PRIORITY.index(cid), cid))
    return max(scored)[2] if scored else "responsibility"


def classify_gap(text: str, tax: dict[str, Any]) -> str:
    cues = {g["id"]: g["cues"] for g in tax["gap_types"]}
    best, best_hits = GAP_DEFAULT, 0
    for gid, glist in cues.items():
        hits = sum(1 for cue in glist if cue in text)
        if hits > best_hits:
            best, best_hits = gid, hits
    return best


def select_experiences(idx: dict[str, Any], tax: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """按 (岗位族, 经历类型) 轮转抽样，保证 12 段经历覆盖多样性；确定性。"""
    pos_to_family = {}
    for fam in tax["position_families"]:
        for pid in fam["position_ids"]:
            pos_to_family[pid] = fam["id"]
    asked = {q.get("experience_id") for q in idx["questions"]}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for e in idx["experiences"]:
        if e.get("experience_id") not in asked:
            continue
        fam = pos_to_family.get(e.get("position_id"), "unknown")
        groups[(fam, e.get("experience_type", "unknown"))].append(e)
    for key in groups:
        groups[key].sort(key=lambda x: x["experience_id"])

    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    keys = sorted(groups)
    round_no = 0
    while len(chosen) < limit and round_no < 50:
        added = False
        for key in keys:
            if round_no >= len(groups[key]):
                continue
            e = groups[key][round_no]
            if e["experience_id"] in seen:
                continue
            chosen.append(e)
            seen.add(e["experience_id"])
            added = True
            if len(chosen) >= limit:
                break
        if not added:
            break
        round_no += 1
    return chosen


def build_candidates(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or core.load_config()
    tax = core.load_taxonomy(cfg)
    idx = parser.load_source_index(cfg)
    limit = cfg["dataset"]["sample_experience_limit"]
    chosen = select_experiences(idx, tax, limit)

    # 目录中的候选方向 ID（用于 Strategy 的方向引用）
    dpath = core.out_path("directions", cfg)
    directions = core.read_json(dpath)["directions"] if dpath.exists() else []
    dir_by_id = {d["direction_id"]: d for d in directions}

    q_by_exp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for q in idx["questions"]:
        q_by_exp[q.get("experience_id")].append(q)
    chain_by_exp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in idx["chains"]:
        chain_by_exp[c.get("experience_id")].append(c)

    claims: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    strategies: list[dict[str, Any]] = []
    review = lambda source: core.review_block(  # noqa: E731
        source=source, status="pending",
        review_reason="规则派生候选，需人工逐条审核后方可进入正式数据集", cfg=cfg)

    for e in chosen:
        eid = e["experience_id"]
        rid = e["resume_id"]
        content = e["original_content"]
        sentences = sentence_spans(content)[: cfg["dataset"]["max_claims_per_experience"]]

        # --- Claims：每一句真实原文 = 一条主张
        exp_claim_ids: list[str] = []
        for n, (sentence, s, t) in enumerate(sentences, start=1):
            cid = f"CLM_{eid[-6:]}_{n:02d}"
            claims.append({
                "claim_id": cid,
                "experience_id": eid,
                "resume_id": rid,
                "claim_type": classify_claim(sentence, tax),
                "claim_text": sentence.rstrip("。；"),
                "source_text": sentence,
                "source_span": {"start_offset": s, "end_offset": t},
                "confidence": 0.6,
                "review": review("rule_based"),
            })
            exp_claim_ids.append(cid)
        if not exp_claim_ids:
            continue

        # --- Evidence Gaps：只描述信息缺失，不作能力/真实性判断
        exp_gap_ids: list[str] = []
        gap_items = list(e.get("potential_risks") or []) + list(e.get("missing_information") or [])
        for n, item in enumerate(gap_items[: cfg["dataset"]["max_gaps_per_experience"]], start=1):
            gid = f"GAP_{eid[-6:]}_{n:02d}"
            gaps.append({
                "gap_id": gid,
                "experience_id": eid,
                "resume_id": rid,
                "related_claim_ids": exp_claim_ids[:2],
                "gap_type": classify_gap(str(item), tax),
                "description": f"简历未提供：{item}。此项仅表示信息不足，需在面试中进一步核实；不代表候选人不具备相关能力，也不代表经历存在造假。",
                "source_text": None,
                "source_span": None,
                "review": review("rule_based"),
            })
            exp_gap_ids.append(gid)

        # --- Strategies：基于该经历真实历史问题 + 已生成的 Claim / Gap
        hist_questions = sorted(q_by_exp.get(eid, []), key=lambda q: q.get("question_id", ""))
        hist_chains = chain_by_exp.get(eid, [])
        triggers = [it.get("trigger_condition") for c in hist_chains
                    for it in (c.get("questions") or []) if it.get("trigger_condition")]
        levels = [it.get("level") for c in hist_chains for it in (c.get("questions") or [])]
        diff_map = tax["chain_level_to_difficulty"]
        qt_map = tax["question_type_to_strategy_type"]

        for n, q in enumerate(hist_questions[: cfg["dataset"]["max_strategies_per_experience"]], start=1):
            did = f"hist_{q.get('question_type')}__{q.get('dimension')}"
            if did not in dir_by_id:
                continue
            d = dir_by_id[did]
            sid = f"STR_{eid[-6:]}_{n:02d}"
            goals = list(q.get("expected_investigation") or [])
            difficulty = diff_map.get(levels[n - 1], "L2") if levels else "L2"
            strategies.append({
                "strategy_id": sid,
                "experience_id": eid,
                "dimension": q.get("dimension"),
                "direction_id": did,
                "direction_name": d["direction_name"],
                "trigger_claim_ids": exp_claim_ids[:2],
                "trigger_gap_ids": exp_gap_ids[:1],
                "rationale": f"依据该经历的历史追问理由：{q.get('reason', '')}".strip(),
                "investigation_goal": "、".join(goals) if goals else "核实该经历的可追溯事实与依据",
                "evidence_to_obtain": goals,
                "risk_signals": [str(x) for x in (e.get("potential_risks") or [])[:2]],
                "expected_answer_signals": [
                    "回答中应出现可核对的时间、参与人与交付物",
                    "回答中应说明具体执行过程与判断依据",
                    "回答中应给出指标口径或对比基准（如涉及量化结果）",
                ],
                "follow_up_triggers": list(dict.fromkeys(triggers))[:3],
                "strategy_type": qt_map.get(q.get("question_type"), "process_reconstruction"),
                "priority": q.get("priority") if q.get("priority") in ("high", "medium", "low") else "medium",
                "difficulty": difficulty,
                "sequence": n,
                "prerequisites": [f"STR_{eid[-6:]}_{n - 1:02d}"] if n > 1 else [],
                "label_status": "unknown",
                "review": review("historical_question"),
            })

    return {
        "version": cfg["ontology_version"],
        "generated_at": core.now_iso(),
        "selected_experience_ids": [e["experience_id"] for e in chosen],
        "position_family_coverage": sorted({e.get("position_id") for e in chosen}),
        "experience_type_coverage": sorted({e.get("experience_type") for e in chosen}),
        "claims": claims,
        "evidence_gaps": gaps,
        "strategies": strategies,
        "note": "全部为规则派生候选（pending / reviewed=false），未经人工审核不得进入正式数据集。",
    }
