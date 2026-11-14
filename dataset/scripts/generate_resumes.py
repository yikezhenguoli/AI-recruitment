#!/usr/bin/env python3
"""阶段三：按批次生成完整模拟简历（含事实句级中间结构）。

用法： python3 scripts/generate_resumes.py --stage pilot [--batch-size 100] [--force]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import pipeline  # noqa: E402
from lib.common import log  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="pilot", choices=["pilot", "full"])
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="强制重生成已完成批次")
    args = ap.parse_args()
    res = pipeline.stage_resumes(args.stage, args.batch_size, args.force)
    log(f"简历生成完成：新增 {res['new']} 份，跳过 {res['skipped']} 份，"
        f"失败 {len(res['failed'])} 份，批次 {res['batches']} 个")
    if res["failed"]:
        for f in res["failed"][:10]:
            log(f"  失败：{f['resume_id']} -> {f['error']}")
    pipeline.materialize()


if __name__ == "__main__":
    main()
