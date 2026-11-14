#!/usr/bin/env python3
"""阶段五：经历级问题生成。

对每份简历的每个事实句生成候选问题，按岗位维度权重、简历质量型、年限档选样，
输出 8~12 道绑定具体 experience_id 的问题。

用法： python3 scripts/generate_questions.py --stage pilot [--force]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import pipeline  # noqa: E402
from lib.common import log, read_jsonl  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="pilot", choices=["pilot", "full"])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    res = pipeline.stage_qa(args.stage, args.force)
    log(f"问题生成完成：问题 {res['questions']} 道，追问链 {res['chains']} 条，"
        f"跳过批次 {res['skipped_batches']} 个")
    pipeline.materialize()
    qs = read_jsonl(pipeline.paths()["questions"])
    from collections import Counter
    per = Counter(q["resume_id"] for q in qs)
    log(f"每份简历问题数范围：{min(per.values()) if per else 0} ~ {max(per.values()) if per else 0}；"
        f"覆盖简历 {len(per)} 份")


if __name__ == "__main__":
    main()
