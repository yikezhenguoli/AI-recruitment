#!/usr/bin/env python3
"""阶段六：构建 RISM-002 主训练数据集。

只消费 data/annotations/ 中「人工已审核」的记录与 ontology 中 approved 的方向。
未审核候选一律排除；未出现的方向一律补 unknown，绝不自动转 negative。

用法：
    python3 scripts/rism002/build_dataset.py
    python3 scripts/rism002/build_dataset.py --include-pending-as-unknown
    python3 scripts/rism002/build_dataset.py --validate

输出：
    data/processed/rism002_samples.jsonl
    outputs/rism002/build_result.json
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rism002.parsers import jsonl as parser  # noqa: E402
from rism002.schemas import validator as schema  # noqa: E402
from rism002.utils import core  # noqa: E402


def _read_approved(path: Path, cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    rows, errs = core.read_jsonl(path, strict=False)
    if errs:
        raise ValueError(f"审核文件 {path.name} 存在解析错误: {errs[:3]}")
    approved = [r for r in rows if core.is_approved(r, cfg)]
    return approved, len(rows) - len(approved)


def _family_of(position_id: str, tax: dict[str, Any]) -> str:
    for fam in tax["position_families"]:
        if position_id in fam["position_ids"]:
            return fam["id"]
    return "unknown"


def build(cfg: dict[str, Any], *, include_pending_as_unknown: bool = False) -> dict[str, Any]:
    tax = core.load_taxonomy(cfg)
    idx = parser.load_source_index(cfg)
    by_exp, by_resume = idx["by_experience"], idx["by_resume"]

    dpath = core.out_path("directions", cfg)
    dirs_doc = core.read_json(dpath) if dpath.exists() else {"directions": []}
    approved_dirs = {d["direction_id"]: d for d in dirs_doc["directions"]
                     if d.get("status") == "approved"}
    all_dirs = dirs_doc["directions"]
    comp_path = core.out_path("competencies", cfg)
    comps = core.read_json(comp_path)["competencies"] if comp_path.exists() else []
    req_by_family: dict[str, list[str]] = defaultdict(list)
    for c in comps:
        req_by_family[c["position_family"]].append(c["competency_name"])

    claims, skipped_c = _read_approved(core.out_path("human_claims", cfg), cfg)
    gaps, skipped_g = _read_approved(core.out_path("human_gaps", cfg), cfg)
    strategies, skipped_s = _read_approved(core.out_path("human_strategies", cfg), cfg)
    # 方向标注记录：其审核状态字段在顶层（不是 review 块），单独过滤
    ann_path = core.out_path("human_direction_annotations", cfg)
    ann_all, _ = core.read_jsonl(ann_path, strict=False) if ann_path.exists() else ([], [])
    valid_anns = [a for a in ann_all
                  if a.get("reviewed") is True
                  and a.get("annotation_source") == "human"
                  and a.get("label_status") in ("positive", "negative", "unknown")]
    skipped_d = len(ann_all) - len(valid_anns)
    ann_by_exp: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for a in valid_anns:
        ann_by_exp[a.get("experience_id")][a.get("direction_id")] = a

    by_exp_claims: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_exp_gaps: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_exp_strategies: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in claims:
        by_exp_claims[c["experience_id"]].append(c)
    for g in gaps:
        by_exp_gaps[g["experience_id"]].append(g)
    for s in strategies:
        by_exp_strategies[s["experience_id"]].append(s)

    # 策略引用的方向必须已批准，且触发 ID 必须在本经历内
    rejected_strategies: list[str] = []
    for eid, items in list(by_exp_strategies.items()):
        cids = {c["claim_id"] for c in by_exp_claims.get(eid, [])}
        gids = {g["gap_id"] for g in by_exp_gaps.get(eid, [])}
        kept = []
        for s in items:
            if s.get("direction_id") not in approved_dirs:
                rejected_strategies.append(f"{s.get('strategy_id')}:方向未批准")
                continue
            if any(x not in cids for x in (s.get("trigger_claim_ids") or [])) or \
               any(x not in gids for x in (s.get("trigger_gap_ids") or [])):
                rejected_strategies.append(f"{s.get('strategy_id')}:触发 ID 无效")
                continue
            kept.append(s)
        by_exp_strategies[eid] = kept

    # 只有存在已审核实体的经历才生成正式样本
    eids = sorted(set(by_exp_claims) | set(by_exp_gaps) | set(by_exp_strategies))
    samples: list[dict[str, Any]] = []
    for n, eid in enumerate(eids, start=1):
        e = by_exp.get(eid)
        if e is None:
            continue
        r = by_resume.get(e["resume_id"])
        if r is None:
            continue
        fam = _family_of(e.get("position_id", ""), tax)
        anns = []
        for did in sorted(approved_dirs):
            rec = ann_by_exp.get(eid, {}).get(did)
            if rec:
                anns.append({
                    "direction_id": did,
                    "label_status": rec["label_status"],
                    "annotation_source": "human",
                    "reviewed": True,
                    "review_reason": rec.get("review_reason", ""),
                    "ontology_version": cfg["ontology_version"],
                })
            else:
                # 关键：未审核 / 未出现的方向一律 unknown，绝不转 negative
                anns.append({
                    "direction_id": did,
                    "label_status": "unknown",
                    "annotation_source": None,
                    "reviewed": False,
                    "review_reason": "未审核，缺乏判断依据",
                    "ontology_version": cfg["ontology_version"],
                })
        samples.append({
            "sample_id": f"SAMPLE_{n:06d}",
            "resume_id": e["resume_id"],
            "candidate_id": r.get("candidate_id"),
            "experience": {
                "experience_id": eid,
                "experience_type": e.get("experience_type"),
                "title": e.get("title", ""),
                "experience_text": e["original_content"],
            },
            "job": {
                "target_position": r.get("target_position"),
                "position_family": fam,
                "career_level": r.get("career_level"),
                "job_requirements": req_by_family.get(fam, []),
            },
            "key_claims": by_exp_claims.get(eid, []),
            "evidence_gaps": by_exp_gaps.get(eid, []),
            "investigation_strategies": by_exp_strategies.get(eid, []),
            "direction_annotations": anns,
            "annotation": {
                "annotation_source": "human",
                "annotation_status": "reviewed",
                "review_workflow_status": "approved",
                "annotator_id": "human_review",
                "reviewed": True,
                "reviewed_at": core.now_iso(),
                "ontology_version": cfg["ontology_version"],
            },
        })

    # 可选：把 unknown-only 预览样本并入（默认关闭；不含任何正负标签）
    preview_added = 0
    if include_pending_as_unknown:
        pp = core.resolve(cfg["paths"]["intermediate_dir"], cfg) / "rism002_unknown_preview.jsonl"
        if pp.exists():
            previews, _ = core.read_jsonl(pp)
            samples.extend(previews)
            preview_added = len(previews)

    # 构建时的 Schema 自检（不通过则不落盘）
    schema_errors: list[str] = []
    for s in samples:
        for msg in schema.validate_entity(s, "sample"):
            schema_errors.append(f"{s.get('sample_id')}: {msg}")
    if schema_errors:
        raise ValueError("样本 Schema 自检未通过，未写入数据集: " + "; ".join(schema_errors[:5]))

    out = core.out_path("processed_samples", cfg)
    core.write_jsonl(out, samples)

    return {
        "generated_at": core.now_iso(),
        "ontology_version": cfg["ontology_version"],
        "output": str(out),
        "sample_count": len(samples),
        "formal_sample_count": len(samples) - preview_added,
        "unknown_preview_samples_added": preview_added,
        "approved_directions": len(approved_dirs),
        "approved_claims": len(claims),
        "approved_gaps": len(gaps),
        "approved_strategies": sum(len(v) for v in by_exp_strategies.values()),
        "valid_direction_annotations": len(valid_anns),
        "skipped_unreviewed": {"claims": skipped_c, "gaps": skipped_g,
                               "strategies": skipped_s, "direction_annotations": skipped_d},
        "rejected_strategies": rejected_strategies,
        "unknown_directions_filled": sum(
            1 for s in samples for a in s["direction_annotations"]
            if a["label_status"] == "unknown"),
        "negative_directions_created": sum(
            1 for s in samples for a in s["direction_annotations"]
            if a["label_status"] == "negative"),
        "schema_self_check_errors": len(schema_errors),
        "dataset_status": (
            "ready" if len(samples) > 0 else "awaiting_human_review"),
        "blocking_conditions": [
            msg for cond, msg in (
                (not approved_dirs, "ontology 中尚无 status=approved 的追问方向，需人工审核后修改"),
                (not claims and not gaps and not strategies,
                 "data/annotations/ 中尚无人工已审核的 Claim / Gap / Strategy"),
            ) if cond
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="构建 RISM-002 主数据集")
    ap.add_argument("--config", help="主配置路径")
    ap.add_argument("--include-pending-as-unknown", action="store_true",
                    help="并入 unknown-only 预览样本（默认关闭；不产生任何正负标签）")
    ap.add_argument("--validate", action="store_true", help="构建后立即执行数据集校验")
    args = ap.parse_args(argv)
    try:
        cfg = core.load_config(args.config)
        core.ensure_dirs(cfg)
        flag = args.include_pending_as_unknown or cfg["dataset"]["include_pending_as_unknown"]
        result = build(cfg, include_pending_as_unknown=flag)
        core.write_json(core.resolve(cfg["paths"]["output_dir"], cfg) / "build_result.json", result)
    except Exception as exc:  # noqa: BLE001
        print(f"[RISM-002] 数据集构建失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"[RISM-002] 数据集构建完成 | 样本 {result['sample_count']} "
          f"(正式 {result['formal_sample_count']} / unknown 预览 {result['unknown_preview_samples_added']}) | "
          f"已批准方向 {result['approved_directions']} | 跳过未审核 "
          f"{sum(result['skipped_unreviewed'].values())} | negative 生成 {result['negative_directions_created']}")
    if args.validate:
        from rism002.validators import dataset_validator
        v = dataset_validator.validate(cfg)
        print(f"[RISM-002] 数据集校验: {'通过' if v['passed'] else '未通过'} | "
              f"错误 {v['error_count']} | 警告 {v['warning_count']}")
        return 0 if v["passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
