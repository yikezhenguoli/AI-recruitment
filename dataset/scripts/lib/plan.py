"""确定性生成计划：精确配额分配 + 分层试验抽样。

关键性质：
  1. 全量计划 5000 条，工作年限与简历质量的计数与配置文件逐项精确相等；
  2. 岗位通过轮转 + 整体洗牌分配，每岗位 166~167 份，均 >= 100；
  3. 每份简历有独立 item_seed，单份重生成不影响其它简历；
  4. 试验 100 份从全量计划中分层抽取，是最终数据集的真子集。
"""
from __future__ import annotations

import math
import random
from typing import Any

from . import config


def build_plan() -> list[dict[str, Any]]:
    gc = config.get_config("generation_config")
    qd = config.get_config("quality_distribution")
    pc = config.get_config("position_categories")
    total = gc["total_resumes"]
    seed = gc["random_seed"]

    qualities: list[dict[str, Any]] = []
    for item in qd["resume_qualities"]:
        qualities.extend([item] * int(item["count"]))
    assert len(qualities) == total, "简历质量配额合计不等于 total_resumes"

    rng = random.Random(seed ^ 0x5EED10)
    rng.shuffle(qualities)

    order = pc["position_order"]
    cats = pc["categories"]
    positions = [order[i % len(order)] for i in range(total)]
    rng.shuffle(positions)  # 排列，不改变每个岗位的计数

    # 年限分配：按岗位资历偏好加权抽样，同时严格消耗全局年限配额。
    # 每个年限档看作 remaining[k] 个带权球，权重 exp(-|档位-偏好|/tau)，
    # 因此既体现「架构师偏资深、客服偏初级」，又保证档位内部仍有多样性。
    seniority = {"fresh": 0, "junior": 1, "mid": 2, "senior": 3, "expert": 4}
    pref = pc.get("seniority_preference", {})
    level_by_key = {x["key"]: x for x in qd["career_levels"]}
    remaining = {x["key"]: int(x["count"]) for x in qd["career_levels"]}
    assert sum(remaining.values()) == total, "工作年限配额合计不等于 total_resumes"
    tau = 1.25
    levels: list[dict[str, Any] | None] = [None] * total
    order_idx = list(range(total))
    rng.shuffle(order_idx)
    for i in order_idx:
        s = pref.get(positions[i], 2)
        keys = [k for k, v in remaining.items() if v > 0]
        weights = [math.exp(-abs(seniority[k] - s) / tau) * remaining[k] for k in keys]
        chosen = rng.choices(keys, weights=weights, k=1)[0]
        levels[i] = level_by_key[chosen]
        remaining[chosen] -= 1
    assert all(x is not None for x in levels), "年限分配未完成"

    level_rng = random.Random(seed ^ 0xA11CE)
    plan = []
    for i in range(total):
        lv = levels[i]
        ql = qualities[i]
        key = lv["key"]
        if key == "fresh":
            years = 0
        else:
            lo = int(lv["min_years"]) if key != "expert" else 11
            hi = int(lv["max_years"])
            if key == "junior":
                years = level_rng.randint(1, 3)
            elif key == "mid":
                years = level_rng.randint(3, 5)
            elif key == "senior":
                years = level_rng.randint(5, 9)
            else:
                years = level_rng.randint(11, 18)
        idx = i + 1
        plan.append({
            "resume_id": f"RES_{idx:06d}",
            "candidate_id": f"CAN_{idx:06d}",
            "position_id": positions[i],
            "target_position": cats[positions[i]]["name"],
            "family": cats[positions[i]]["family"],
            "career_level": lv["key"],
            "career_level_label": lv["label"],
            "total_work_years": years,
            "resume_quality": ql["key"],
            "resume_quality_label": ql["label"],
            "item_seed": seed + idx * 7919,
            "batch_id": i // gc["batch_size"],
        })
    return plan


def validate_plan(plan: list[dict[str, Any]]) -> dict[str, Any]:
    gc = config.get_config("generation_config")
    qd = config.get_config("quality_distribution")
    pc = config.get_config("position_categories")
    from collections import Counter
    lc = Counter(x["career_level"] for x in plan)
    qc = Counter(x["resume_quality"] for x in plan)
    pcount = Counter(x["position_id"] for x in plan)
    expected_l = {x["key"]: x["count"] for x in qd["career_levels"]}
    expected_q = {x["key"]: x["count"] for x in qd["resume_qualities"]}
    assert dict(lc) == expected_l, f"年限配额不符: {lc}"
    assert dict(qc) == expected_q, f"质量配额不符: {qc}"
    assert len(plan) == gc["total_resumes"], "总数不符"
    assert len(set(x["resume_id"] for x in plan)) == len(plan), "简历 ID 重复"
    assert len(pcount) == len(pc["position_order"]), "岗位覆盖不足 30 类"
    assert min(pcount.values()) >= gc["min_resumes_per_position"], "存在岗位少于 100 份"
    return {
        "total": len(plan),
        "career_levels": dict(lc),
        "resume_qualities": dict(qc),
        "position_min": min(pcount.values()),
        "position_max": max(pcount.values()),
        "positions": len(pcount),
    }


def select_pilot_ids(plan: list[dict[str, Any]], size: int | None = None) -> list[str]:
    """分层抽取试验 ID：覆盖 30 岗位 + 5 年限 + 4 质量型，且分散在全量计划中。"""
    gc = config.get_config("generation_config")
    size = size or gc["pilot_size"]
    rng = random.Random(gc["random_seed"] ^ 0x9A17)
    by_pos: dict[str, list[dict[str, Any]]] = {}
    for row in plan:
        by_pos.setdefault(row["position_id"], []).append(row)

    chosen: dict[str, dict[str, Any]] = {}
    # 每个岗位至少 3 份
    for pid, rows in by_pos.items():
        picks = rng.sample(rows, min(3, len(rows)))
        for r in picks:
            chosen[r["resume_id"]] = r
    # 贪心补齐缺失的年限档与质量型
    need_levels = {x["key"] for x in config.get_config("quality_distribution")["career_levels"]}
    need_qualities = {x["key"] for x in config.get_config("quality_distribution")["resume_qualities"]}
    pool = [r for r in plan if r["resume_id"] not in chosen]
    rng.shuffle(pool)
    for r in pool:
        got_l = {x["career_level"] for x in chosen.values()}
        got_q = {x["resume_quality"] for x in chosen.values()}
        if (need_levels - got_l) or (need_qualities - got_q):
            if r["career_level"] in (need_levels - got_l) or r["resume_quality"] in (need_qualities - got_q):
                chosen[r["resume_id"]] = r
        if len(chosen) >= size:
            break
    # 补足到 size，尽量分散
    for r in pool:
        if len(chosen) >= size:
            break
        if r["resume_id"] not in chosen:
            chosen[r["resume_id"]] = r
    ids = sorted(chosen, key=lambda x: int(x.split("_")[1]))[:size]
    return ids


def load_plan(path: str | None = None) -> list[dict[str, Any]]:
    import json
    import os
    from .common import read_json
    p = path or config.abspath(config.get_config("generation_config")["checkpoint"]["plan_file"])
    if not os.path.exists(p):
        plan = build_plan()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"total": len(plan), "seed": config.get_config("generation_config")["random_seed"],
                       "items": plan}, fh, ensure_ascii=False, indent=1)
        return plan
    return read_json(p)["items"]
