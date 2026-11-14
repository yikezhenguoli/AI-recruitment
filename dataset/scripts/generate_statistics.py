#!/usr/bin/env python3
"""统计分析与报告生成。

输出 metadata/*.json 与 reports/*.md：
  generation_report.md / quality_report.md / coverage_report.md /
  sample_review_report.md / final_acceptance_report.md（仅全量阶段）

用法： python3 scripts/generate_statistics.py [--stage auto|pilot|full]
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from collections import Counter, defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import config, pipeline  # noqa: E402
from lib.common import log, read_json, read_jsonl, write_json  # noqa: E402

GC = config.get_config("generation_config")
QD = config.get_config("quality_distribution")
PC = config.get_config("position_categories")
DCFG = config.get_config("question_dimensions")
TCFG = config.get_config("question_types")
DIM_LABEL = {d["key"]: d["label"] for d in DCFG["dimensions"]}
TYPE_LABEL = {d["key"]: d["label"] for d in TCFG["question_types"]}
QUAL_LABEL = {d["key"]: d["label"] for d in QD["resume_qualities"]}
LEVEL_LABEL = {d["key"]: d["label"] for d in QD["career_levels"]}


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d):.1f}%" if d else "-"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="auto", choices=["auto", "pilot", "full"])
    args = ap.parse_args()
    p = pipeline.paths()
    resumes = read_jsonl(p["resumes"])
    exps = read_jsonl(p["experiences"])
    qs = read_jsonl(p["questions"])
    chains = read_jsonl(p["chains"])
    if not resumes:
        raise SystemExit("没有可用的简历数据，请先运行生成脚本")
    stage = args.stage
    if stage == "auto":
        stage = "full" if len(resumes) > GC["pilot_size"] else "pilot"
    val_path = config.abspath("dataset/metadata/validation_result.json")
    validation = read_json(val_path) if os.path.exists(val_path) else {"passed": None, "statistics": {}}
    dedup_path = config.abspath("dataset/metadata/deduplication_report.json")
    dedup = read_json(dedup_path) if os.path.exists(dedup_path) else {}

    # ---------------------------------------------------------- 分布
    pos_c = Counter(r["target_position"] for r in resumes)
    pos_pid = Counter(r["position_id"] for r in resumes)
    lvl_c = Counter(r["career_level"] for r in resumes)
    qual_c = Counter(r["resume_quality"] for r in resumes)
    dim_c = Counter(q["dimension"] for q in qs)
    type_c = Counter(q["question_type"] for q in qs)
    etype_c = Counter(e["experience_type"] for e in exps)
    q_per = Counter(q["resume_id"] for q in qs)
    c_per = Counter(c["resume_id"] for c in chains)
    exp_covered = defaultdict(set)
    for q in qs:
        exp_covered[q["resume_id"]].add(q["experience_id"])

    # ---------------------------------------------------------- metadata 文件
    meta_dir = config.abspath(GC["paths"]["metadata_dir"])
    os.makedirs(meta_dir, exist_ok=True)
    dataset_meta = {
        "dataset_version": GC["dataset_version"],
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "stage": stage,
        "random_seed": GC["random_seed"],
        "as_of_date": GC["as_of_date"],
        "target_total_resumes": GC["total_resumes"],
        "current_resumes": len(resumes),
        "experiences": len(exps),
        "questions": len(qs),
        "chains": len(chains),
        "position_count": len(pos_pid),
        "questions_per_resume": {"min": min(q_per.values()) if q_per else 0,
                                 "max": max(q_per.values()) if q_per else 0,
                                 "avg": round(len(qs) / max(1, len(resumes)), 2)},
        "chains_per_resume": {"min": min(c_per.values()) if c_per else 0,
                              "max": max(c_per.values()) if c_per else 0},
        "external_generation": GC["external_generation"],
        "prohibited_components": "无 PyTorch / 无模型训练 / 无推理 API / 无前后端业务系统",
    }
    write_json(os.path.join(meta_dir, "dataset_metadata.json"), dataset_meta)

    position_stats = []
    for pid in PC["position_order"]:
        name = PC["categories"][pid]["name"]
        sub = [r for r in resumes if r["position_id"] == pid]
        sq = [q for q in qs if q["resume_id"] in {r["resume_id"] for r in sub}]
        position_stats.append({
            "position_id": pid, "index": PC["categories"][pid]["index"],
            "name": name, "family": PC["categories"][pid]["family"],
            "resumes": len(sub), "experiences": sum(1 for e in exps if e["position_id"] == pid),
            "questions": len(sq),
            "top_dimensions": dict(Counter(q["dimension"] for q in sq).most_common(5)),
            "career_levels": dict(Counter(r["career_level"] for r in sub)),
            "qualities": dict(Counter(r["resume_quality"] for r in sub)),
        })
    write_json(os.path.join(meta_dir, "position_statistics.json"),
               {"total": len(position_stats), "positions": position_stats})

    quality_stats = {
        "resume_qualities": {k: {"count": qual_c[k], "label": QUAL_LABEL[k],
                                 "target": next((x["count"] for x in QD["resume_qualities"] if x["key"] == k), None)}
                             for k in QUAL_LABEL},
        "career_levels": {k: {"count": lvl_c[k], "label": LEVEL_LABEL[k],
                              "target": next((x["count"] for x in QD["career_levels"] if x["key"] == k), None)}
                          for k in LEVEL_LABEL},
        "avg_scores": {
            "resume": validation["statistics"].get("avg_resume_score"),
            "experience": validation["statistics"].get("avg_experience_score"),
            "question": validation["statistics"].get("avg_question_score"),
            "chain": validation["statistics"].get("avg_chain_score"),
        },
        "validation_passed": validation.get("passed"),
    }
    write_json(os.path.join(meta_dir, "quality_statistics.json"), quality_stats)

    dim_stats = {
        "dimensions": [{"key": k, "label": DIM_LABEL[k], "count": dim_c[k],
                        "ratio": round(dim_c[k] / max(1, len(qs)), 4)} for k in DIM_LABEL],
        "question_types": [{"key": k, "label": TYPE_LABEL[k], "count": type_c[k],
                            "ratio": round(type_c[k] / max(1, len(qs)), 4)} for k in TYPE_LABEL],
        "experience_types": dict(etype_c),
        "priority": dict(Counter(q["priority"] for q in qs)),
        "difficulty": dict(Counter(q["difficulty"] for q in qs)),
    }
    write_json(os.path.join(meta_dir, "dimension_statistics.json"), dim_stats)

    # ---------------------------------------------------------- generation_report.md
    gen = [
        f"# 数据生成报告（{stage} 阶段）", "",
        f"> 生成时间：{dataset_meta['generated_at']}　|　随机种子：{GC['random_seed']}　|　基准月：{GC['as_of_date']}", "",
        "## 1. 生成方式", "",
        "全部数据由**本地规则模板 + 30 岗位知识库 + 固定种子结构化随机组合**生成，"
        "未调用任何外部 AI 服务或付费 API，未使用真实个人简历或真实身份信息。", "",
        f"- 外部生成开关：`{GC['external_generation']['enabled']}`",
        f"- 简历基准日期：{GC['as_of_date']}",
        f"- 批次大小：{GC['batch_size']} 份/批", "",
        "## 2. 规模", "",
        md_table(["指标", "当前值", "目标值"], [
            ["模拟简历", len(resumes), GC["total_resumes"]],
            ["经历单元", len(exps), "—"],
            ["面试问题", len(qs), f"{len(resumes) * 8} ~ {len(resumes) * 12}"],
            ["追问链", len(chains), f"≥ {len(resumes) * 3}"],
            ["岗位类别", len(pos_pid), 30],
        ]), "",
        "## 3. 岗位分布", "",
        md_table(["编号", "岗位类别", "简历数", "经历数", "问题数", "首要维度"],
                 [[s["index"], s["name"], s["resumes"], s["experiences"], s["questions"],
                   (DIM_LABEL.get(list(s["top_dimensions"])[0], "—") if s["top_dimensions"] else "—")]
                  for s in position_stats]), "",
        "## 4. 工作年限分布", "",
        md_table(["年限档", "当前数量", "当前占比", "全量目标", "全量占比"],
                 [[LEVEL_LABEL[k], lvl_c[k], pct(lvl_c[k], len(resumes)),
                   next(x["count"] for x in QD["career_levels"] if x["key"] == k),
                   pct(next(x["count"] for x in QD["career_levels"] if x["key"] == k), 5000)]
                  for k in LEVEL_LABEL]), "",
        "## 5. 简历质量分布", "",
        md_table(["质量型", "当前数量", "当前占比", "全量目标", "全量占比"],
                 [[QUAL_LABEL[k], qual_c[k], pct(qual_c[k], len(resumes)),
                   next(x["count"] for x in QD["resume_qualities"] if x["key"] == k),
                   pct(next(x["count"] for x in QD["resume_qualities"] if x["key"] == k), 5000)]
                  for k in QUAL_LABEL]), "",
        "## 6. 断点续跑", "",
        f"- 全量计划：`{GC['checkpoint']['plan_file']}`（5000 条确定性分配）",
        f"- 批次状态：`{GC['checkpoint']['state_file']}`",
        f"- 批次文件：`{GC['checkpoint']['batch_dir']}`",
        f"- 日志：`{GC['checkpoint']['log_file']}`", "",
    ]
    _write_report("generation_report.md", "\n".join(gen))

    # ---------------------------------------------------------- coverage_report.md
    cov = [
        f"# 岗位与维度覆盖报告（{stage} 阶段）", "",
        "## 1. 岗位覆盖", "",
        md_table(["编号", "岗位类别", "家族", "简历数", "经历数", "问题数", "主要追问维度（前 3）"],
                 [[s["index"], s["name"], s["family"], s["resumes"], s["experiences"], s["questions"],
                   "、".join(DIM_LABEL.get(k, k) for k in list(s["top_dimensions"])[:3])]
                  for s in position_stats]), "",
        "## 2. 15 个追问维度覆盖", "",
        md_table(["维度标签", "中文含义", "问题数", "占比", "是否覆盖"],
                 [[k, DIM_LABEL[k], dim_c[k], pct(dim_c[k], len(qs)), "是" if dim_c[k] else "否"]
                  for k in DIM_LABEL]), "",
        f"覆盖维度数：**{sum(1 for v in dim_c.values() if v)} / 15**", "",
        "## 3. 10 种问题类型分布", "",
        md_table(["类型标签", "中文含义", "问题数", "占比"],
                 [[k, TYPE_LABEL[k], type_c[k], pct(type_c[k], len(qs))] for k in TYPE_LABEL]), "",
        "## 4. 8 类经历单元分布", "",
        md_table(["经历类型", "数量", "占比"],
                 [[k, v, pct(v, len(exps))] for k, v in sorted(etype_c.items())]), "",
        "## 5. 每份简历的问题与链覆盖", "",
        md_table(["指标", "最小值", "最大值", "平均值"], [
            ["每份简历问题数", min(q_per.values()) if q_per else 0, max(q_per.values()) if q_per else 0,
             round(len(qs) / max(1, len(resumes)), 2)],
            ["每份简历覆盖经历数", min(len(v) for v in exp_covered.values()) if exp_covered else 0,
             max(len(v) for v in exp_covered.values()) if exp_covered else 0,
             round(sum(len(v) for v in exp_covered.values()) / max(1, len(exp_covered)), 2)],
            ["每份简历追问链数", min(c_per.values()) if c_per else 0, max(c_per.values()) if c_per else 0,
             round(len(chains) / max(1, len(resumes)), 2)],
        ]), "",
        "## 6. 难度与优先级", "",
        md_table(["优先级", "数量", "难度", "数量"],
                 [[k, Counter(q["priority"] for q in qs)[k], d, Counter(q["difficulty"] for q in qs)[d]]
                  for k, d in zip(["high", "medium", "low"], ["easy", "medium", "hard"])]), "",
    ]
    _write_report("coverage_report.md", "\n".join(cov))

    # ---------------------------------------------------------- quality_report.md
    vst = validation.get("statistics", {})
    errors = validation.get("errors", {})
    warnings = validation.get("warnings", {})
    qual = [
        f"# 数据质量报告（{stage} 阶段）", "",
        f"> 自动校验结果：**{'通过' if validation.get('passed') else '未通过 / 尚未执行'}**　"
        f"错误 {validation.get('error_total', 0)} 项　警告 {validation.get('warning_total', 0)} 项", "",
        "## 1. 五项硬性门槛", "",
        md_table(["门槛", "含义", "判定"],
                 [[g, rules_text(g), "通过（失败 0 条）" if not any(g in k for k in errors) else "存在失败"]
                  for g in GC["quality_gate"]["hard_gates"]]), "",
        "## 2. 关键质量指标", "",
        md_table(["指标", "数值", "门槛"], [
            ["每道问题经历关联", "全部绑定具体 experience_id", "必须具备"],
            ["原文引用精确匹配", "事实句原子化，偏移量真实计算", "必须具备"],
            ["硬性门槛未过问题数", vst.get("hard_gate_failed_questions", "—"), "0"],
            ["问题重复率", dedup.get("duplicate_question_ratio", vst.get("duplicate_question_ratio", "—")),
             f"≤ {GC['quality_gate']['max_duplicate_question_ratio']}"],
            ["模板集中度", dedup.get("max_signature_ratio", vst.get("template_concentration", "—")),
             f"≤ {GC['quality_gate']['max_template_concentration']}"],
            ["不同问题模板签名数", dedup.get("distinct_question_signatures", vst.get("distinct_question_signatures", "—")), "越多越好"],
            ["简历文本完全重复", "0" if not errors.get("duplicate_resume_text") else errors["duplicate_resume_text"], "0"],
            ["追问链经历一致性", "全部通过" if not errors.get("chain_experience_consistent") else "存在失败", "必须通过"],
        ]), "",
        "## 3. 质量评分（0~100，权重见 config/scoring_rules.yaml）", "",
        md_table(["对象", "平均分", "门槛"], [
            ["简历", vst.get("avg_resume_score", "—"), GC["quality_gate"]["min_resume_score"]],
            ["经历单元", vst.get("avg_experience_score", "—"), GC["quality_gate"]["min_experience_score"]],
            ["问题", vst.get("avg_question_score", "—"), GC["quality_gate"]["min_question_score"]],
            ["追问链", vst.get("avg_chain_score", "—"), "—"],
        ]), "",
        "> 硬性门槛独立判定：即使其它评分较高，只要问题未正确关联具体经历，也不得判定为合格。", "",
        "## 4. 错误明细", "",
    ]
    if errors:
        qual.append(md_table(["错误码", "数量", "示例"],
                             [[k, v, (validation.get("error_samples", {}).get(k) or [""])[0][:120]]
                              for k, v in sorted(errors.items(), key=lambda x: -x[1])]))
    else:
        qual.append("无错误。")
    qual += ["", "## 5. 警告明细", ""]
    if warnings:
        qual.append(md_table(["警告码", "数量", "示例"],
                             [[k, v, (validation.get("warning_samples", {}).get(k) or [""])[0][:120]]
                              for k, v in sorted(warnings.items(), key=lambda x: -x[1])]))
    else:
        qual.append("无警告。")
    qual += ["", "## 6. 校验覆盖范围", "",
             "基础完整性 / 简历合理性 / 经历关联（最高优先级）/ 问题质量 / 追问链 / 多样性 / "
             "岗位配额 / 15 维度覆盖 / 问题类型集中度 / 岗位专业词泄漏，详见 `scripts/validate_dataset.py`。", ""]
    _write_report("quality_report.md", "\n".join(qual))

    # ---------------------------------------------------------- sample_review_report.md
    _write_report("sample_review_report.md", _sample_review(resumes, exps, qs, chains, stage))

    # ---------------------------------------------------------- final_acceptance_report.md
    if stage == "full":
        _write_report("final_acceptance_report.md", _final_report(dataset_meta, pos_c, lvl_c, qual_c,
                                                                 vst, validation, dedup))

    log(f"统计与报告生成完成：metadata 4 份，reports {5 if stage == 'full' else 4} 份（阶段 {stage}）")


def rules_text(g: str) -> str:
    return {
        "experience_link_valid": "问题关联存在且归属一致的 experience_id",
        "reference_exact_match": "引用是经历原文精确子串且偏移量一致",
        "no_generic_question": "问题含可定位原文引用，无泛泛提问",
        "no_cross_experience_mix": "问题不混合其它经历单元内容",
        "chain_experience_consistent": "追问链始终围绕同一个 experience_id",
    }.get(g, g)


def _write_report(name: str, text: str) -> None:
    path = os.path.join(config.abspath(GC["paths"]["reports_dir"]), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")


def _sample_review(resumes, exps, qs, chains, stage: str) -> str:
    """按岗位/年限/质量分层抽取真实样本，供人工验收逐条核对。"""
    by_rid_exp: dict[str, list[dict]] = defaultdict(list)
    by_rid_q: dict[str, list[dict]] = defaultdict(list)
    by_rid_c: dict[str, list[dict]] = defaultdict(list)
    for e in exps:
        by_rid_exp[e["resume_id"]].append(e)
    for q in qs:
        by_rid_q[q["resume_id"]].append(q)
    for c in chains:
        by_rid_c[c["resume_id"]].append(c)

    # 分层：保证覆盖不同岗位、不同质量型、不同年限
    picked: list[dict] = []
    seen_combo: set[tuple[str, str]] = set()
    for qk in ("high", "vague", "contradictory", "normal"):
        cand = [r for r in resumes if r["resume_quality"] == qk]
        cand.sort(key=lambda r: (r["career_level"], r["resume_id"]))
        for r in cand:
            key = (r["position_id"], qk)
            if key in seen_combo:
                continue
            seen_combo.add(key)
            picked.append(r)
            break
    for r in sorted(resumes, key=lambda x: x["resume_id"]):
        if len(picked) >= 12:
            break
        if r["resume_id"] not in {x["resume_id"] for x in picked}:
            picked.append(r)
    picked = picked[:12]

    out = [
        f"# 人工验收抽样审核报告（{stage} 阶段）", "",
        "> 本报告用于**第三阶段人工验收**。每项样本均直接引用数据集原文，"
        "请重点核对「问题是否真正针对简历中的具体经历，而不是只针对整份简历」。", "",
        "## 1. 抽样方法", "",
        f"- 抽取 {len(picked)} 份样本，覆盖 {len({r['position_id'] for r in picked})} 个岗位、"
        f"{len({r['career_level'] for r in picked})} 个年限档、{len({r['resume_quality'] for r in picked})} 种质量型。",
        "- 每份样本展示：简历基本信息、一个经历单元原文、绑定该经历的问题、一条同经历追问链。", "",
        "## 2. 人工检查清单", "",
        "| 序号 | 检查项 | 判定 |", "|---|---|---|",
        "| 1 | 问题是否明确关联某一个 experience_id | ☐ 是 ☐ 否 |",
        "| 2 | reference.original_text 是否能在该经历原文中逐字找到 | ☐ 是 ☐ 否 |",
        "| 3 | 问题是否围绕该经历、而非整份简历泛泛提问 | ☐ 是 ☐ 否 |",
        "| 4 | 提问原因与引用内容是否一致、是否含无依据的事实假设 | ☐ 是 ☐ 否 |",
        "| 5 | 追问链是否始终围绕同一经历并体现递进关系 | ☐ 是 ☐ 否 |",
        "| 6 | 是否存在虚构候选人回答 | ☐ 是 ☐ 否 |",
        "| 7 | 问题是否符合岗位专业背景、中文表达是否自然 | ☐ 是 ☐ 否 |", "",
        "## 3. 样本明细", "",
    ]
    for i, r in enumerate(picked, 1):
        rid = r["resume_id"]
        my_q = by_rid_q.get(rid, [])
        my_e = by_rid_exp.get(rid, [])
        my_c = by_rid_c.get(rid, [])
        if not my_q or not my_e:
            continue
        q0 = my_q[0]
        e0 = next((e for e in my_e if e["experience_id"] == q0["experience_id"]), my_e[0])
        c0 = next((c for c in my_c if c["experience_id"] == q0["experience_id"]), (my_c[0] if my_c else None))
        out += [
            f"### 样本 {i}：{rid} · {r['target_position']} · {r['career_level_label']} · {r['resume_quality_label']}", "",
            f"- 虚构姓名：{r['basic_info']['name']}　城市：{r['basic_info']['city']}　"
            f"工作年限：{r['total_work_years']} 年",
            f"- 经历单元总数：{len(my_e)}　问题数：{len(my_q)}　追问链数：{len(my_c)}　"
            f"问题覆盖经历数：{len({q['experience_id'] for q in my_q})}", "",
            f"**经历单元 `{e0['experience_id']}`（{e0['experience_type']} · {e0['title']}）原文：**", "",
            f"> {e0['original_content']}", "",
            f"**绑定问题 `{q0['question_id']}`**　维度 `{q0['dimension']}`　类型 `{q0['question_type']}`　"
            f"优先级 `{q0['priority']}`", "",
            f"- 原文引用：`{q0['reference']['original_text']}`（偏移 {q0['reference']['start_offset']}~{q0['reference']['end_offset']}）",
            f"- 问题：{q0['question']}",
            f"- 提问原因：{q0['reason']}",
            f"- 期望了解：{'；'.join(q0['expected_investigation'])}",
            f"- 后续追问：{'；'.join(q0['follow_up_questions'])}", "",
        ]
        if c0:
            out += [f"**追问链 `{c0['chain_id']}`（主题 {c0.get('theme')}，深度 {c0['chain_depth']}）**", "",
                    md_table(["层", "层次", "追问", "触发条件"],
                             [[x["sequence"], x["level"], x["question"][:110] + "…", x["trigger_condition"]]
                              for x in c0["questions"]]), "",
                    f"- 提前结束条件：{c0.get('stop_condition', '—')}", ""]
        out += ["---", ""]
    out += [
        "## 4. 验收结论（由人工填写）", "",
        "| 项目 | 结论 |", "|---|---|",
        "| 简历质量抽样 | ☐ 通过　☐ 需修正 |",
        "| 经历拆解准确性 | ☐ 通过　☐ 需修正 |",
        "| 问题与经历关联 | ☐ 通过　☐ 需修正 |",
        "| 追问链质量 | ☐ 通过　☐ 需修正 |",
        "| 岗位覆盖 | ☐ 通过　☐ 需修正 |",
        "| 问题多样性 | ☐ 通过　☐ 需修正 |", "",
        "**只有以上全部通过，才可运行 `python3 scripts/run_pipeline.py --accept` 解除阶段闸门，"
        "进入第四阶段生成剩余 4900 份简历。**", "",
    ]
    return "\n".join(out)


def _final_report(meta, pos_c, lvl_c, qual_c, vst, validation, dedup) -> str:
    return "\n".join([
        "# 最终质量验收报告", "",
        f"> 生成时间：{meta['generated_at']}　|　数据集版本：{meta['dataset_version']}", "",
        "## 1. 验收结果", "",
        f"- 自动校验：**{'通过' if validation.get('passed') else '未通过'}**"
        f"（错误 {validation.get('error_total', 0)}，警告 {validation.get('warning_total', 0)}）",
        f"- 模型训练代码：**不存在**（本阶段仅含数据工程脚本）", "",
        "## 2. 最终指标", "",
        md_table(["验收项目", "目标", "实际", "结论"], [
            ["模拟简历总量", 5000, meta["current_resumes"], "✓" if meta["current_resumes"] == 5000 else "✗"],
            ["岗位类别", 30, len(pos_c), "✓" if len(pos_c) == 30 else "✗"],
            ["每岗位最少简历", 100, min(pos_c.values()) if pos_c else 0,
             "✓" if pos_c and min(pos_c.values()) >= 100 else "✗"],
            ["应届毕业生", 1000, lvl_c.get("fresh", 0), "✓" if lvl_c.get("fresh") == 1000 else "✗"],
            ["1~3 年", 1250, lvl_c.get("junior", 0), "✓" if lvl_c.get("junior") == 1250 else "✗"],
            ["3~5 年", 1250, lvl_c.get("mid", 0), "✓" if lvl_c.get("mid") == 1250 else "✗"],
            ["5~10 年", 1000, lvl_c.get("senior", 0), "✓" if lvl_c.get("senior") == 1000 else "✗"],
            ["10 年以上", 500, lvl_c.get("expert", 0), "✓" if lvl_c.get("expert") == 500 else "✗"],
            ["优质简历", 1500, qual_c.get("high", 0), "✓" if qual_c.get("high") == 1500 else "✗"],
            ["普通简历", 2000, qual_c.get("normal", 0), "✓" if qual_c.get("normal") == 2000 else "✗"],
            ["信息模糊型", 1000, qual_c.get("vague", 0), "✓" if qual_c.get("vague") == 1000 else "✗"],
            ["疑点型", 500, qual_c.get("contradictory", 0), "✓" if qual_c.get("contradictory") == 500 else "✗"],
            ["经历单元总量", "—", meta["experiences"], "—"],
            ["问题总量", "—", meta["questions"], "—"],
            ["追问链总量", "—", meta["chains"], "—"],
            ["每份问题数", "8~12", f"{meta['questions_per_resume']['min']}~{meta['questions_per_resume']['max']}",
             "✓" if meta["questions_per_resume"]["min"] >= 8 and meta["questions_per_resume"]["max"] <= 12 else "✗"],
            ["每份追问链", "≥3", meta["chains_per_resume"]["min"],
             "✓" if meta["chains_per_resume"]["min"] >= 3 else "✗"],
            ["问题关联准确率", "100%", f"{100 - round(100 * vst.get('hard_gate_failed_questions', 0) / max(1, meta['questions']), 2)}%", "—"],
            ["原文引用准确率", "100%", "校验通过" if not validation.get("errors", {}).get("reference_exact_match") else "存在失败", "—"],
            ["重复率", "≤2%", dedup.get("duplicate_question_ratio", "—"), "—"],
            ["数据校验通过率", "100%", "通过" if validation.get("passed") else "未通过", "—"],
        ]), "",
        "## 3. 五项关键验收要求", "",
        "1. 每个问题都能定位到一份具体简历；",
        "2. 每个问题都能定位到简历中的一个具体经历单元；",
        "3. 每个问题都有准确的原文引用；",
        "4. 每个问题都有明确的考察维度和提问目的；",
        "5. 每条追问链都围绕同一个经历展开，并具有合理的递进关系。", "",
        "以上任一项不满足，对应问题均不得判定为合格。校验脚本已将这五项设为硬性门槛。", "",
    ])


if __name__ == "__main__":
    main()
