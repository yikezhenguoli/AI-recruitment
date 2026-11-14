#!/usr/bin/env python3
"""阶段六：为每份简历构建递进式多轮追问链。

从已有问题中选择重要问题作为根问题，围绕同一 experience_id 与同一句原文，
按 事实确认 → 过程细节 → 原理/决策 → 验证与挑战 → 场景迁移 递进展开。
不生成任何候选人回答，每层带 trigger_condition。

用法： python3 scripts/generate_question_chains.py
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import pipeline  # noqa: E402
from lib.common import log, read_jsonl, write_jsonl  # noqa: E402
from lib.question_engine import build_chains_for_resume  # noqa: E402


def main() -> None:
    p = pipeline.paths()
    resumes = read_jsonl(p["resumes"])
    exps = read_jsonl(p["experiences"])
    questions = read_jsonl(p["questions"])
    exp_by_rid: dict[str, list[dict]] = defaultdict(list)
    q_by_rid: dict[str, list[dict]] = defaultdict(list)
    for e in exps:
        exp_by_rid[e["resume_id"]].append(e)
    for q in questions:
        q_by_rid[q["resume_id"]].append(q)

    chains = []
    short = []
    for r in resumes:
        qs = q_by_rid.get(r["resume_id"], [])
        cs = build_chains_for_resume(r, exp_by_rid.get(r["resume_id"], []), qs)
        if len(cs) < 3:
            short.append((r["resume_id"], len(cs)))
        chains.extend(cs)
    chains.sort(key=lambda x: x["chain_id"])
    write_jsonl(p["chains"], chains)
    log(f"追问链重建完成：{len(chains)} 条，覆盖 {len({c['resume_id'] for c in chains})} 份简历")
    if short:
        log(f"警告：{len(short)} 份简历追问链不足 3 条，示例 {short[:5]}")
    assert all(c["experience_id"] for c in chains), "存在未关联经历的追问链"


if __name__ == "__main__":
    main()
