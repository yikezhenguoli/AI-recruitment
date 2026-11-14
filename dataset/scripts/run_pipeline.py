#!/usr/bin/env python3
"""总编排：分批生成 → 经历拆解 → 问题 → 追问链 → 全量校验 → 去重分析 → 统计报告。

阶段闸门：
  第二阶段  python3 scripts/run_pipeline.py --stage pilot
  第三阶段  人工审阅 reports/sample_review_report.md 等报告
            python3 scripts/run_pipeline.py --accept --note "人工验收通过"
  第四阶段  python3 scripts/run_pipeline.py --stage full
  第五阶段  自动执行全量校验与最终验收报告

其它：
  --validate-only  仅重新执行校验与统计
  --force          强制重生成已完成批次
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from lib import pipeline  # noqa: E402
from lib.common import log  # noqa: E402


def run(script: str, *args: str) -> None:
    cmd = [sys.executable, os.path.join(HERE, script), *args]
    log("执行：" + " ".join(os.path.basename(x) if x.endswith(".py") else x for x in cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def full_cycle(stage: str, force: bool, strict: bool, batch_size: int | None = None) -> None:
    pipeline.ensure_plan()
    pipeline.ensure_pilot_ids()
    res = pipeline.stage_resumes(stage, batch_size, force)
    log(f"[阶段] 简历批次完成：新增 {res['new']}，失败 {len(res['failed'])}")
    if res["failed"]:
        log("警告：存在失败数据，已进入 logs/generation_state.json 的 failed_resume_ids 队列，可单独重生成")
    pipeline.stage_qa(stage, force)
    pipeline.materialize()
    run("extract_experiences.py")
    run("generate_question_chains.py")
    run("validate_dataset.py", "--stage", stage, *(["--strict"] if strict else []))
    run("deduplicate_dataset.py")
    run("generate_statistics.py", "--stage", stage)
    log(f"=== {stage} 阶段流程结束 ===")
    if stage == "pilot":
        log("下一步：人工验收 reports/ 下 4 份报告；确认后执行 --accept 解除阶段闸门，再 --stage full")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default=None, choices=["pilot", "full"])
    ap.add_argument("--accept", action="store_true", help="记录第三阶段人工验收确认")
    ap.add_argument("--note", default="人工验收确认")
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--strict", action="store_true", help="校验不通过时以非零状态退出")
    args = ap.parse_args()

    if args.accept:
        path = pipeline.mark_acceptance(args.note)
        log(f"阶段闸门已解除：{path}")
        if not args.stage:
            return

    if args.validate_only:
        run("validate_dataset.py", "--stage", "auto", *(["--strict"] if args.strict else []))
        run("deduplicate_dataset.py")
        run("generate_statistics.py", "--stage", "auto")
        return

    stage = args.stage or "pilot"
    full_cycle(stage, args.force, args.strict, args.batch_size)


if __name__ == "__main__":
    main()
