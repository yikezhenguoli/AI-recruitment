"""RISM-001 原始数据只读审计器。

检查 JSONL 格式、字段缺失、ID 唯一性、外键关联、原文引用与偏移、
追问链一致性、Embedding 资产只读性；不修改任何原始文件。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..parsers import jsonl as parser
from ..utils import core

# 必需字段来自阶段一对真实数据的实测，不照搬任务书示例
REQUIRED_FIELDS: dict[str, list[str]] = {
    "resumes": ["resume_id", "candidate_id", "target_position", "position_id",
                "family", "career_level", "resume_text"],
    "experiences": ["experience_id", "resume_id", "experience_type", "title",
                    "original_content"],
    "questions": ["question_id", "resume_id", "experience_id", "experience_type",
                  "reference", "dimension", "question_type", "question", "reason",
                  "expected_investigation", "priority", "difficulty", "follow_up_questions"],
    "chains": ["chain_id", "resume_id", "experience_id", "root_question_id",
               "dimension", "questions"],
}

ID_FIELD = {
    "resumes": "resume_id",
    "experiences": "experience_id",
    "questions": "question_id",
    "chains": "chain_id",
}

VALID_LEVELS = {"fact_confirmation", "process_detail", "principle_decision",
                "verification_challenge", "scenario_migration"}


def _field_checks(rows: list[dict[str, Any]], kind: str, label: str,
                  errors: list[str]) -> dict[str, int]:
    presence: dict[str, int] = {f: 0 for f in REQUIRED_FIELDS[kind]}
    for i, row in enumerate(rows, start=1):
        for field in REQUIRED_FIELDS[kind]:
            if field in row and row[field] is not None:
                presence[field] += 1
            else:
                errors.append(f"{label} 第 {i} 条缺少必需字段 '{field}'")
    return presence


def _unique_check(rows: list[dict[str, Any]], kind: str, label: str,
                  errors: list[str]) -> int:
    key = ID_FIELD[kind]
    seen: set[str] = set()
    dup = 0
    for row in rows:
        val = row.get(key)
        if val is None:
            continue
        if val in seen:
            dup += 1
            if dup <= 5:
                errors.append(f"{label} 重复 ID {key}={val}")
        seen.add(val)
    if dup > 5:
        errors.append(f"{label} 重复 ID 共 {dup} 条（仅列出前 5 条）")
    return len(seen)


def audit(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or core.load_config()
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, Any] = {}

    # 1) 格式与字段
    data: dict[str, list[dict[str, Any]]] = {}
    descriptions: dict[str, Any] = {}
    for kind in ("resumes", "experiences", "questions", "chains"):
        path = core.source_path(kind, cfg)
        if not path.exists():
            errors.append(f"源文件不存在: {path}")
            data[kind] = []
            continue
        rows, parse_errors = core.read_jsonl(path, strict=False)
        errors.extend(parse_errors)
        data[kind] = rows
        descriptions[kind] = parser.describe_jsonl(path)
        stats[f"{kind}_lines"] = len(rows)
        stats[f"{kind}_fields"] = _field_checks(rows, kind, kind, errors)
        stats[f"{kind}_unique_ids"] = _unique_check(rows, kind, kind, errors)

    resumes, experiences = data["resumes"], data["experiences"]
    questions, chains = data["questions"], data["chains"]
    by_resume = {r.get("resume_id"): r for r in resumes}
    by_exp = {e.get("experience_id"): e for e in experiences}
    by_q = {q.get("question_id"): q for q in questions}

    # 2) experience -> resume
    orphan_exp = 0
    for e in experiences:
        rid = e.get("resume_id")
        if rid not in by_resume:
            orphan_exp += 1
            if orphan_exp <= 5:
                errors.append(f"experience {e.get('experience_id')} 引用不存在的 resume_id={rid}")
    stats["orphan_experiences"] = orphan_exp

    # 3) question -> experience / resume / 原文与偏移
    bad_exp_ref = bad_resume_ref = bad_type = bad_quote = bad_offset = 0
    quote_checked = 0
    for q in questions:
        eid = q.get("experience_id")
        exp = by_exp.get(eid)
        if exp is None:
            bad_exp_ref += 1
            if bad_exp_ref <= 5:
                errors.append(f"question {q.get('question_id')} 引用不存在的 experience_id={eid}")
            continue
        if q.get("resume_id") != exp.get("resume_id"):
            bad_resume_ref += 1
            if bad_resume_ref <= 5:
                errors.append(f"question {q.get('question_id')} 的 resume_id 与经历所属简历不一致")
        if q.get("experience_type") != exp.get("experience_type"):
            bad_type += 1
            if bad_type <= 5:
                errors.append(f"question {q.get('question_id')} 的 experience_type 与经历不一致")
        ref = q.get("reference") or {}
        quote = ref.get("original_text") if isinstance(ref, dict) else None
        content = exp.get("original_content", "")
        if not isinstance(quote, str) or not quote:
            bad_quote += 1
            continue
        quote_checked += 1
        if quote not in content:
            bad_quote += 1
            if bad_quote <= 5:
                errors.append(f"question {q.get('question_id')} 的 reference.original_text 不是经历原文子串")
            continue
        s, t = ref.get("start_offset"), ref.get("end_offset")
        if isinstance(s, int) and isinstance(t, int):
            if content[s:t] != quote:
                bad_offset += 1
                if bad_offset <= 5:
                    errors.append(f"question {q.get('question_id')} 的引用字符偏移与原文不匹配")
    stats.update({
        "question_bad_experience_ref": bad_exp_ref,
        "question_bad_resume_ref": bad_resume_ref,
        "question_bad_experience_type": bad_type,
        "question_bad_quote": bad_quote,
        "question_bad_offset": bad_offset,
        "quote_offset_checked": quote_checked,
    })

    # 4) chain -> experience / root question / 递进
    bad_chain_exp = bad_root = bad_level = bad_sequence = 0
    for c in chains:
        eid = c.get("experience_id")
        if eid not in by_exp:
            bad_chain_exp += 1
            if bad_chain_exp <= 5:
                errors.append(f"chain {c.get('chain_id')} 引用不存在的 experience_id={eid}")
        root = by_q.get(c.get("root_question_id"))
        if root is None:
            bad_root += 1
            if bad_root <= 5:
                errors.append(f"chain {c.get('chain_id')} 的根问题不存在")
        elif root.get("experience_id") != eid:
            bad_root += 1
            if bad_root <= 5:
                errors.append(f"chain {c.get('chain_id')} 的根问题属于其它经历")
        items = c.get("questions") or []
        if not isinstance(items, list):
            errors.append(f"chain {c.get('chain_id')} questions 非数组")
            continue
        seqs = [it.get("sequence") for it in items if isinstance(it, dict)]
        if seqs != list(range(1, len(items) + 1)):
            bad_sequence += 1
            if bad_sequence <= 5:
                errors.append(f"chain {c.get('chain_id')} 的 sequence 不是从 1 连续递增")
        for it in items:
            if isinstance(it, dict) and it.get("level") not in VALID_LEVELS:
                bad_level += 1
                if bad_level <= 5:
                    errors.append(f"chain {c.get('chain_id')} 含未知追问层级 {it.get('level')}")
    stats.update({
        "chain_bad_experience_ref": bad_chain_exp,
        "chain_bad_root_question": bad_root,
        "chain_bad_level": bad_level,
        "chain_bad_sequence": bad_sequence,
    })

    # 5) 分布统计（只输出计数与枚举，不输出任何简历正文）
    stats["experience_type_distribution"] = dict(sorted(Counter(
        e.get("experience_type") for e in experiences).items()))
    stats["dimension_distribution"] = dict(sorted(Counter(
        q.get("dimension") for q in questions).items()))
    stats["question_type_distribution"] = dict(sorted(Counter(
        q.get("question_type") for q in questions).items()))
    stats["chain_depth_distribution"] = dict(sorted(Counter(
        c.get("chain_depth") for c in chains).items()))
    stats["chain_level_distribution"] = dict(sorted(Counter(
        it.get("level") for c in chains for it in (c.get("questions") or [])).items()))
    stats["position_family_distribution"] = dict(sorted(Counter(
        r.get("family") for r in resumes).items()))
    asked = {q.get("experience_id") for q in questions}
    stats["experiences_with_questions"] = len(asked & set(by_exp))
    stats["experiences_without_questions"] = len(set(by_exp) - asked)
    stats["unique_resume_ids_in_questions"] = len({q.get("resume_id") for q in questions})

    # 6) 标签兼容层一致性（只读）
    md_path = core.source_path("embedding_metadata", cfg)
    if md_path.exists():
        md = core.read_json(md_path)
        tax_dims = core.primary_dimension_ids(cfg)
        if md.get("label_names") != tax_dims:
            errors.append("RISM-002 一级维度顺序与 RISM-001 metadata.label_names 不一致")
        stats["rism001_label_names"] = md.get("label_names")
        stats["rism001_sample_count"] = len(md.get("experience_ids", []))
    else:
        warnings.append("未找到 RISM-001 embedding metadata，跳过标签兼容层比对")

    # 7) 只读资产指纹比对
    manifest_path = core.out_path("source_manifest", cfg)
    readonly: dict[str, Any] = {"checked": 0, "changed": [], "missing": []}
    if manifest_path.exists():
        manifest = core.read_json(manifest_path)
        for rel, rec in manifest["files"].items():
            p = core.resolve(rel, cfg)
            if not p.exists():
                readonly["missing"].append(rel)
                continue
            readonly["checked"] += 1
            if core.sha256_file(p) != rec["sha256"]:
                readonly["changed"].append(rel)
        if readonly["changed"] or readonly["missing"]:
            errors.append(f"只读资产发生变化: changed={readonly['changed']} missing={readonly['missing']}")
    else:
        warnings.append("未找到 source_manifest.json，跳过只读资产指纹比对")
    stats["readonly_assets"] = readonly

    # 8) embedding header 只读盘点
    emb: dict[str, Any] = {}
    for name in ("experience_embeddings", "job_embeddings", "labels"):
        p = core.resolve(f"embeddings/{name}.npy", cfg)
        if p.exists():
            emb[name] = parser.npy_header(p)
    npz = core.resolve("embeddings/split_indices.npz", cfg)
    if npz.exists():
        emb["split_indices_members"] = parser.npz_members(npz)
    stats["embedding_assets"] = emb

    return {
        "passed": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "statistics": stats,
        "file_descriptions": descriptions,
        "ontology_version": cfg["ontology_version"],
        "generated_at": core.now_iso(),
    }
