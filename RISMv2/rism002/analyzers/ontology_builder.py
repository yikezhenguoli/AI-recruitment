"""从历史候选方向构建 RISM-002 初始本体（可复现、不自动批准）。

- investigation_directions.json：全部 status=candidate，来源 historical_question
- position_competencies.json：8 个岗位族的能力，与方向多对多关联
- 能力关联依据「能力域 → 历史问题类型」的显式映射，不依赖岗位名称文本相似度
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..utils import core

# 能力域 -> 相关历史问题类型（显式映射，非文本相似度）
DOMAIN_QTYPES: dict[str, set[str]] = {
    "technical_implementation": {"technical_deep_dive", "clarification"},
    "verification_and_metrics": {"data_verification", "result_verification"},
    "decision_and_design": {"decision_analysis", "technical_deep_dive", "scenario_analysis"},
    "problem_diagnosis": {"problem_investigation", "risk_investigation"},
    "contribution_and_collaboration": {"contribution_verification", "clarification"},
    "planning_and_business": {"decision_analysis", "scenario_analysis"},
    "risk_and_evidence": {"risk_investigation", "data_verification"},
    "reflection_and_improvement": {"reflection", "scenario_analysis"},
}

# 8 个岗位族 -> 3 个能力域（id, 中文名, 定义, 重要度）
FAMILY_COMPETENCIES: dict[str, list[tuple[str, str, str, str]]] = {
    "software_development": [
        ("impl_detail", "技术实现与实现细节掌控", "能够说明具体实现路径、关键参数与异常处理，并解释实现背后的原理与边界。", "high"),
        ("design_decision", "技术方案决策与权衡", "能够说明方案选择依据、替代方案比较与技术取舍，而非仅描述结果。", "high"),
        ("problem_diagnosis", "问题定位与排查", "能够还原问题现象、排查路径、根因判断与验证方式。", "medium"),
    ],
    "algorithm_and_data": [
        ("metric_evidence", "指标口径与数据证据", "能够说明指标定义、数据来源、统计口径、对比基准与观察周期。", "high"),
        ("method_principle", "方法原理与实验设计", "能够解释方法原理、变量控制、实验设计与结论适用边界。", "high"),
        ("result_attribution", "结果归因与可复现性", "能够区分个人贡献与团队贡献，说明结果的可复现条件与局限。", "medium"),
    ],
    "product_and_project": [
        ("business_context", "业务背景与优先级判断", "能够说明业务问题触发背景、相关方诉求与优先级判断依据。", "high"),
        ("planning_control", "排期与里程碑管理", "能够说明任务分解、依赖关系、里程碑设置与风险预案。", "high"),
        ("acceptance_validation", "验收标准与成果核实", "能够说明业务验收标准、成果核对方式与数据来源。", "medium"),
    ],
    "quality_and_operations": [
        ("verification_process", "验证过程与排查路径", "能够说明测试/验证设计、问题现象、排查路径与排除依据。", "high"),
        ("risk_handling", "风险识别与处置", "能够说明风险信号、影响面、预案与资源协调方式。", "high"),
        ("evidence_trace", "证据链与口径一致性", "能够提供可核对的过程记录，说明统计口径与信息一致性。", "medium"),
    ],
    "design": [
        ("design_rationale", "设计决策依据", "能够说明设计取舍、用户场景约束与替代方案比较。", "high"),
        ("user_evidence", "用户研究与验证证据", "能够说明研究方法、样本范围、结论依据与验证方式。", "high"),
        ("iteration_reflection", "迭代复盘与改进", "能够说明识别到的不足、具体改进动作与改进效果验证。", "medium"),
    ],
    "corporate_functions": [
        ("process_compliance", "流程与口径合规", "能够说明流程依据、审批权限、口径一致性与可核对记录。", "high"),
        ("data_attribution", "数据归责与口径", "能够说明数据来源、计算公式、对比基准与个人/团队职责边界。", "high"),
        ("stakeholder_coordination", "相关方协同与优先级", "能够说明相关方诉求、沟通路径与优先级判断。", "medium"),
    ],
    "marketing_and_sales": [
        ("result_evidence", "业绩证据与归因", "能够说明业绩口径、数据来源、对比基准与归因隔离方法。", "high"),
        ("business_judgement", "业务判断与决策依据", "能够说明市场判断、方案选择依据与预期/实际差异。", "high"),
        ("customer_collaboration", "客户协同与过程还原", "能够还原客户沟通、推进过程与个人实际贡献。", "medium"),
    ],
    "hardware_and_manufacturing": [
        ("engineering_detail", "工程实现与参数依据", "能够说明具体实现步骤、关键工具与参数、完成确认方式。", "high"),
        ("verification_baseline", "测试验证与对比基准", "能够说明测试环境、对比基准、测量方法与结果验证。", "high"),
        ("failure_analysis", "异常分析与改进", "能够说明异常现象、根因定位、处理过程与后续改进。", "medium"),
    ],
}

# 能力 id -> 能力域
COMPETENCY_DOMAIN: dict[str, str] = {
    "impl_detail": "technical_implementation",
    "design_decision": "decision_and_design",
    "problem_diagnosis": "problem_diagnosis",
    "metric_evidence": "verification_and_metrics",
    "method_principle": "decision_and_design",
    "result_attribution": "contribution_and_collaboration",
    "business_context": "planning_and_business",
    "planning_control": "planning_and_business",
    "acceptance_validation": "verification_and_metrics",
    "verification_process": "verification_and_metrics",
    "risk_handling": "risk_and_evidence",
    "evidence_trace": "verification_and_metrics",
    "design_rationale": "decision_and_design",
    "user_evidence": "verification_and_metrics",
    "iteration_reflection": "reflection_and_improvement",
    "process_compliance": "planning_and_business",
    "data_attribution": "verification_and_metrics",
    "stakeholder_coordination": "contribution_and_collaboration",
    "result_evidence": "verification_and_metrics",
    "business_judgement": "planning_and_business",
    "customer_collaboration": "contribution_and_collaboration",
    "engineering_detail": "technical_implementation",
    "verification_baseline": "verification_and_metrics",
    "failure_analysis": "problem_diagnosis",
}


def _qtype_of(direction: dict[str, Any]) -> str:
    sig = direction.get("origin", {}).get("signature", "")
    return sig.split("::")[0] if "::" in sig else ""


def build_competencies(cfg: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    by_domain: dict[str, list[str]] = defaultdict(list)
    for c in candidates:
        qt = _qtype_of(c)
        for domain, qtypes in DOMAIN_QTYPES.items():
            if qt in qtypes:
                by_domain[domain].append(c["direction_id"])
    records = []
    for family, items in FAMILY_COMPETENCIES.items():
        for cid, name, definition, importance in items:
            domain = COMPETENCY_DOMAIN[cid]
            dids = sorted(set(by_domain.get(domain, [])))
            records.append({
                "position_family": family,
                "competency_id": f"{family}__{cid}",
                "competency_name": name,
                "competency_definition": definition,
                "importance": importance,
                "related_direction_ids": dids,
                "competency_domain": domain,
                "version": cfg["ontology_version"],
                "review": core.review_block(source="rule_based", status="pending",
                                            review_reason="岗位能力由能力域映射初建，待人工审核",
                                            cfg=cfg),
            })
    return {
        "version": cfg["ontology_version"],
        "generated_at": core.now_iso(),
        "note": "岗位能力与追问方向为多对多关系；关联依据是显式能力域映射，不是岗位名称文本相似度。",
        "position_family_count": len(FAMILY_COMPETENCIES),
        "competency_count": len(records),
        "competencies": records,
    }


def build_directions(cfg: dict[str, Any], candidates: list[dict[str, Any]],
                     competencies: dict[str, Any]) -> dict[str, Any]:
    # 由岗位能力反填方向适用的岗位族
    family_by_direction: dict[str, set[str]] = defaultdict(set)
    for rec in competencies["competencies"]:
        for did in rec["related_direction_ids"]:
            family_by_direction[did].add(rec["position_family"])

    # 关联方向：共享一级维度最多的其它方向（仅语义关联，不合并、不构成依赖）
    by_dim: dict[str, set[str]] = defaultdict(set)
    for c in candidates:
        for d in c["parent_dimensions"]:
            by_dim[d].add(c["direction_id"])

    out = []
    for c in candidates:
        score: dict[str, int] = defaultdict(int)
        for d in c["parent_dimensions"]:
            for other in by_dim[d]:
                if other != c["direction_id"]:
                    score[other] += 1
        related = [k for k, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
        rec = dict(c)
        rec["related_directions"] = related
        rec["depends_on_direction_ids"] = []
        rec["applicable_position_families"] = sorted(family_by_direction.get(c["direction_id"], set()))
        rec["review"] = core.review_block(
            source="historical_question", status="pending",
            review_reason="历史问题仅为方向发现依据，需人工审核后方可批准", cfg=cfg)
        rec["status"] = "candidate"
        out.append(rec)

    return {
        "version": cfg["ontology_version"],
        "generated_at": core.now_iso(),
        "note": "初始方向目录全部为 candidate，未经人工审核不得标记为 approved；方向 ID 稳定唯一，不因中文名称调整而变更。",
        "status_counts": {"candidate": len(out), "approved": 0, "deprecated": 0},
        "multi_parent_direction_count": sum(1 for d in out if len(d["parent_dimensions"]) > 1),
        "directions": out,
    }


def build_all(cfg: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = cfg or core.load_config()
    candidates, errors = core.read_jsonl(core.out_path("candidate_directions", cfg))
    if errors:
        raise ValueError(f"候选方向文件存在解析错误: {errors[:3]}")
    competencies = build_competencies(cfg, candidates)
    directions = build_directions(cfg, candidates, competencies)
    core.write_json(core.out_path("competencies", cfg), competencies)
    core.write_json(core.out_path("directions", cfg), directions)
    return directions, competencies
