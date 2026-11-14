#!/usr/bin/env python3
"""阶段七：记录「人工审核决定」（一次一条，绝不批量、绝不自动批准）。

设计约束：
- 必须显式传入 --confirm-human-review、--annotator、--reason，缺一即拒绝执行。
- 只记录人工做出的决定，脚本本身不会推断、不会批量把 pending 改成 approved。
- 方向的 negative 只能由人工在 direction_annotation 中显式给出，未出现方向永远保持 unknown。
- 写出的审核记录保留 annotation_source / annotation_status / annotator_id /
  reviewed_at / review_reason / ontology_version，且审核状态与 label_status 互不推导。

用法（每次一条）：
    # 批准一个追问方向
    python3 scripts/rism002/record_review.py --entity direction \
        --id hist_data_verification__data_evidence --decision approved \
        --annotator human_01 --reason "已核对该方向定义与排除条件" --confirm-human-review

    # 批准一条 Claim
    python3 scripts/rism002/record_review.py --entity claim \
        --id CLM_037707_01 --decision approved \
        --annotator human_01 --reason "已核对原文与字符偏移" --confirm-human-review

    # 记录「某经历某方向明确不值得追问」（唯一允许产生 negative 的入口）
    python3 scripts/rism002/record_review.py --entity direction_annotation \
        --experience-id EXP_00037707 --direction-id hist_data_verification__data_evidence \
        --label-status negative --annotator human_01 \
        --reason "人工确认该经历与数据核实无关" --confirm-human-review
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rism002.schemas import validator as schema  # noqa: E402
from rism002.utils import core  # noqa: E402

ENTITIES: dict[str, tuple[str, str, str, str]] = {
    # entity: (候选来源配置键, 审核输出配置键, ID 字段, Schema 实体名)
    "claim": ("candidate_claims", "human_claims", "claim_id", "claim"),
    "gap": ("candidate_gaps", "human_gaps", "gap_id", "evidence_gap"),
    "strategy": ("candidate_strategies", "human_strategies", "strategy_id", "strategy"),
}

NON_HUMAN = {"rule_based", "historical_question", "llm", "unknown", "auto", "system"}


def _review(*, decision: str, annotator: str, reason: str,
            cfg: dict[str, Any]) -> dict[str, Any]:
    return core.review_block(
        source="human", status=decision, annotator_id=annotator,
        reviewed_at=core.now_iso(), review_reason=reason, cfg=cfg)


def _load_or_empty(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows, errs = core.read_jsonl(path, strict=False)
    if errs:
        raise ValueError(f"审核文件存在解析错误，已中止以防覆盖: {path} | {errs[:2]}")
    return rows


def _upsert(path: Path, record: dict[str, Any], id_field: str) -> str:
    rows = _load_or_empty(path)
    key = record[id_field]
    found = False
    for i, row in enumerate(rows):
        if row.get(id_field) == key:
            rows[i] = record
            found = True
            break
    if not found:
        rows.append(record)
    core.write_jsonl(path, rows)
    return "更新" if found else "追加"


def record_entity(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    source_key, target_key, id_field, entity = ENTITIES[args.entity]
    source = core.out_path(source_key, cfg)
    candidates, errs = core.read_jsonl(source, strict=False) if source.exists() else ([], [])
    if errs:
        raise ValueError(f"候选文件解析失败: {errs[:2]}")
    match = next((r for r in candidates if r.get(id_field) == args.id), None)
    if match is None:
        raise ValueError(f"未找到 {args.entity} ID={args.id}（候选来源 {source}）")

    rec = dict(match)
    rec["review"] = _review(decision=args.decision, annotator=args.annotator,
                            reason=args.reason, cfg=cfg)
    if args.entity == "strategy":
        # 人工批准策略 = 明确认定该方向值得追问；拒绝时不改变 label_status
        if args.decision == "approved":
            rec["label_status"] = args.label_status or "positive"
    schema_errs = schema.validate_entity(rec, entity)
    if schema_errs:
        raise ValueError(f"审核记录不符合 Schema: {schema_errs[:3]}")
    action = _upsert(core.out_path(target_key, cfg), rec, id_field)
    return {"entity": args.entity, "id": args.id, "decision": args.decision,
            "action": action, "target": str(core.out_path(target_key, cfg)),
            "label_status": rec.get("label_status")}


def record_direction(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    path = core.out_path("directions", cfg)
    doc = core.read_json(path)
    match = next((d for d in doc["directions"] if d.get("direction_id") == args.id), None)
    if match is None:
        raise ValueError(f"未找到 direction_id={args.id}")
    match["review"] = _review(decision=args.decision, annotator=args.annotator,
                              reason=args.reason, cfg=cfg)
    if args.decision == "approved":
        match["status"] = "approved"
    else:
        # 拒绝不删除方向，保留 candidate 状态与审计痕迹
        match["status"] = "candidate"
    schema_errs = schema.validate_entity(match, "direction")
    if schema_errs:
        raise ValueError(f"方向记录不符合 Schema: {schema_errs[:3]}")
    core.write_json(path, doc)
    return {"entity": "direction", "id": args.id, "decision": args.decision,
            "action": "更新", "status": match["status"], "target": str(path)}


def record_direction_annotation(cfg: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if not args.experience_id or not args.direction_id or not args.label_status:
        raise ValueError("direction_annotation 必须提供 --experience-id / --direction-id / --label-status")
    if args.label_status not in cfg["review"]["label_statuses"]:
        raise ValueError("label_status 非法")
    if args.label_status == "negative":
        print("[RISM-002] 注意：negative 表示「人工已审核并明确判定不值得追问」，"
              "不得用于未判断的方向。", file=sys.stderr)
    rec = {
        "experience_id": args.experience_id,
        "direction_id": args.direction_id,
        "label_status": args.label_status,
        "annotation_source": "human",
        "annotation_status": "approved",
        "reviewed": True,
        "annotator_id": args.annotator,
        "reviewed_at": core.now_iso(),
        "review_reason": args.reason,
        "ontology_version": cfg["ontology_version"],
    }
    schema_errs = schema.validate(rec, schema.schema_for("sample")["properties"]["direction_annotations"]["items"])
    if schema_errs:
        raise ValueError(f"方向标注不符合 Schema: {schema_errs[:3]}")
    path = core.out_path("human_direction_annotations", cfg)
    rows = _load_or_empty(path)
    rows = [r for r in rows
            if not (r.get("experience_id") == args.experience_id
                    and r.get("direction_id") == args.direction_id)]
    rows.append(rec)
    core.write_jsonl(path, rows)
    return {"entity": "direction_annotation", "id": f"{args.experience_id}|{args.direction_id}",
            "label_status": args.label_status, "action": "追加/替换", "target": str(path)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="记录 RISM-002 人工审核决定（一次一条）")
    ap.add_argument("--config", help="主配置路径")
    ap.add_argument("--entity", required=True,
                    choices=[*ENTITIES, "direction", "direction_annotation"])
    ap.add_argument("--id", help="实体 ID（direction_annotation 除外）")
    ap.add_argument("--decision", choices=["approved", "rejected"])
    ap.add_argument("--annotator", help="人工审核员标识（必填，不接受机器来源）")
    ap.add_argument("--reason", help="审核理由（必填）")
    ap.add_argument("--experience-id", help="direction_annotation 专用")
    ap.add_argument("--direction-id", help="direction_annotation 专用")
    ap.add_argument("--label-status", choices=["positive", "negative", "unknown"],
                    help="direction_annotation 专用；strategy 批准时可选（默认 positive）")
    ap.add_argument("--confirm-human-review", action="store_true",
                    help="必须由人工显式确认；无此参数脚本拒绝写入")
    args = ap.parse_args(argv)

    if not args.confirm_human_review:
        print("[RISM-002] 拒绝执行：缺少 --confirm-human-review，本工具不会自动批准任何内容。",
              file=sys.stderr)
        return 2
    if not args.annotator or args.annotator.strip().lower() in NON_HUMAN:
        print("[RISM-002] 拒绝执行：--annotator 必须是真实人工标识。", file=sys.stderr)
        return 2
    if not args.reason or len(args.reason.strip()) < 8:
        print("[RISM-002] 拒绝执行：--reason 需填写至少 8 个字的审核理由。", file=sys.stderr)
        return 2
    if args.entity != "direction_annotation":
        if not args.id or not args.decision:
            print("[RISM-002] 拒绝执行：需要 --id 与 --decision。", file=sys.stderr)
            return 2

    try:
        cfg = core.load_config(args.config)
        core.ensure_dirs(cfg)
        if args.entity == "direction":
            result = record_direction(cfg, args)
        elif args.entity == "direction_annotation":
            result = record_direction_annotation(cfg, args)
        else:
            result = record_entity(cfg, args)
    except Exception as exc:  # noqa: BLE001
        print(f"[RISM-002] 审核记录失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"[RISM-002] 已记录人工审核 | entity={result['entity']} id={result['id']} "
          f"decision={result.get('decision', result.get('label_status'))} "
          f"action={result['action']} | {result['target']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
