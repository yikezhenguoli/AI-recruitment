#!/usr/bin/env python3
"""阶段四：历史追问意图分析（基础模式，默认不调用外部 LLM）。

用法：
    python3 scripts/rism002/analyze_question_intents.py
    python3 scripts/rism002/analyze_question_intents.py --strict

外部 LLM：默认关闭。若配置启用，脚本会先打印将发送的数据字段与目标服务，
并拒绝执行直到显式传入 --enable-llm --confirm-external；本次任务不启用。

输出：
    data/intermediate/question_intent_analysis.json
    data/intermediate/candidate_directions.jsonl   （全部 candidate / pending）
    outputs/rism002/04_intent_analysis_report.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rism002.analyzers import intent  # noqa: E402
from rism002.reports import render  # noqa: E402
from rism002.utils import core  # noqa: E402


def build_report(result: dict[str, Any]) -> list[tuple[str, str]]:
    s = result["summary"]
    sections: list[tuple[str, str]] = []

    sections.append(("1. 分析概览", render.kv_table({
        "分析模式": result["mode"],
        "历史问题数": s["questions_analyzed"],
        "追问链数": s["chains_analyzed"],
        "不同意图签名数": s["distinct_intent_signatures"],
        "问题类型 × 一级维度组合数": s["distinct_question_type_dimension_combinations"],
        "语义相似问题对（总数）": s["similar_question_pairs_total"],
        "相似问题但维度不同": s["cross_dimension_similar_pairs"],
        "同一原文对应多种意图": s["quotes_with_multiple_intents"],
        "一级维度语义过宽数": s["broad_primary_dimensions"],
        "生成的候选二级方向": s["candidate_directions_generated"],
        "自动批准的方向数": s["candidate_directions_auto_approved"],
        "回收的 secondary_dimensions 问题数": s["secondary_dimensions_recovered"],
    })))

    llm = result["llm"]
    sections.append(("2. 外部 LLM 调用状态", render.kv_table({
        "是否调用": "否" if not llm["used"] else "是",
        "原因 / 说明": llm["reason"],
        "将发送字段": llm["fields_to_send"] or "（无，未启用）",
        "目标服务": llm["endpoint"] or "（无，未启用）",
    }) + "\n\n> 本次分析完全由本地规则完成，未向任何第三方服务发送数据。"))

    sig_rows = [[i + 1, x["question_type"], x["dimension"], x["count"],
                 "、".join(x["goals"][:3])]
                for i, x in enumerate(result["intent_signatures"][:25])]
    sections.append(("3. 核心考察意图签名（Top 25）", render.md_table(
        ["#", "问题类型", "主维度", "问题数", "主要考察点"], sig_rows)))

    sim_rows = [[p["question_id_1"], p["question_id_2"], p["similarity"],
                 "是" if p["same_dimension"] else "否"]
                for p in result["similar_question_pairs"][:20]]
    cross_rows = [[p["quote_fingerprint"], p["experience_id"], p["question_id_1"],
                   p["dimension_1"], p["question_id_2"], p["dimension_2"],
                   p["skeleton_similarity"]]
                  for p in result["cross_intent_similar_pairs"][:15]]
    sections.append(("4. 语义重复但表达不同的问题（样例）", render.md_table(
        ["问题 A", "问题 B", "相似度", "同维度"], sim_rows)
        + f"\n\n引用同一段经历原文但考察目标不同的问题对共 "
          f"{s['cross_dimension_similar_pairs']} 对，样例如下：\n\n"
        + render.md_table(["原文指纹", "经历 ID", "问题 A", "维度 A", "问题 B", "维度 B", "骨架相似度"],
                          cross_rows)))

    diff_rows = [[x["quote_fingerprint"], x["question_count"], x["distinct_intents"],
                  "、".join(x["intents"][:4])]
                 for x in result["same_text_different_intent"][:20]]
    sections.append(("5. 文本相似但考察目标不同", render.md_table(
        ["原文指纹", "问题数", "意图数", "意图组合（维度/问题类型）"], diff_rows)
        + "\n\n> 原文以 SHA-256 前 12 位指纹代替，报告不输出简历原文内容。"))

    broad_rows = [[b["dimension"], b["dimension_name"], b["distinct_question_types"],
                   "、".join(f"{k}:{v}" for k, v in list(b["question_type_counts"].items())[:6])]
                  for b in result["broad_dimensions"]]
    sections.append(("6. 现有 15 个一级维度无法准确表达的意图", render.md_table(
        ["一级维度", "中文名", "不同考察目标数", "问题类型分布"], broad_rows)))

    cand_rows = [[c["direction_id"], c["direction_name"], len(c["parent_dimensions"]),
                  c["origin"]["question_count"], c["status"], c["review"]["annotation_status"]]
                 for c in result["candidate_directions"]]
    sections.append(("7. 候选二级追问方向", render.md_table(
        ["direction_id", "名称", "关联一级维度数", "支撑问题数", "方向状态", "审核状态"], cand_rows)))

    ca = result["chain_analysis"]
    sections.append(("8. 追问链递进关系分析", render.kv_table({
        "追问链总数": ca["chain_count"],
        "不同触发条件数": ca["distinct_trigger_conditions"],
        "不同追问目的数": ca["distinct_purposes"],
        "层级分布": "、".join(f"{k}:{v}" for k, v in ca["level_distribution"].items()),
    }) + "\n\n" + render.md_table(["递进序列", "链数"],
                                  [[x["sequence"], x["count"]] for x in ca["top_level_sequences"]])
        + "\n\n难度映射（供 Strategy.difficulty 使用）：\n\n"
        + render.md_table(["追问层级", "难度"], [[k, v] for k, v in ca["difficulty_mapping"].items()])))

    sections.append(("9. 候选结果使用限制（硬性）",
                     "- 所有候选方向 `status = candidate`、`annotation_status = pending`、"
                     "`annotation_source = historical_question`，**未自动批准任何方向**。\n"
                     "- 历史问题中出现某方向仅可作为 Positive **候选**；某段经历未出现某方向"
                     "**不得**据此判定为 Negative。\n"
                     "- 未审核的候选结果不得进入 `data/processed/rism002_samples.jsonl`。\n"
                     "- 方向 ID 稳定唯一，不因中文名称调整而变更；语义相似但考察目标不同的方向不自动合并。"))
    sections.append(("10. 数据安全声明",
                     "报告仅输出问题 ID、计数、枚举与脱敏指纹；未输出简历正文、姓名、电话、邮箱等个人信息。"
                     "全部输入以只读方式打开，未发生任何网络请求、模型训练或 Embedding 生成。"))
    return sections


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RISM-002 历史追问意图分析")
    ap.add_argument("--config", help="主配置路径")
    ap.add_argument("--strict", action="store_true", help="候选方向为空时返回非零")
    ap.add_argument("--enable-llm", action="store_true", help="请求启用外部 LLM（默认关闭）")
    ap.add_argument("--confirm-external", action="store_true",
                    help="显式确认外部数据发送；需与 --enable-llm 同时使用")
    args = ap.parse_args(argv)

    try:
        cfg = core.load_config(args.config)
        core.ensure_dirs(cfg)
        if args.confirm_external and not args.enable_llm:
            print("[RISM-002] --confirm-external 必须与 --enable-llm 同时使用", file=sys.stderr)
            return 2
        if cfg["llm"]["enabled"] and (args.enable_llm or args.confirm_external):
            llm = cfg["llm"]
            print("[RISM-002] 外部 LLM 请求被拦截。将发送数据字段："
                  f"{llm['fields_to_send']}；目标服务：{llm['provider']} / {llm['endpoint']}。"
                  "本任务不执行外部调用。", file=sys.stderr)
        result = intent.analyze(cfg, llm_requested=args.enable_llm,
                                llm_confirmed=args.confirm_external)
    except PermissionError as exc:
        print(f"[RISM-002] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[RISM-002] 分析执行异常: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    core.write_json(core.out_path("intent_analysis", cfg), result)
    n = core.write_jsonl(core.out_path("candidate_directions", cfg),
                         intent.candidate_direction_records(result))
    render.write_report(core.resolve(cfg["paths"]["output_dir"], cfg) / "04_intent_analysis_report.md",
                        "RISM-002 历史追问意图分析报告", build_report(result),
                        meta={"阶段": "四", "分析模式": result["mode"], "外部 LLM": "关闭"})

    s = result["summary"]
    print(f"[RISM-002] 意图分析完成 | 问题 {s['questions_analyzed']} | 追问链 {s['chains_analyzed']} | "
          f"意图签名 {s['distinct_intent_signatures']} | 相似对 {s['similar_question_pairs_total']} | "
          f"候选方向 {n}（全部 pending，未批准）| LLM 调用：否")
    if args.strict and not result["candidate_directions"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
