#!/usr/bin/env python3
"""阶段六：RISM-002 主训练数据集质量校验。

校验项（对应需求 8.5）：
    JSON Schema / 引用 ID / Claim 原文对应 / Gap 关联 Claim / Strategy 合法方向
    Positive-Negative-Unknown 三态 / 重复策略 / 优先级与难度 / ontology_version
    数据泄漏与重复 / RISM-001 只读资产未被修改 / 未审核记录硬性门槛

用法：
    python3 scripts/rism002/validate_dataset.py
    python3 scripts/rism002/validate_dataset.py --strict
    python3 scripts/rism002/validate_dataset.py --samples /path/to/samples.jsonl

输出：
    outputs/rism002/dataset_validation_result.json
    outputs/rism002/06_dataset_validation_report.md
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rism002.reports import render  # noqa: E402
from rism002.utils import core  # noqa: E402
from rism002.validators import dataset_validator  # noqa: E402

CHECK_NAMES = [
    ("json_schema", "JSON Schema 结构"),
    ("reference_ids", "全部引用 ID 存在且一致"),
    ("source_text", "Claim.source_text 对应经历原文"),
    ("gap_claim", "Evidence Gap 关联同经历 Claim"),
    ("strategy_direction", "Strategy 仅引用 approved 方向"),
    ("three_state_label", "Positive / Negative / Unknown 三态合法"),
    ("duplicate_strategy", "无重复策略"),
    ("priority_difficulty", "优先级与难度枚举合法"),
    ("ontology_version", "ontology_version 全局一致"),
    ("leakage", "无明显泄漏或重复样本"),
    ("readonly_assets", "RISM-001 只读资产零改动"),
    ("unreviewed_gate", "未审核记录未进入正式数据集"),
]


def _classify_errors(errors: list[str]) -> dict[str, int]:
    """把错误按校验项归类，用于报告展示覆盖度。"""
    keys = {
        "缺少必需字段": "json_schema", "类型应为": "json_schema", "取值": "json_schema",
        "不在枚举": "json_schema", "不匹配模式": "json_schema", "长度不足": "json_schema",
        "不存在": "reference_ids", "不一致": "reference_ids", "跨经历": "reference_ids",
        "source_text": "source_text", "source_span": "source_text",
        "Gap": "gap_claim", "Evidence Gap": "gap_claim",
        "方向": "strategy_direction", "direction": "strategy_direction",
        "label": "three_state_label", "negative": "three_state_label",
        "positive": "three_state_label", "unknown": "three_state_label",
        "重复策略": "duplicate_strategy",
        "priority": "priority_difficulty", "difficulty": "priority_difficulty",
        "ontology_version": "ontology_version",
        "只读资产": "readonly_assets",
        "未通过人工审核": "unreviewed_gate",
    }
    out: Counter = Counter()
    for e in errors:
        hit = "leakage"
        for token, key in keys.items():
            if token in e:
                hit = key
                break
        out[hit] += 1
    return dict(out)


def report(result: dict[str, Any], cfg: dict[str, Any]) -> Path:
    stats = result["statistics"]
    classified = _classify_errors(result["errors"])
    check_rows = [[desc, classified.get(key, 0),
                   "通过" if classified.get(key, 0) == 0 else "未通过"]
                  for key, desc in CHECK_NAMES]

    summary = {
        "校验结论": "通过" if result["passed"] else "未通过",
        "数据集状态": result.get("dataset_status", "unknown"),
        "样本数": stats.get("sample_count", 0),
        "错误数": result["error_count"],
        "警告数": result["warning_count"],
        "ontology_version": cfg["ontology_version"],
        "已批准方向数": stats.get("approved_direction_count_in_ontology", 0),
    }
    sections: list[tuple[str, str]] = [
        ("1. 校验摘要", render.kv_table(summary)),
        ("2. 校验项覆盖", render.md_table(["校验项", "命中错误数", "结论"], check_rows)),
        ("3. 硬性门槛", render.kv_table({
            "未审核记录泄漏": stats.get("hard_gate_unreviewed_records", 0),
            "Claim 原文不对应": stats.get("hard_gate_bad_source_text", 0),
            "只读资产被改动": len(stats.get("readonly_assets_changed", [])),
            "自动生成的 negative 方向": "0（构建器从不生成 negative，仅接受人工审核记录）",
        })),
        ("4. 数据规模与分布", render.kv_table({
            "简历数": stats.get("resume_count", 0),
            "候选人数": stats.get("candidate_count", 0),
            "经历数": stats.get("experience_count", 0),
            "Claim 数": stats.get("claim_count", 0),
            "Gap 数": stats.get("gap_count", 0),
            "Strategy 数": stats.get("strategy_count", 0),
            "方向标注数": stats.get("direction_annotation_count", 0),
            "重复策略数": stats.get("duplicate_strategy_count", 0),
            "重复经历文本数": stats.get("duplicate_experience_texts", 0),
        })),
        ("5. 三态标注分布", render.md_table(
            ["label_status", "数量"], sorted(stats.get("label_status_distribution", {}).items()))),
        ("6. 错误明细（最多 30 条）", render.bullet_list(result["errors"][:30])
            if result["errors"] else "无错误。"),
        ("7. 警告明细（最多 30 条）", render.bullet_list(result["warnings"][:30])
            if result["warnings"] else "无警告。"),
        ("8. 状态说明",
         "数据集为空属预期状态：所有候选 Claim / Gap / Strategy 与追问方向均为 pending，"
         "在人工审核完成前不得进入正式数据集。校验器不会把未出现的方向自动判为 negative，"
         "也不会把 unverified 的 AI/规则输出标记为 reviewed。"),
    ]
    return render.write_report(
        core.resolve(cfg["paths"]["output_dir"], cfg) / "06_dataset_validation_report.md",
        "RISM-002 主数据集校验报告", sections,
        meta={"执行脚本": "scripts/rism002/validate_dataset.py",
              "配置文件": "configs/rism002.json",
              "隐私": "报告仅含 ID / 计数 / 枚举，不含简历正文与个人信息"})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="校验 RISM-002 主训练数据集")
    ap.add_argument("--config", help="主配置路径")
    ap.add_argument("--samples", help="指定样本 JSONL（默认读取配置中的 processed_samples）")
    ap.add_argument("--strict", action="store_true", help="存在警告时也返回非零退出码")
    ap.add_argument("--no-report", action="store_true", help="只输出 JSON 结果，不生成 Markdown")
    args = ap.parse_args(argv)

    try:
        cfg = core.load_config(args.config)
        if args.samples:
            rows, parse_errors = core.read_jsonl(args.samples, strict=False)
            result = dataset_validator.validate(cfg, samples=rows)
            result["errors"] = parse_errors + result["errors"]
            result["error_count"] = len(result["errors"])
            result["passed"] = result["error_count"] == 0
        else:
            result = dataset_validator.validate(cfg)
        core.write_json(core.resolve(cfg["paths"]["output_dir"], cfg)
                        / "dataset_validation_result.json", result)
        if not args.no_report:
            path = report(result, cfg)
            print(f"[RISM-002] 校验报告: {path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[RISM-002] 校验失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"[RISM-002] 数据集校验: {'通过' if result['passed'] else '未通过'} | "
          f"状态 {result.get('dataset_status')} | 样本 {result['statistics']['sample_count']} | "
          f"错误 {result['error_count']} | 警告 {result['warning_count']}")
    if not result["passed"]:
        return 1
    if args.strict and result["warning_count"]:
        print("[RISM-002] --strict：存在警告，返回非零", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
