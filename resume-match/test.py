#!/usr/bin/env python3
"""在固定划分的 test 集上评估 best/，并与 TF-IDF + 线性模型基线并排对照。

test 不参与任何模型/超参选择，是唯一可以写进对外结论的指标。
产物写到 <model-dir>/../eval-test/（或 --out-dir）：
  metrics.json / report.txt / confusion_matrix.csv / per_class.csv / predictions.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DEFAULT_CSV, DEFAULT_SPLIT  # noqa: E402
from evaluate import evaluate_split  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="test 集评估：神经模型 vs TF-IDF 经典基线（含配对 bootstrap 区间）。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--model-dir", required=True, help="train.py 保存的 best/ 目录")
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Resume.csv 路径")
    p.add_argument("--split", type=Path, default=DEFAULT_SPLIT, help="固定划分 split.csv（只读）")
    p.add_argument("--out-dir", type=Path, default=None, help="默认 <model-dir>/../eval-test/")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--max-length", type=int, default=None, help="默认沿用 checkpoint 的 infer_config.json")
    p.add_argument("--device", default="auto", help="auto/cpu/cuda/cuda:0")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--baseline", action=argparse.BooleanOptionalAction, default=True,
                   help="是否跑 TF-IDF + LinearSVC/LogReg 基线")
    p.add_argument("--bootstrap", type=int, default=1000, help="配对 bootstrap 次数；0 表示关闭")
    p.add_argument("--max-features", type=int, default=200_000, help="TF-IDF 最大特征数")
    p.add_argument("--allow-dry-run", action="store_true", help="允许评估 --dry-run 的随机权重")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    evaluate_split(
        "test",
        model_dir=args.model_dir,
        csv_path=args.csv,
        split_path=args.split,
        out_dir=args.out_dir,
        batch_size=args.batch_size,
        max_length=args.max_length,
        device=args.device,
        seed=args.seed,
        use_baseline=args.baseline,
        bootstrap_n=args.bootstrap,
        max_features=args.max_features,
        allow_dry_run=args.allow_dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
