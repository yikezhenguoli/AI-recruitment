#!/usr/bin/env python3
"""阶段三：RISM-001 原始数据只读审计。

用法（可从任意目录运行）：
    python3 scripts/rism002/audit_source_data.py
    python3 scripts/rism002/audit_source_data.py --strict
    python3 scripts/rism002/audit_source_data.py --json-only

退出码：0 = 审计通过；1 = 发现错误；2 = 配置/运行异常。
本脚本只读，不修改任何 RISM-001 原始数据。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rism002.reports import render  # noqa: E402
from rism002.utils import core  # noqa: E402
from rism002.validators.source_audit import audit  # noqa: E402


def build_report(result: dict[str, Any]) -> list[tuple[str, str]]:
    s = result["statistics"]
    sections: list[tuple[str, str]] = []

    overview = {
        "审计结论": "通过" if result["passed"] else "未通过",
        "错误数": result["error_count"],
        "警告数": result["warning_count"],
        "本体版本": result["ontology_version"],
        "简历 / 经历 / 问题 / 追问链": f"{s.get('resumes_lines')} / {s.get('experiences_lines')} / {s.get('questions_lines')} / {s.get('chains_lines')}",
    }
    sections.append(("1. 审计概览", render.kv_table(overview)))

    rows = []
    for kind, d in result["file_descriptions"].items():
        rows.append([kind, d["line_count"], round(d["size_bytes"] / 1024, 1),
                     d["parse_error_count"], s.get(f"{kind}_unique_ids", "-")])
    sections.append(("2. JSONL 格式与 ID 唯一性",
                     render.md_table(["数据集", "有效行数", "KiB", "解析错误", "唯一 ID 数"], rows)))

    field_rows = []
    for kind in ("resumes", "experiences", "questions", "chains"):
        total = s.get(f"{kind}_lines", 0)
        for f, n in s.get(f"{kind}_fields", {}).items():
            field_rows.append([kind, f, n, total, "完整" if n == total else "缺失"])
    sections.append(("3. 必需字段覆盖", render.md_table(
        ["数据集", "字段", "出现次数", "总行数", "状态"], field_rows)))

    link_keys = [
        ("orphan_experiences", "经历引用无效简历"),
        ("question_bad_experience_ref", "问题引用无效经历"),
        ("question_bad_resume_ref", "问题简历归属不一致"),
        ("question_bad_experience_type", "问题经历类型不一致"),
        ("question_bad_quote", "原文引用非经历子串"),
        ("question_bad_offset", "引用字符偏移错误"),
        ("quote_offset_checked", "已校验引用条数"),
        ("chain_bad_experience_ref", "追问链引用无效经历"),
        ("chain_bad_root_question", "追问链根问题异常"),
        ("chain_bad_level", "追问层级非法"),
        ("chain_bad_sequence", "追问序号不连续"),
    ]
    sections.append(("4. 关联与原文引用校验", render.md_table(
        ["检查项", "数量"], [[label, s.get(k, "-")] for k, label in link_keys])))

    dist_titles = [
        ("experience_type_distribution", "5. 经历类型分布"),
        ("dimension_distribution", "6. 一级追问维度分布"),
        ("question_type_distribution", "7. 历史问题类型分布"),
        ("chain_depth_distribution", "8. 追问链深度分布"),
        ("chain_level_distribution", "9. 追问层级分布"),
        ("position_family_distribution", "10. 岗位族分布"),
    ]
    for key, title in dist_titles:
        sections.append((title, render.md_table(["取值", "数量"],
                                               [[k, v] for k, v in s.get(key, {}).items()])))

    extra = {
        "有历史问题的经历": s.get("experiences_with_questions"),
        "无历史问题的经历（不得据此判 Negative）": s.get("experiences_without_questions"),
        "RISM-001 embedding 样本数": s.get("rism001_sample_count"),
    }
    sections.append(("11. 历史数据覆盖", render.kv_table(extra)))

    ro = s.get("readonly_assets", {})
    sections.append(("12. 只读资产指纹", render.kv_table({
        "已比对文件数": ro.get("checked", 0),
        "发生变化": len(ro.get("changed", [])),
        "缺失": len(ro.get("missing", [])),
    })))

    emb_rows = []
    for name, info in s.get("embedding_assets", {}).items():
        if isinstance(info, dict) and "shape" in info:
            emb_rows.append([name, info.get("shape"), info.get("descr"), info.get("size_bytes")])
        else:
            emb_rows.append([name, "-", "-", "-"])
    sections.append(("13. Embedding 资产只读盘点", render.md_table(
        ["资产", "shape", "dtype", "bytes"], emb_rows)))

    sections.append(("14. 错误明细", render.bullet_list(result["errors"], limit=50)))
    sections.append(("15. 警告明细", render.bullet_list(result["warnings"], limit=50)))
    sections.append(("16. 数据安全声明",
                     "本报告仅输出 ID、计数与枚举分布；未输出简历正文、姓名、电话、邮箱等个人信息。"
                     "审计全程以只读方式打开源文件，未执行任何写入、训练或 Embedding 生成。"))
    return sections


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RISM-002 原始数据只读审计")
    ap.add_argument("--config", help="主配置路径（默认 configs/rism002.json）")
    ap.add_argument("--strict", action="store_true", help="有警告也返回非零退出码")
    ap.add_argument("--json-only", action="store_true", help="只写 JSON 结果，不写 Markdown 报告")
    args = ap.parse_args(argv)

    try:
        cfg = core.load_config(args.config)
        core.ensure_dirs(cfg)
        result = audit(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"[RISM-002] 审计执行异常: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    outdir = core.resolve(cfg["paths"]["output_dir"], cfg)
    outdir.mkdir(parents=True, exist_ok=True)
    core.write_json(outdir / "source_audit_result.json", result)
    if not args.json_only:
        render.write_report(outdir / "03_source_audit_report.md", "RISM-002 原始数据审计报告",
                            build_report(result), meta={"阶段": "三", "只读": "是"})

    print(f"[RISM-002] 源数据审计: {'通过' if result['passed'] else '未通过'} | "
          f"错误 {result['error_count']} | 警告 {result['warning_count']} | "
          f"简历 {result['statistics'].get('resumes_lines')} / 经历 {result['statistics'].get('experiences_lines')} / "
          f"问题 {result['statistics'].get('questions_lines')} / 追问链 {result['statistics'].get('chains_lines')}")
    if result["error_count"]:
        return 1
    if args.strict and result["warning_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
