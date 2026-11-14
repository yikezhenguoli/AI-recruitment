#!/usr/bin/env python3
"""阶段六（辅助）：生成待人工审核的候选 Claim / Gap / Strategy 与 Unknown 预览样本。

用法：python3 scripts/rism002/prepare_candidates.py

生成（data/intermediate/）：
    candidate_claims.jsonl / candidate_gaps.jsonl / candidate_strategies.jsonl
    rism002_unknown_preview.jsonl   （非正式样本，三态标注全为 unknown）
生成（data/annotations/，已存在则绝不覆盖）：
    claims.jsonl / evidence_gaps.jsonl / strategies.jsonl / direction_annotations.jsonl
    human_review_template.jsonl     （每次刷新，仅模板）

所有候选一律 pending，不产生任何 approved 标签。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rism002.analyzers import candidate_builder  # noqa: E402
from rism002.parsers import jsonl as parser  # noqa: E402
from rism002.utils import core  # noqa: E402


def _family_of(position_id: str, tax: dict) -> str:
    for fam in tax["position_families"]:
        if position_id in fam["position_ids"]:
            return fam["id"]
    return "unknown"


def build_unknown_previews(cfg: dict, result: dict) -> list[dict]:
    """构造 unknown-only 预览样本：无 Claim/Gap/Strategy、无正负标签。"""
    tax = core.load_taxonomy(cfg)
    idx = parser.load_source_index(cfg)
    by_exp = idx["by_experience"]
    by_resume = idx["by_resume"]
    comp_path = core.out_path("competencies", cfg)
    comps = core.read_json(comp_path)["competencies"] if comp_path.exists() else []
    req_by_family: dict[str, list[str]] = {}
    for c in comps:
        req_by_family.setdefault(c["position_family"], []).append(c["competency_name"])
    dir_path = core.out_path("directions", cfg)
    directions = core.read_json(dir_path)["directions"] if dir_path.exists() else []

    out = []
    for n, eid in enumerate(result["selected_experience_ids"], start=1):
        e = by_exp[eid]
        r = by_resume.get(e["resume_id"])
        if r is None:
            continue
        fam = _family_of(e.get("position_id", ""), tax)
        out.append({
            "sample_id": f"SAMPLE_PREVIEW_{n:04d}",
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
            "key_claims": [],
            "evidence_gaps": [],
            "investigation_strategies": [],
            "direction_annotations": [
                {"direction_id": d["direction_id"], "label_status": "unknown",
                 "annotation_source": None, "reviewed": False,
                 "review_reason": "未审核，不作正负判断", "ontology_version": cfg["ontology_version"]}
                for d in directions
            ],
            "annotation": {
                "annotation_source": "rule_based",
                "annotation_status": "pending",
                "annotator_id": None,
                "reviewed": False,
                "reviewed_at": None,
                "ontology_version": cfg["ontology_version"],
            },
        })
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成 RISM-002 待审核候选数据")
    ap.add_argument("--config", help="主配置路径")
    args = ap.parse_args(argv)
    try:
        cfg = core.load_config(args.config)
        core.ensure_dirs(cfg)
        result = candidate_builder.build_candidates(cfg)

        n1 = core.write_jsonl(core.out_path("candidate_claims", cfg), result["claims"])
        n2 = core.write_jsonl(core.out_path("candidate_gaps", cfg), result["evidence_gaps"])
        n3 = core.write_jsonl(core.out_path("candidate_strategies", cfg), result["strategies"])

        # 审核数据文件：只在不存在时创建，绝不覆盖人工已填写内容
        created = []
        for key in ("human_claims", "human_gaps", "human_strategies", "human_direction_annotations"):
            p = core.out_path(key, cfg)
            if not p.exists():
                core.write_jsonl(p, [])
                created.append(p.name)

        # 审核模板（每次刷新，仅模板，不是正式标注）
        template = []
        for entity, rows in (("claim", result["claims"]),
                             ("evidence_gap", result["evidence_gaps"]),
                             ("strategy", result["strategies"])):
            for row in rows:
                rec = dict(row)
                rec["_entity"] = entity
                rec["_review_instructions"] = (
                    "人工逐条核验后，将 review.annotation_source 改为 human、"
                    "annotation_status 改为 approved（或 rejected）、reviewed 改为 true，"
                    "并填写 annotator_id / reviewed_at / review_reason；"
                    "随后把该记录按实体类型放入 data/annotations/ 下对应 JSONL 文件。"
                    "请勿在未核验的情况下批准。")
                template.append(rec)
        core.write_jsonl(core.out_path("review_template", cfg), template)

        previews = build_unknown_previews(cfg, result)
        preview_path = core.resolve(cfg["paths"]["intermediate_dir"], cfg) / "rism002_unknown_preview.jsonl"
        n4 = core.write_jsonl(preview_path, previews)

        core.write_json(core.resolve(cfg["paths"]["output_dir"], cfg) / "candidate_build_result.json", {
            "generated_at": core.now_iso(),
            "selected_experience_ids": result["selected_experience_ids"],
            "experience_type_coverage": result["experience_type_coverage"],
            "position_id_coverage": result["position_family_coverage"],
            "candidate_claims": n1, "candidate_gaps": n2, "candidate_strategies": n3,
            "unknown_preview_samples": n4,
            "approved_records_created": 0,
            "annotation_files_initialized": created,
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[RISM-002] 候选生成异常: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"[RISM-002] 候选生成完成 | 经历 {len(result['selected_experience_ids'])} | "
          f"Claim {n1} / Gap {n2} / Strategy {n3}（全部 pending）| "
          f"Unknown 预览样本 {n4} | 审核文件新建 {len(created)} | 批准记录 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
