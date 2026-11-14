#!/usr/bin/env python3
"""阶段二：建立全量 5000 条确定性分配计划，并抽取试验样本 ID。

用法： python3 scripts/generate_candidate_profiles.py [--stage pilot|full]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import config, plan  # noqa: E402
from lib.common import log, write_json  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="pilot", choices=["pilot", "full"])
    args = ap.parse_args()

    pl = plan.load_plan()
    stat = plan.validate_plan(pl)
    log(f"生成计划加载完成：{stat['total']} 条；岗位 {stat['positions']} 类；"
        f"每岗位 {stat['position_min']}~{stat['position_max']} 份")
    log(f"年限分布：{stat['career_levels']}")
    log(f"质量分布：{stat['resume_qualities']}")

    pilot_ids = plan.select_pilot_ids(pl)
    write_json(config.abspath("dataset/metadata/pilot_ids.json"),
               {"stage": "pilot", "size": len(pilot_ids), "ids": pilot_ids})
    by_id = {x["resume_id"]: x for x in pl}
    from collections import Counter
    sub = [by_id[i] for i in pilot_ids]
    log(f"试验样本 {len(pilot_ids)} 份：岗位 {len(set(x['position_id'] for x in sub))} 类；"
        f"年限 {dict(Counter(x['career_level'] for x in sub))}；"
        f"质量 {dict(Counter(x['resume_quality'] for x in sub))}")
    log(f"阶段参数：--stage {args.stage}（本脚本只建立计划，不生成简历）")


if __name__ == "__main__":
    main()
