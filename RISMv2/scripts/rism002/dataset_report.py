#!/usr/bin/env python3
"""阶段七：RISM-002 数据集全维度统计与质量报告。

统计范围（区分「已审核正式数据」与「候选/预览数据」，不混为一谈）：
    data/processed/rism002_samples.jsonl          正式样本
    data/annotations/*.jsonl                     人工审核记录
    data/intermediate/candidate_*.jsonl          规则派生候选（pending）
    data/ontology/*.json                         方向与岗位能力目录
    源数据 data/*.jsonl                           RISM-001 只读资产

报告只输出 ID、计数、枚举分布与状态，绝不输出姓名/电话/邮箱/身份证号或简历正文。

用法：
    python3 scripts/rism002/dataset_report.py
    python3 scripts/rism002/dataset_report.py --json-only

输出：
    outputs/rism002/dataset_report.md
    outputs/rism002/dataset_report.json
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rism002.parsers import jsonl as parser  # noqa: E402
from rism002.reports import render  # noqa: E402
from rism002.utils import core  # noqa: E402

ANNOTATION_FILES = [
    ("claims", "human_claims"),
    ("evidence_gaps", "human_gaps"),
    ("strategies", "human_strategies"),
    ("direction_annotations", "human_direction_annotations"),
]


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows, _ = core.read_jsonl(path, strict=False)
    return rows


def _counter_table(counter: Counter) -> list[list[Any]]:
    return [[k, v] for k, v in sorted(counter.items(), key=lambda x: (-x[1], str(x[0])))]


def _table_or_empty(headers: list[str], rows: list[list[Any]]) -> str:
    return render.md_table(headers, rows) if rows else \
        render.md_table(headers, [["（暂无记录）", "—"]] if len(headers) == 2
                        else [["（暂无记录）"] + ["—"] * (len(headers) - 1)])


_TRAIN_MODULES = {"torch", "tensorflow", "transformers", "sentence_transformers",
                  "sklearn", "pytorch_lightning"}


def _scan_training_code(cfg: dict[str, Any]) -> list[str]:
    """AST 级检测：真实 import 或训练调用才计入，注释/字符串中的字样不算。"""
    import ast
    hits: list[str] = []
    paths = list(Path(core.resolve("rism002", cfg)).rglob("*.py")) + \
            list(Path(core.resolve("scripts/rism002", cfg)).rglob("*.py"))
    for f in sorted(paths):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError as exc:  # pragma: no cover
            hits.append(f"{f.relative_to(core.root(cfg))}:语法错误 {exc}")
            continue
        rel = str(f.relative_to(core.root(cfg)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in _TRAIN_MODULES:
                        hits.append(f"{rel}:import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod in _TRAIN_MODULES:
                    hits.append(f"{rel}:from {node.module} import ...")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                owner = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
                if attr in ("backward", "step") or (attr == "train" and owner in ("model", "net")) \
                        or attr == "fit":
                    hits.append(f"{rel}:{owner + '.' if owner else ''}{attr}()")
    return hits


def collect(cfg: dict[str, Any]) -> dict[str, Any]:
    tax = core.load_taxonomy(cfg)
    idx = parser.load_source_index(cfg)
    resumes, experiences = idx["resumes"], idx["experiences"]
    questions, chains = idx["questions"], idx["chains"]

    # 岗位族映射
    pos_to_family: dict[str, str] = {}
    for fam in tax["position_families"]:
        for pid in fam["position_ids"]:
            pos_to_family[pid] = fam["id"]
    resume_by_id = idx["by_resume"]
    exp_family: dict[str, str] = {}
    for e in experiences:
        r = resume_by_id.get(e.get("resume_id"), {})
        exp_family[e.get("experience_id")] = pos_to_family.get(r.get("position_id"), "unknown")

    # 本体
    dpath = core.out_path("directions", cfg)
    directions = core.read_json(dpath)["directions"] if dpath.exists() else []
    cpath = core.out_path("competencies", cfg)
    comps = core.read_json(cpath)["competencies"] if cpath.exists() else []

    # 候选
    cand_claims = _rows(core.out_path("candidate_claims", cfg))
    cand_gaps = _rows(core.out_path("candidate_gaps", cfg))
    cand_strats = _rows(core.out_path("candidate_strategies", cfg))
    preview = _rows(core.resolve(cfg["paths"]["intermediate_dir"], cfg)
                    / "rism002_unknown_preview.jsonl")
    intent_path = core.out_path("intent_analysis", cfg)
    intent = core.read_json(intent_path) if intent_path.exists() else {}

    # 人工审核记录
    annotations: dict[str, list[dict[str, Any]]] = {
        name: _rows(core.out_path(key, cfg)) for name, key in ANNOTATION_FILES
    }
    review_status: Counter = Counter()
    review_source: Counter = Counter()
    for rows in annotations.values():
        for r in rows:
            rv = r.get("review", r)
            review_status[rv.get("annotation_status", "missing")] += 1
            review_source[rv.get("annotation_source", "missing")] += 1
    for d in directions:
        rv = d.get("review", {})
        review_status[f"direction:{rv.get('annotation_status', 'missing')}"] += 1

    # 正式样本
    samples = _rows(core.out_path("processed_samples", cfg))
    src_dist: Counter = Counter()
    label_dist: Counter = Counter()
    claim_types: Counter = Counter()
    gap_types: Counter = Counter()
    strategy_types: Counter = Counter()
    dir_dist: Counter = Counter()
    dim_dist: Counter = Counter()
    priority_dist: Counter = Counter()
    difficulty_dist: Counter = Counter()
    family_dir_dist: dict[str, Counter] = defaultdict(Counter)
    for s in samples:
        fam = (s.get("job") or {}).get("position_family", "unknown")
        for a in s.get("direction_annotations") or []:
            label_dist[a.get("label_status")] += 1
            src_dist[a.get("annotation_source")] += 1
            family_dir_dist[fam][a.get("direction_id")] += 1
        for c in s.get("key_claims") or []:
            claim_types[c.get("claim_type")] += 1
        for g in s.get("evidence_gaps") or []:
            gap_types[g.get("gap_type")] += 1
        for st in s.get("investigation_strategies") or []:
            strategy_types[st.get("strategy_type")] += 1
            dir_dist[st.get("direction_id")] += 1
            dim_dist[st.get("dimension")] += 1
            priority_dist[st.get("priority")] += 1
            difficulty_dist[st.get("difficulty")] += 1

    # 候选口径的「岗位族 × 方向」分布（非已审核标签，单独标注）
    cand_family_dir: dict[str, Counter] = defaultdict(Counter)
    cand_dir_dist: Counter = Counter()
    cand_dim_dist: Counter = Counter()
    cand_claim_types: Counter = Counter()
    cand_gap_types: Counter = Counter()
    cand_strategy_types: Counter = Counter()
    for c in cand_claims:
        cand_claim_types[c.get("claim_type")] += 1
    for g in cand_gaps:
        cand_gap_types[g.get("gap_type")] += 1
    for st in cand_strats:
        cand_dir_dist[st.get("direction_id")] += 1
        cand_dim_dist[st.get("dimension")] += 1
        cand_strategy_types[st.get("strategy_type")] += 1
        cand_family_dir[exp_family.get(st.get("experience_id"), "unknown")][st.get("direction_id")] += 1

    # 校验结果
    vpath = core.resolve(cfg["paths"]["output_dir"], cfg) / "dataset_validation_result.json"
    validation = core.read_json(vpath) if vpath.exists() else {}

    # 只读资产核验
    baseline = core.out_path("baseline_manifest", cfg)
    changed: list[str] = []
    if baseline.exists():
        base_root = core.read_json(baseline)["baseline_root"]
        for rel, rec in core.read_json(baseline)["files"].items():
            p = Path(base_root) / rel
            if not p.exists() or core.sha256_file(p) != rec["sha256"]:
                changed.append(rel)
    manifest = core.out_path("source_manifest", cfg)
    src_changed: list[str] = []
    if manifest.exists():
        for rel, rec in core.read_json(manifest)["files"].items():
            p = core.resolve(rel, cfg)
            if not p.exists() or core.sha256_file(p) != rec["sha256"]:
                src_changed.append(rel)

    # 训练行为静态扫描：基于 AST 识别真实 import / 训练调用，忽略注释与字符串
    train_hits = _scan_training_code(cfg)

    return {
        "generated_at": core.now_iso(),
        "ontology_version": cfg["ontology_version"],
        "source": {
            "resume_count": len(resumes),
            "candidate_count": len({r.get("candidate_id") for r in resumes}),
            "experience_count": len(experiences),
            "question_count": len(questions),
            "chain_count": len(chains),
            "position_family_count": len(tax["position_families"]),
            "position_count": len({r.get("position_id") for r in resumes}),
            "experience_type_distribution": dict(Counter(
                e.get("experience_type") for e in experiences)),
        },
        "ontology": {
            "direction_count": len(directions),
            "direction_status_distribution": dict(Counter(
                d.get("status") for d in directions)),
            "multi_parent_direction_count": sum(
                1 for d in directions if len(d.get("parent_dimensions") or []) > 1),
            "competency_count": len(comps),
            "competency_family_distribution": dict(Counter(
                c.get("position_family") for c in comps)),
        },
        "intent_analysis": intent.get("summary", {}),
        "candidates": {
            "claims": len(cand_claims), "gaps": len(cand_gaps),
            "strategies": len(cand_strats), "unknown_preview_samples": len(preview),
            "all_pending": all(
                (r.get("review") or {}).get("annotation_status") == "pending"
                for r in cand_claims + cand_gaps + cand_strats),
            "claim_type_distribution": dict(cand_claim_types),
            "gap_type_distribution": dict(cand_gap_types),
            "strategy_type_distribution": dict(cand_strategy_types),
            "direction_distribution": dict(cand_dir_dist),
            "primary_dimension_distribution": dict(cand_dim_dist),
        },
        "annotations": {name: len(rows) for name, rows in annotations.items()},
        "review_status_distribution": dict(review_status),
        "review_source_distribution": dict(review_source),
        "processed": {
            "sample_count": len(samples),
            "resume_count": len({s.get("resume_id") for s in samples}),
            "candidate_count": len({s.get("candidate_id") for s in samples}),
            "experience_count": len({(s.get("experience") or {}).get("experience_id")
                                     for s in samples}),
            "claim_type_distribution": dict(claim_types),
            "gap_type_distribution": dict(gap_types),
            "strategy_type_distribution": dict(strategy_types),
            "direction_distribution": dict(dir_dist),
            "primary_dimension_distribution": dict(dim_dist),
            "label_status_distribution": dict(label_dist),
            "annotation_source_distribution": dict(src_dist),
            "priority_distribution": dict(priority_dist),
            "difficulty_distribution": dict(difficulty_dist),
        },
        "family_direction_distribution": {
            fam: dict(c) for fam, c in sorted(family_dir_dist.items())},
        "candidate_family_direction_distribution": {
            fam: dict(c) for fam, c in sorted(cand_family_dir.items())},
        "quality": {
            "dataset_status": validation.get("dataset_status", "not_validated"),
            "validation_passed": validation.get("passed"),
            "validation_errors": validation.get("error_count"),
            "validation_warnings": validation.get("warning_count"),
            "duplicate_strategy_count": (validation.get("statistics") or {}).get(
                "duplicate_strategy_count", 0),
            "duplicate_experience_texts": (validation.get("statistics") or {}).get(
                "duplicate_experience_texts", 0),
        },
        "safety": {
            "rism001_baseline_changed": changed,
            "readonly_source_changed": src_changed,
            "training_code_hits": train_hits,
            "llm_enabled": cfg["llm"]["enabled"],
            "llm_provider": cfg["llm"]["provider"],
            "privacy_flags": cfg["privacy"],
        },
    }


def build_report(stats: dict[str, Any], cfg: dict[str, Any]) -> Path:
    s, c, p, o = stats["source"], stats["candidates"], stats["processed"], stats["ontology"]
    q, safe = stats["quality"], stats["safety"]
    sections: list[tuple[str, str]] = [
        ("1. 数据规模（RISM-001 只读源数据）", render.kv_table({
            "简历数量": s["resume_count"], "候选人数量": s["candidate_count"],
            "经历数量": s["experience_count"], "历史问题数量": s["question_count"],
            "历史追问链数量": s["chain_count"], "岗位类别数": s["position_count"],
            "岗位族数量": s["position_family_count"],
        })),
        ("2. 本体目录", render.kv_table({
            "追问方向总数": o["direction_count"],
            "方向状态分布": str(o["direction_status_distribution"]),
            "关联多个一级维度的方向数": o["multi_parent_direction_count"],
            "岗位能力条目数": o["competency_count"],
            "岗位能力族分布": str(o["competency_family_distribution"]),
        })),
        ("3. 历史追问意图分析", render.kv_table(stats["intent_analysis"] or {"状态": "尚未生成"})),
        ("4. 候选数据（全部 pending，非已审核标签）", render.kv_table({
            "候选 Claim": c["claims"], "候选 Evidence Gap": c["gaps"],
            "候选 Strategy": c["strategies"],
            "unknown-only 预览样本": c["unknown_preview_samples"],
            "全部候选均为 pending": c["all_pending"],
        })),
        ("5. 人工审核记录", render.kv_table(stats["annotations"])),
        ("6. 审核状态与来源分布", render.md_table(
            ["审核状态", "数量"], _counter_table(Counter(stats["review_status_distribution"])))
            + "\n\n" + render.md_table(
                ["标注来源", "数量"], _counter_table(Counter(stats["review_source_distribution"])))),
        ("7. 正式数据集统计", render.kv_table({
            "样本数": p["sample_count"], "简历数": p["resume_count"],
            "候选人数": p["candidate_count"], "经历数": p["experience_count"],
            "数据集状态": q["dataset_status"],
        })),
        ("8. Claim / Evidence Gap 类型分布（正式 + 候选）", render.md_table(
            ["口径", "类型", "数量"],
            [["正式", k, v] for k, v in sorted(p["claim_type_distribution"].items())]
            + [["候选", k, v] for k, v in sorted(c["claim_type_distribution"].items())]
            + [["正式-Gap", k, v] for k, v in sorted(p["gap_type_distribution"].items())]
            + [["候选-Gap", k, v] for k, v in sorted(c["gap_type_distribution"].items())])),
        ("9. 追问方向 / 一级维度 / 策略类型分布（候选口径）", render.md_table(
            ["类别", "取值", "数量"],
            [["方向", k, v] for k, v in sorted(c["direction_distribution"].items())]
            + [["一级维度", k, v] for k, v in sorted(c["primary_dimension_distribution"].items())]
            + [["策略类型", k, v] for k, v in sorted(c["strategy_type_distribution"].items())])),
        ("10. Positive / Negative / Unknown 分布", _table_or_empty(
            ["label_status", "正式样本计数"],
            [[k, v] for k, v in sorted(p["label_status_distribution"].items())])),
        ("11. 各方向标注来源分布", _table_or_empty(
            ["annotation_source", "数量"],
            [[str(k), v] for k, v in sorted(
                p["annotation_source_distribution"].items(), key=lambda x: str(x[0]))])),
        ("12. 不同岗位族的方向分布（候选口径，非已审核标签）", render.md_table(
            ["岗位族", "方向 ID", "候选策略计数"],
            [[fam, did, n] for fam, dist in stats["candidate_family_direction_distribution"].items()
             for did, n in sorted(dist.items(), key=lambda x: -x[1])][:80])),
        ("13. 优先级与难度（正式样本）", _table_or_empty(
            ["类别", "取值", "数量"],
            [["priority", k, v] for k, v in sorted(p["priority_distribution"].items())]
            + [["difficulty", k, v] for k, v in sorted(p["difficulty_distribution"].items())])),
        ("14. 重复与异常", render.kv_table({
            "校验结论": q["validation_passed"], "错误数": q["validation_errors"],
            "警告数": q["validation_warnings"],
            "重复策略数": q["duplicate_strategy_count"],
            "出现在多个样本的经历文本数": q["duplicate_experience_texts"],
            "正式样本重复 sample_id": "由 validate_dataset.py 逐条检测",
        })),
        ("15. 安全与合规", render.kv_table({
            "RISM-001 基线被改动文件": safe["rism001_baseline_changed"] or "0（无）",
            "只读源资产被改动": safe["readonly_source_changed"] or "0（无）",
            "RISM-002 代码中的训练调用命中": safe["training_code_hits"] or "0（无）",
            "外部 LLM 启用": safe["llm_enabled"],
            "外部 LLM 服务": safe["llm_provider"],
            "报告输出简历正文/个人信息": "否（配置 privacy.id_only_in_reports=true）",
        })),
        ("16. 状态解读",
         "正式数据集当前为空是预期状态：所有候选 Claim / Evidence Gap / Strategy 与追问方向"
         "均为 pending，需人工逐条审核后由 record_review.py 记录，再由 build_dataset.py 生成正式样本。"
         "未出现的方向一律保持 unknown，不会被自动转换为 negative；"
         "规则/历史问题来源的输出不会被标记为 reviewed 或高可信度标签。"),
    ]
    return render.write_report(
        core.resolve(cfg["paths"]["output_dir"], cfg) / "dataset_report.md",
        "RISM-002 数据集统计与质量报告", sections,
        meta={"ontology_version": cfg["ontology_version"],
              "生成脚本": "scripts/rism002/dataset_report.py",
              "隐私": "仅含 ID / 计数 / 枚举分布，不含简历正文与个人信息"})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成 RISM-002 数据集统计报告")
    ap.add_argument("--config", help="主配置路径")
    ap.add_argument("--json-only", action="store_true", help="只输出 JSON")
    args = ap.parse_args(argv)
    try:
        cfg = core.load_config(args.config)
        stats = collect(cfg)
        out_dir = core.resolve(cfg["paths"]["output_dir"], cfg)
        core.write_json(out_dir / "dataset_report.json", stats)
        if not args.json_only:
            path = build_report(stats, cfg)
            print(f"[RISM-002] 统计报告: {path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[RISM-002] 统计失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"[RISM-002] 统计完成 | 正式样本 {stats['processed']['sample_count']} | "
          f"候选 Claim {stats['candidates']['claims']} / Gap {stats['candidates']['gaps']} / "
          f"Strategy {stats['candidates']['strategies']} | 方向 {stats['ontology']['direction_count']} | "
          f"审核记录 {sum(stats['annotations'].values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
