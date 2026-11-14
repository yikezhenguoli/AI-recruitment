#!/usr/bin/env python3
"""阶段五：追问方向目录与岗位能力目录校验。

用法：
    python3 scripts/rism002/validate_ontology.py
    python3 scripts/rism002/validate_ontology.py --strict

校验：ID 唯一性、一级维度引用、关联方向存在性、依赖环、状态合法性、
定义字段完整性、审核状态一致性、岗位能力引用、版本一致性。
输出：outputs/rism002/05_ontology_validation_report.md 与 ontology_validation_result.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rism002.reports import render  # noqa: E402
from rism002.utils import core  # noqa: E402
from rism002.validators import ontology  # noqa: E402


def build_report(result: dict[str, Any]) -> list[tuple[str, str]]:
    s = result["statistics"]
    sections: list[tuple[str, str]] = []
    sections.append(("1. 校验概览", render.kv_table({
        "校验结论": "通过" if result["passed"] else "未通过",
        "错误数": result["error_count"],
        "警告数": result["warning_count"],
        "方向总数": s.get("direction_count"),
        "已批准方向数": s.get("approved_direction_count"),
        "岗位能力数": s.get("competency_count"),
        "岗位族数": s.get("position_family_count"),
    })))

    checks = [
        ("direction_id 唯一 / 格式", "通过" if not any("direction_id" in e for e in result["errors"]) else "失败"),
        ("parent_dimensions ⊆ 15 个一级维度", "通过" if not any("一级维度" in e for e in result["errors"]) else "失败"),
        ("related_directions 引用存在", "通过" if not any("related_directions" in e for e in result["errors"]) else "失败"),
        ("depends_on 循环依赖", f"{s.get('dependency_cycles')} 个环"),
        ("status 合法", "通过" if not any("status" in e for e in result["errors"]) else "失败"),
        ("定义字段完整性", "通过" if not any("定义过短" in e or "缺少有效内容" in e for e in result["errors"]) else "失败"),
        ("approved 必须人工审核", "通过" if not any("approved" in e for e in result["errors"]) else "失败"),
        ("岗位能力方向引用", "通过" if not any("引用不存在的方向" in e for e in result["errors"]) else "失败"),
        ("本体版本一致", "通过" if not any("version" in e for e in result["errors"]) else "失败"),
    ]
    sections.append(("2. 校验项结果", render.md_table(["检查项", "结果"], checks)))

    sections.append(("3. 方向状态分布", render.md_table(
        ["状态", "数量"], [[k, v] for k, v in s.get("status_distribution", {}).items()])))
    sections.append(("4. 一级维度被引用分布（多对多）", render.md_table(
        ["一级维度", "关联方向数"], [[k, v] for k, v in s.get("parent_dimension_distribution", {}).items()])
        + f"\n\n关联多个一级维度的方向数：**{s.get('multi_parent_direction_count')}**；"
          f"单方向最多关联 **{s.get('max_parent_dimensions')}** 个一级维度。"))
    sections.append(("5. 关联与依赖统计", render.kv_table({
        "方向间语义关联边": s.get("related_direction_links"),
        "依赖边": s.get("dependency_edges"),
        "依赖环": s.get("dependency_cycles"),
        "能力→方向关联边": s.get("competency_direction_links"),
        "已绑定岗位族的方向数": s.get("directions_with_position_families"),
    })))
    sections.append(("6. 错误明细", render.bullet_list(result["errors"], limit=50)))
    sections.append(("7. 警告明细", render.bullet_list(result["warnings"], limit=50)))
    sections.append(("8. 审核状态说明",
                     "初始目录全部为 `candidate` 且 `annotation_status=pending`、"
                     "`annotation_source=historical_question`。校验器强制要求 `approved` 方向必须带 "
                     "`human` 来源与 `reviewed=true`；candidate 方向不得携带 approved 审核状态。"
                     "方向 ID 稳定唯一，语义相似但考察目标不同的方向不合并。"))
    sections.append(("9. 数据安全声明",
                     "报告仅输出 ID、计数与枚举分布，未输出任何简历正文或个人信息；校验过程只读。"))
    return sections


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RISM-002 方向目录校验")
    ap.add_argument("--config", help="主配置路径")
    ap.add_argument("--strict", action="store_true", help="有警告也返回非零退出码")
    args = ap.parse_args(argv)
    try:
        cfg = core.load_config(args.config)
        core.ensure_dirs(cfg)
        result = ontology.validate(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"[RISM-002] 本体校验异常: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    outdir = core.resolve(cfg["paths"]["output_dir"], cfg)
    outdir.mkdir(parents=True, exist_ok=True)
    core.write_json(outdir / "ontology_validation_result.json", result)
    render.write_report(outdir / "05_ontology_validation_report.md",
                        "RISM-002 方向目录校验报告", build_report(result),
                        meta={"阶段": "五", "只读": "是"})
    print(f"[RISM-002] 本体校验: {'通过' if result['passed'] else '未通过'} | "
          f"错误 {result['error_count']} | 警告 {result['warning_count']} | "
          f"方向 {result['statistics'].get('direction_count')} | "
          f"能力 {result['statistics'].get('competency_count')}")
    if result["error_count"]:
        return 1
    if args.strict and result["warning_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
