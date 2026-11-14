"""RISM-002 主训练数据集校验器（内容级，含全部硬性门槛）。

硬性门槛：
- 未审核记录不得进入正式数据集（review 必须 human + approved + reviewed）
- Claim.source_text 必须是经历原文的真实子串
- Evidence Gap 必须关联同经历的 Claim
- Strategy 必须关联 approved 方向、同经历的 Claim 与 Gap
- negative 必须来自人工审核；unknown 绝不自动转 negative
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ..parsers import jsonl as parser
from ..schemas import validator as schema
from ..utils import core


def _approved_review(rec: dict[str, Any], cfg: dict[str, Any], label: str,
                     errors: list[str]) -> None:
    if not core.is_approved(rec, cfg):
        rv = rec.get("review", {})
        errors.append(
            f"{label}: 未通过人工审核的记录不得进入正式数据集 "
            f"(source={rv.get('annotation_source')}, status={rv.get('annotation_status')}, "
            f"reviewed={rv.get('reviewed')})")


def validate(cfg: dict[str, Any] | None = None,
             samples: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cfg = cfg or core.load_config()
    errors: list[str] = []
    warnings: list[str] = []

    path = core.out_path("processed_samples", cfg)
    if samples is None:
        if not path.exists():
            return {"passed": False, "dataset_status": "invalid",
                    "error_count": 1, "warning_count": 0,
                    "errors": [f"正式数据集不存在: {path}"], "warnings": [],
                    "statistics": {"sample_count": 0},
                    "generated_at": core.now_iso()}
        samples, parse_errors = core.read_jsonl(path, strict=False)
        errors.extend(parse_errors)

    idx = parser.load_source_index(cfg)
    by_exp = idx["by_experience"]
    by_resume = idx["by_resume"]
    dpath = core.out_path("directions", cfg)
    directions_doc = core.read_json(dpath) if dpath.exists() else {"directions": []}
    dir_by_id = {d["direction_id"]: d for d in directions_doc["directions"]}
    approved_dirs = {k for k, v in dir_by_id.items() if v.get("status") == "approved"}
    dims = set(core.primary_dimension_ids(cfg))
    version = cfg["ontology_version"]

    seen_ids: dict[str, set[str]] = defaultdict(set)
    stat_claim_types: Counter = Counter()
    stat_gap_types: Counter = Counter()
    stat_directions: Counter = Counter()
    stat_dims: Counter = Counter()
    stat_labels: Counter = Counter()
    stat_sources: Counter = Counter()
    stat_priority: Counter = Counter()
    stat_difficulty: Counter = Counter()
    stat_strategy_types: Counter = Counter()
    exp_texts: Counter = Counter()
    duplicate_strategy_keys: set[str] = set()
    duplicate_strategy_count = 0

    for si, s in enumerate(samples, start=1):
        tag = s.get("sample_id", f"#{si}")
        for msg in schema.validate_entity(s, "sample"):
            errors.append(f"[{tag}] {msg}")

        # ID 唯一
        for field, key in (("sample_id", "sample"), ("resume_id", "resume_ref"),
                           ("candidate_id", "candidate_ref")):
            val = s.get(field)
            if field == "sample_id":
                if val in seen_ids[key]:
                    errors.append(f"[{tag}] 重复 sample_id={val}")
                seen_ids[key].add(val)

        rid, eid = s.get("resume_id"), (s.get("experience") or {}).get("experience_id")
        r = by_resume.get(rid)
        e = by_exp.get(eid)
        if r is None:
            errors.append(f"[{tag}] 引用不存在的 resume_id={rid}")
        elif s.get("candidate_id") != r.get("candidate_id"):
            errors.append(f"[{tag}] candidate_id 与简历不一致")
        if e is None:
            errors.append(f"[{tag}] 引用不存在的 experience_id={eid}")
            continue
        exp = s.get("experience") or {}
        if exp.get("experience_text") != e.get("original_content"):
            errors.append(f"[{tag}] experience_text 与源经历原文不一致（不得改写）")
        if exp.get("experience_type") != e.get("experience_type"):
            errors.append(f"[{tag}] experience_type 与源经历不一致")
        exp_texts[exp.get("experience_text", "")] += 1

        # 本样本内的实体索引
        claims = s.get("key_claims") or []
        gaps = s.get("evidence_gaps") or []
        strategies = s.get("investigation_strategies") or []
        claim_ids = {c.get("claim_id") for c in claims}
        gap_ids = {g.get("gap_id") for g in gaps}

        for c in claims:
            cid = c.get("claim_id", "?")
            if cid in seen_ids["claim"]:
                errors.append(f"[{tag}] 重复 claim_id={cid}")
            seen_ids["claim"].add(cid)
            for msg in schema.validate_entity(c, "claim"):
                errors.append(f"[{tag}/{cid}] {msg}")
            _approved_review(c, cfg, f"[{tag}/{cid}]", errors)
            if c.get("experience_id") != eid or c.get("resume_id") != rid:
                errors.append(f"[{tag}/{cid}] Claim 跨经历或跨简历引用")
            st = c.get("source_text", "")
            if not isinstance(st, str) or st not in exp.get("experience_text", ""):
                errors.append(f"[{tag}/{cid}] source_text 不是经历原文子串")
            span = c.get("source_span")
            if isinstance(span, dict) and isinstance(span.get("start_offset"), int) \
                    and isinstance(span.get("end_offset"), int):
                if exp.get("experience_text", "")[span["start_offset"]:span["end_offset"]] != st:
                    errors.append(f"[{tag}/{cid}] source_span 与原文不匹配")
            if (c.get("review") or {}).get("ontology_version") != version:
                errors.append(f"[{tag}/{cid}] ontology_version 不一致")
            stat_claim_types[c.get("claim_type")] += 1

        for g in gaps:
            gid = g.get("gap_id", "?")
            if gid in seen_ids["gap"]:
                errors.append(f"[{tag}] 重复 gap_id={gid}")
            seen_ids["gap"].add(gid)
            for msg in schema.validate_entity(g, "evidence_gap"):
                errors.append(f"[{tag}/{gid}] {msg}")
            _approved_review(g, cfg, f"[{tag}/{gid}]", errors)
            if g.get("experience_id") != eid or g.get("resume_id") != rid:
                errors.append(f"[{tag}/{gid}] Gap 跨经历或跨简历引用")
            rel = g.get("related_claim_ids") or []
            if not rel:
                errors.append(f"[{tag}/{gid}] Evidence Gap 未关联任何 Claim")
            for cid in rel:
                if cid not in claim_ids:
                    errors.append(f"[{tag}/{gid}] 关联了不存在的 Claim {cid}")
            desc = str(g.get("description", ""))
            if "造假" in desc and "不代表" not in desc:
                errors.append(f"[{tag}/{gid}] 证据缺口描述不得直接断定经历造假")
            if (g.get("review") or {}).get("ontology_version") != version:
                errors.append(f"[{tag}/{gid}] ontology_version 不一致")
            stat_gap_types[g.get("gap_type")] += 1

        for st in strategies:
            sid = st.get("strategy_id", "?")
            if sid in seen_ids["strategy"]:
                errors.append(f"[{tag}] 重复 strategy_id={sid}")
            seen_ids["strategy"].add(sid)
            for msg in schema.validate_entity(st, "strategy"):
                errors.append(f"[{tag}/{sid}] {msg}")
            _approved_review(st, cfg, f"[{tag}/{sid}]", errors)
            did = st.get("direction_id")
            if did not in dir_by_id:
                errors.append(f"[{tag}/{sid}] 引用不存在的 direction_id={did}")
            elif did not in approved_dirs:
                errors.append(f"[{tag}/{sid}] 引用了未批准的方向 {did}（status={dir_by_id[did].get('status')}）")
            else:
                d = dir_by_id[did]
                if st.get("direction_name") != d.get("direction_name"):
                    errors.append(f"[{tag}/{sid}] direction_name 与目录不一致")
                if st.get("dimension") not in (d.get("parent_dimensions") or []) \
                        and st.get("dimension") not in dims:
                    errors.append(f"[{tag}/{sid}] dimension 非法")
            for cid in st.get("trigger_claim_ids") or []:
                if cid not in claim_ids:
                    errors.append(f"[{tag}/{sid}] 触发 Claim 不存在或跨经历 {cid}")
            for gid in st.get("trigger_gap_ids") or []:
                if gid not in gap_ids:
                    errors.append(f"[{tag}/{sid}] 触发 Gap 不存在或跨经历 {gid}")
            if not (st.get("trigger_claim_ids") or []) and not (st.get("trigger_gap_ids") or []):
                errors.append(f"[{tag}/{sid}] 策略未追溯到任何 Claim 或 Gap")
            if (st.get("review") or {}).get("ontology_version") != version:
                errors.append(f"[{tag}/{sid}] ontology_version 不一致")
            key = f"{eid}|{st.get('dimension')}|{did}|{st.get('strategy_type')}|{st.get('sequence')}"
            if key in duplicate_strategy_keys:
                duplicate_strategy_count += 1
                errors.append(f"[{tag}/{sid}] 重复策略（同经历/维度/方向/类型/序号）")
            duplicate_strategy_keys.add(key)
            stat_directions[did] += 1
            stat_dims[st.get("dimension")] += 1
            stat_priority[st.get("priority")] += 1
            stat_difficulty[st.get("difficulty")] += 1
            stat_strategy_types[st.get("strategy_type")] += 1

        # 方向三态标注
        anns = s.get("direction_annotations") or []
        ann_ids = set()
        for a in anns:
            did = a.get("direction_id")
            if did in ann_ids:
                errors.append(f"[{tag}] 重复 direction_annotation {did}")
            ann_ids.add(did)
            label = a.get("label_status")
            stat_labels[label] += 1
            stat_sources[a.get("annotation_source")] += 1
            if label == "negative":
                if not a.get("reviewed") or a.get("annotation_source") != "human":
                    errors.append(f"[{tag}/{did}] negative 必须由人工审核确认（reviewed=true + source=human）")
            if label == "positive" and not a.get("reviewed"):
                errors.append(f"[{tag}/{did}] positive 必须已审核")
            if label == "unknown" and a.get("reviewed"):
                warnings.append(f"[{tag}/{did}] unknown 标注被标记为 reviewed，请确认")
            if a.get("ontology_version") != version:
                errors.append(f"[{tag}/{did}] ontology_version 不一致")
        # 未出现的 approved 方向必须补 unknown，绝不能补 negative
        for did in approved_dirs - ann_ids:
            warnings.append(f"[{tag}] approved 方向 {did} 未出现在 direction_annotations 中，应显式补 unknown")

        ann = s.get("annotation") or {}
        if ann.get("reviewed") and ann.get("annotation_source") != "human":
            errors.append(f"[{tag}] 顶层标注 reviewed=true 但来源不是 human")
        if ann.get("annotation_status") in ("approved", "reviewed") and not ann.get("reviewed"):
            errors.append(f"[{tag}] 顶层标注 {ann.get('annotation_status')} 但未 reviewed")
        if ann.get("ontology_version") != version:
            errors.append(f"[{tag}] 顶层 ontology_version 不一致")

    # 数据重复/泄漏
    duplicate_experience_texts = sum(1 for t, n in exp_texts.items() if n > 1 and t)
    if duplicate_experience_texts:
        warnings.append(f"存在 {duplicate_experience_texts} 段经历文本出现在多个样本中（跨岗位样本允许，需确认非重复样本）")
    if not samples:
        warnings.append("正式数据集为空：尚无人工已审核记录，处于 awaiting_human_review 状态（属预期，不是数据错误）")

    # 只读资产
    manifest_path = core.out_path("source_manifest", cfg)
    changed: list[str] = []
    if manifest_path.exists():
        for rel, rec in core.read_json(manifest_path)["files"].items():
            p = core.resolve(rel, cfg)
            if not p.exists() or core.sha256_file(p) != rec["sha256"]:
                changed.append(rel)
        if changed:
            errors.append(f"只读资产被修改: {changed}")

    stats = {
        "sample_count": len(samples),
        "resume_count": len({s.get("resume_id") for s in samples}),
        "candidate_count": len({s.get("candidate_id") for s in samples}),
        "experience_count": len({(s.get("experience") or {}).get("experience_id") for s in samples}),
        "claim_count": sum(len(s.get("key_claims") or []) for s in samples),
        "gap_count": sum(len(s.get("evidence_gaps") or []) for s in samples),
        "strategy_count": sum(len(s.get("investigation_strategies") or []) for s in samples),
        "direction_annotation_count": sum(len(s.get("direction_annotations") or []) for s in samples),
        "claim_type_distribution": dict(sorted(stat_claim_types.items())),
        "gap_type_distribution": dict(sorted(stat_gap_types.items())),
        "strategy_type_distribution": dict(sorted(stat_strategy_types.items())),
        "direction_distribution": dict(sorted(stat_directions.items())),
        "primary_dimension_distribution": dict(sorted(stat_dims.items())),
        "label_status_distribution": dict(sorted(stat_labels.items())),
        "annotation_source_distribution": dict(sorted(stat_sources.items(), key=lambda x: str(x[0]))),
        "priority_distribution": dict(sorted(stat_priority.items())),
        "difficulty_distribution": dict(sorted(stat_difficulty.items())),
        "duplicate_strategy_count": duplicate_strategy_count,
        "duplicate_experience_texts": duplicate_experience_texts,
        "approved_direction_count_in_ontology": len(approved_dirs),
        "readonly_assets_changed": changed,
        "hard_gate_unreviewed_records": sum(1 for e in errors if "未通过人工审核" in e),
        "hard_gate_bad_source_text": sum(1 for e in errors if "source_text 不是经历原文子串" in e),
    }

    status = ("ready" if samples and not errors else
              "awaiting_human_review" if not samples and not errors else "invalid")
    return {
        "passed": len(errors) == 0,
        "dataset_status": status,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "statistics": stats,
        "generated_at": core.now_iso(),
    }
