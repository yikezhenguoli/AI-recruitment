"""RISM-002 方向目录与岗位能力目录校验器。"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ..schemas import validator as schema
from ..utils import core


def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """有向图环检测，返回环路径列表。"""
    cycles: list[list[str]] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def dfs(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if state.get(nxt) == 1:
                start = stack.index(nxt) if nxt in stack else 0
                cycles.append(stack[start:] + [nxt])
            elif state.get(nxt, 0) == 0:
                dfs(nxt)
        stack.pop()
        state[node] = 2

    for n in graph:
        if state.get(n, 0) == 0:
            dfs(n)
    return cycles


def validate(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or core.load_config()
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, Any] = {}

    dpath = core.out_path("directions", cfg)
    cpath = core.out_path("competencies", cfg)
    if not dpath.exists():
        return {"passed": False, "error_count": 1, "warning_count": 0,
                "errors": [f"方向目录不存在: {dpath}"], "warnings": [], "statistics": {}}
    if not cpath.exists():
        return {"passed": False, "error_count": 1, "warning_count": 0,
                "errors": [f"岗位能力目录不存在: {cpath}"], "warnings": [], "statistics": {}}

    dirs_doc = core.read_json(dpath)
    comp_doc = core.read_json(cpath)
    directions = dirs_doc.get("directions", [])
    competencies = comp_doc.get("competencies", [])
    dims = core.primary_dimension_ids(cfg)
    families = {f["id"] for f in core.load_taxonomy(cfg)["position_families"]}
    statuses = core.enum_values("direction_status", cfg)

    # 版本一致
    for label, doc in (("方向目录", dirs_doc), ("能力目录", comp_doc)):
        if doc.get("version") != cfg["ontology_version"]:
            errors.append(f"{label} version={doc.get('version')} 与配置 {cfg['ontology_version']} 不一致")

    # 方向 ID 唯一
    ids = [d.get("direction_id") for d in directions]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    if dup:
        errors.append(f"direction_id 重复: {dup}")
    id_set = set(ids)

    dep_graph: dict[str, list[str]] = {}
    for i, d in enumerate(directions):
        tag = d.get("direction_id", f"#{i}")
        for msg in schema.validate_entity(d, "direction"):
            errors.append(f"[{tag}] {msg}")
        if d.get("status") not in statuses:
            errors.append(f"[{tag}] 非法 status={d.get('status')}")
        parents = d.get("parent_dimensions") or []
        if not parents:
            errors.append(f"[{tag}] parent_dimensions 为空")
        for p in parents:
            if p not in dims:
                errors.append(f"[{tag}] 引用无效一级维度 {p}")
        if len(set(parents)) != len(parents):
            errors.append(f"[{tag}] parent_dimensions 存在重复")
        for rel in d.get("related_directions") or []:
            if rel == tag:
                errors.append(f"[{tag}] related_directions 自引用")
            elif rel not in id_set:
                errors.append(f"[{tag}] related_directions 引用不存在的方向 {rel}")
        for fam in d.get("applicable_position_families") or []:
            if fam not in families:
                errors.append(f"[{tag}] applicable_position_families 引用未知岗位族 {fam}")
        dep = d.get("depends_on_direction_ids") or []
        for x in dep:
            if x == tag:
                errors.append(f"[{tag}] 依赖自身，形成环")
            elif x not in id_set:
                errors.append(f"[{tag}] 依赖不存在的方向 {x}")
        dep_graph[tag] = list(dep)

        # 定义字段完整性（内容级，不只是 Schema 类型）
        for f in ("definition", "direction_name"):
            if len(str(d.get(f, ""))) < 4:
                errors.append(f"[{tag}] {f} 定义过短")
        for f in ("inclusion_criteria", "exclusion_criteria", "evidence_types"):
            if not [x for x in (d.get(f) or []) if str(x).strip()]:
                errors.append(f"[{tag}] {f} 缺少有效内容")

        rv = d.get("review") or {}
        if d.get("status") == "approved":
            if rv.get("annotation_source") != "human" or not rv.get("reviewed"):
                errors.append(f"[{tag}] approved 方向必须由人工审核（human + reviewed=true）")
            if rv.get("annotation_status") != "approved":
                errors.append(f"[{tag}] approved 方向的 annotation_status 必须一致")
        elif d.get("status") == "candidate" and rv.get("annotation_status") == "approved":
            errors.append(f"[{tag}] candidate 方向不得带有 approved 审核状态（禁止自动批准）")

    cycles = _find_cycles(dep_graph)
    if cycles:
        errors.append(f"depends_on_direction_ids 存在循环依赖: {cycles[:5]}")

    # 岗位能力
    cids = [c.get("competency_id") for c in competencies]
    cdup = [k for k, v in Counter(cids).items() if v > 1]
    if cdup:
        errors.append(f"competency_id 重复: {cdup}")
    deprecated = {d["direction_id"] for d in directions if d.get("status") == "deprecated"}
    for i, c in enumerate(competencies):
        tag = c.get("competency_id", f"#{i}")
        for msg in schema.validate_entity(c, "competency"):
            errors.append(f"[{tag}] {msg}")
        if c.get("position_family") not in families:
            errors.append(f"[{tag}] 未知岗位族 {c.get('position_family')}")
        for did in c.get("related_direction_ids") or []:
            if did not in id_set:
                errors.append(f"[{tag}] 引用不存在的方向 {did}")
            elif did in deprecated:
                warnings.append(f"[{tag}] 引用了 deprecated 方向 {did}")
        if not (c.get("related_direction_ids") or []):
            warnings.append(f"[{tag}] 未关联任何追问方向")

    stats = {
        "direction_count": len(directions),
        "status_distribution": dict(sorted(Counter(d.get("status") for d in directions).items())),
        "approved_direction_count": sum(1 for d in directions if d.get("status") == "approved"),
        "multi_parent_direction_count": sum(1 for d in directions if len(d.get("parent_dimensions") or []) > 1),
        "max_parent_dimensions": max((len(d.get("parent_dimensions") or []) for d in directions), default=0),
        "parent_dimension_distribution": dict(sorted(Counter(
            p for d in directions for p in (d.get("parent_dimensions") or [])).items())),
        "related_direction_links": sum(len(d.get("related_directions") or []) for d in directions),
        "dependency_edges": sum(len(v) for v in dep_graph.values()),
        "dependency_cycles": len(cycles),
        "competency_count": len(competencies),
        "position_family_count": len({c.get("position_family") for c in competencies}),
        "competency_direction_links": sum(len(c.get("related_direction_ids") or []) for c in competencies),
        "directions_with_position_families": sum(
            1 for d in directions if d.get("applicable_position_families")),
    }

    return {
        "passed": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "statistics": stats,
        "generated_at": core.now_iso(),
    }
