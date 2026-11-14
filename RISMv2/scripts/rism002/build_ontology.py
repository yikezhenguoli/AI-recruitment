#!/usr/bin/env python3
"""阶段五（辅助）：从历史候选方向构建初始本体文件。

用法：python3 scripts/rism002/build_ontology.py

生成：
    data/ontology/position_competencies.json
    data/ontology/investigation_directions.json

所有方向初始 status=candidate / annotation_status=pending / source=historical_question，
脚本绝不自动批准任何方向。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rism002.analyzers import ontology_builder  # noqa: E402
from rism002.utils import core  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="构建 RISM-002 初始方向目录")
    ap.add_argument("--config", help="主配置路径")
    args = ap.parse_args(argv)
    try:
        cfg = core.load_config(args.config)
        core.ensure_dirs(cfg)
        directions, competencies = ontology_builder.build_all(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"[RISM-002] 本体构建异常: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"[RISM-002] 本体构建完成 | 方向 {len(directions['directions'])} "
          f"(candidate={directions['status_counts']['candidate']}, "
          f"approved={directions['status_counts']['approved']}) | "
          f"多父维度方向 {directions['multi_parent_direction_count']} | "
          f"岗位能力 {competencies['competency_count']} / 岗位族 {competencies['position_family_count']} | "
          f"自动批准 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
