#!/usr/bin/env python3
"""阶段七：全量数据质量校验（内容级，不只是 JSON 格式）。

硬性门槛（任一不过即该问题不合格）：
  experience_link_valid / reference_exact_match / no_generic_question /
  no_cross_experience_mix / chain_experience_consistent

用法：
  python3 scripts/validate_dataset.py [--stage auto|pilot|full] [--strict]
输出：
  dataset/metadata/validation_result.json
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import config, pipeline  # noqa: E402
from lib.common import all_position_kbs, log, months_between, read_jsonl, write_json  # noqa: E402
from lib.scoring import rules  # noqa: E402

GC = config.get_config("generation_config")
QD = config.get_config("quality_distribution")
DCFG = config.get_config("question_dimensions")
TCFG = config.get_config("question_types")
XCFG = config.get_config("experience_types")
VALID_DIMS = {d["key"] for d in DCFG["dimensions"]}
VALID_TYPES = {d["key"] for d in TCFG["question_types"]}
VALID_EXP_TYPES = set(XCFG["experience_types"])
LEVELS = GC["question_levels"]

RESUME_REQUIRED = ["resume_id", "candidate_id", "target_position", "career_level",
                   "total_work_years", "resume_quality", "basic_info", "education",
                   "work_experiences", "project_experiences", "internship_experiences",
                   "skills", "achievements", "certifications", "research_experiences",
                   "competitions", "resume_text", "quality_signals", "generation"]
EXP_REQUIRED = ["experience_id", "resume_id", "experience_type", "title", "organization",
                "start_date", "end_date", "original_content", "key_points",
                "skills_involved", "achievements", "potential_risks", "missing_information"]
Q_REQUIRED = ["question_id", "resume_id", "experience_id", "experience_type", "reference",
              "dimension", "question_type", "question", "reason", "expected_investigation",
              "priority", "difficulty", "follow_up_questions"]
CHAIN_REQUIRED = ["chain_id", "resume_id", "experience_id", "root_question_id",
                  "dimension", "chain_depth", "questions"]
GENERIC_BANNED = ["请介绍一下你在项目中的主要职责", "你在工作中遇到过什么困难",
                  "你认为自己的优势是什么", "请做一下自我介绍", "谈谈你的职业规划"]


class Report:
    def __init__(self) -> None:
        self.errors: Counter[str] = Counter()
        self.warnings: Counter[str] = Counter()
        self.samples: dict[str, list[str]] = defaultdict(list)

    def err(self, code: str, ident: str, detail: str = "") -> None:
        self.errors[code] += 1
        if len(self.samples[code]) < 5:
            self.samples[code].append(f"{ident}: {detail}"[:220])

    def warn(self, code: str, ident: str, detail: str = "") -> None:
        self.warnings[code] += 1
        if len(self.samples[code]) < 5:
            self.samples[code].append(f"{ident}: {detail}"[:220])

    def as_dict(self) -> dict[str, Any]:
        return {
            "errors": dict(self.errors),
            "error_samples": {k: v for k, v in self.samples.items() if k in self.errors},
            "warnings": dict(self.warnings),
            "warning_samples": {k: v for k, v in self.samples.items() if k in self.warnings},
            "error_total": sum(self.errors.values()),
            "warning_total": sum(self.warnings.values()),
        }


def _required(rep: Report, row: dict[str, Any], fields: list[str], tag: str) -> None:
    for f in fields:
        if f not in row or row[f] is None:
            rep.err("missing_required_field", tag, f"缺少 {f}")


def _kb_corpus(kb: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("core_responsibilities", "common_tasks", "core_skills", "tools",
                "business_scenarios", "achievement_metrics", "technical_difficulties",
                "work_risks", "probe_topics"):
        parts.extend(kb.get(key, []))
    for p in kb.get("project_types", []):
        parts.extend([p["name"], p["goal"], *p["tech_focus"],
                      *p["typical_metrics"], *p["difficulties"]])
    return " | ".join(parts)


def _exclusive_tokens(kbs: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    """只把「在其它岗位整个知识库文本中都不出现」的词视为岗位专属词，避免误报。"""
    corpora = {pid: _kb_corpus(kb) for pid, kb in kbs.items()}
    out: dict[str, set[str]] = defaultdict(set)
    for pid, kb in kbs.items():
        terms = set(kb["tools"]) | set(kb["core_skills"]) | set(kb["probe_topics"])
        for t in terms:
            if len(t) < 3:
                continue
            if all(t not in corpora[other] for other in kbs if other != pid):
                out[pid].add(t)
    return out


def validate(stage: str = "auto") -> dict[str, Any]:
    p = pipeline.paths()
    resumes = read_jsonl(p["resumes"])
    exps = read_jsonl(p["experiences"])
    qs = read_jsonl(p["questions"])
    chains = read_jsonl(p["chains"])
    rep = Report()

    if stage == "auto":
        stage = "full" if len(resumes) > GC["pilot_size"] else "pilot"
    kbs = all_position_kbs()
    exclusive = _exclusive_tokens(kbs)

    # ---------------------------------------------------------- 1. 基础完整性
    for name, rows, prefix in [("resume", resumes, "resume_id"),
                               ("experience", exps, "experience_id"),
                               ("question", qs, "question_id"),
                               ("chain", chains, "chain_id")]:
        ids = [r.get(prefix) for r in rows]
        dup = [k for k, v in Counter(ids).items() if v > 1]
        if dup:
            rep.err("duplicate_id", name, f"{len(dup)} 个重复 ID，示例 {dup[:3]}")
    for r in resumes:
        _required(rep, r, RESUME_REQUIRED, r.get("resume_id", "?"))
    for e in exps:
        _required(rep, e, EXP_REQUIRED, e.get("experience_id", "?"))
    for q in qs:
        _required(rep, q, Q_REQUIRED, q.get("question_id", "?"))
    for c in chains:
        _required(rep, c, CHAIN_REQUIRED, c.get("chain_id", "?"))

    r_by_id = {r["resume_id"]: r for r in resumes}
    e_by_id = {e["experience_id"]: e for e in exps}
    q_by_id = {q["question_id"]: q for q in qs}
    q_by_rid: dict[str, list[dict]] = defaultdict(list)
    e_by_rid: dict[str, list[dict]] = defaultdict(list)
    c_by_rid: dict[str, list[dict]] = defaultdict(list)
    for e in exps:
        e_by_rid[e["resume_id"]].append(e)
    for q in qs:
        q_by_rid[q["resume_id"]].append(q)
    for c in chains:
        c_by_rid[c["resume_id"]].append(c)

    # ---------------------------------------------------------- 2. 简历合理性
    for r in resumes:
        rid = r["resume_id"]
        for e in e_by_rid[rid]:
            if e["original_content"] not in r["resume_text"]:
                rep.err("original_not_traceable", rid, f"{e['experience_id']} 原文不在简历正文中")
            if e["experience_type"] not in VALID_EXP_TYPES:
                rep.err("invalid_experience_type", e["experience_id"], e["experience_type"])
        works = r["work_experiences"]
        if r["career_level"] == "fresh" and works:
            rep.err("fresh_has_formal_work", rid, f"应届毕业生存在 {len(works)} 段正式工作")
        if works:
            starts = [w["start_date"] for w in works]
            ends = [w["end_date"] for w in works]
            months = months_between(min(starts), max(ends))
            if abs(months / 12 - r["total_work_years"]) > 1.6:
                rep.err("timeline_mismatch", rid,
                        f"工作跨度 {months} 月 vs 声明 {r['total_work_years']} 年")
            ordered = sorted(zip(starts, ends))
            for i in range(len(ordered) - 1):
                if ordered[i + 1][0] <= ordered[i][1]:
                    if r["resume_quality"] != "contradictory":
                        rep.err("work_overlap", rid, f"{ordered[i]} 与 {ordered[i + 1]} 重叠")
                    elif not any(e["potential_risks"] for e in e_by_rid[rid]):
                        rep.warn("overlap_without_risk_note", rid, "疑点型重叠未标注核实点")
        for ed in r["education"]:
            if ed["start_date"] >= ed["end_date"]:
                rep.err("invalid_education_time", rid, f"{ed['start_date']} >= {ed['end_date']}")
        if not (18 <= r["basic_info"]["age"] <= 58):
            rep.err("implausible_age", rid, str(r["basic_info"]["age"]))
        kb = kbs.get(r["position_id"])
        if kb:
            pool = set(kb["core_skills"]) | set(kb["tools"])
            hit = sum(1 for s in r["skills"] if s["name"] in pool)
            if hit < 3:
                rep.err("position_skill_mismatch", rid, f"岗位技能命中 {hit} 项")
        sig = r["quality_signals"]
        q = r["resume_quality"]
        if q == "high" and (sig["vague_sentence_count"] > 2 or sig["quantified_ratio"] < 0.08):
            rep.warn("high_quality_signal_weak", rid, f"vague={sig['vague_sentence_count']} ratio={sig['quantified_ratio']}")
        if q == "vague" and sig["vague_sentence_count"] < 1:
            rep.warn("vague_quality_signal_weak", rid, "模糊句不足")
        if q == "contradictory" and sig["risk_statement_count"] < 1:
            rep.err("contradictory_no_risk", rid, "缺少需核实的事实句")

    # ---------------------------------------------------------- 3. 经历关联（最高优先级）
    hard_fail_qids: set[str] = set()
    for q in qs:
        qid = q["question_id"]
        ref = q.get("reference", {})
        quote = ref.get("original_text", "")
        exp = e_by_id.get(q["experience_id"])
        bad = False
        if exp is None:
            rep.err("experience_link_valid", qid, "experience_id 不存在")
            bad = True
        else:
            if exp["resume_id"] != q["resume_id"]:
                rep.err("experience_link_valid", qid, "问题与经历所属简历不一致")
                bad = True
            if q["experience_type"] != exp["experience_type"]:
                rep.err("experience_type_mismatch", qid,
                        f"{q['experience_type']} != {exp['experience_type']}")
                bad = True
            content = exp["original_content"]
            if not quote or quote not in content:
                rep.err("reference_exact_match", qid, "引用不是对应经历原文的精确子串")
                bad = True
            else:
                so, eo = ref.get("start_offset"), ref.get("end_offset")
                if so is None or eo is None:
                    rep.err("reference_offset_missing", qid, "可定位却未给出偏移量")
                    bad = True
                elif content[so:eo] != quote:
                    rep.err("reference_offset_wrong", qid, f"content[{so}:{eo}] != 引用")
                    bad = True
            if quote not in q["question"]:
                rep.err("no_generic_question", qid, "问题文本未包含精确原文引用")
                bad = True
            # 跨经历混合检查：只看问题里「引用之外」的新增文字，
            # 因为引用本身是本经历的证据，不应因与其它标题偶然同名而误判
            outside = q["question"].replace(quote, "")
            others = [e for e in e_by_rid[q["resume_id"]] if e["experience_id"] != q["experience_id"]]
            for o in others:
                if (len(o["title"]) >= 6 and o["title"] in outside
                        and o["title"] not in exp["title"] and exp["title"] not in o["title"]):
                    rep.err("no_cross_experience_mix", qid, f"混入其它经历标题 {o['title']}")
                    bad = True
                    break
                for kp in o["key_points"][:2]:
                    kp_clean = kp.rstrip("。；，")
                    if len(kp_clean) >= 18 and kp_clean in outside and kp_clean not in content:
                        rep.err("no_cross_experience_mix", qid, "混入其它经历原文片段")
                        bad = True
                        break
        for g in GENERIC_BANNED:
            if g in q["question"]:
                rep.err("no_generic_question", qid, "命中泛化问题模板")
                bad = True
        if q["dimension"] not in VALID_DIMS:
            rep.err("invalid_dimension", qid, q["dimension"])
            bad = True
        if q["question_type"] not in VALID_TYPES:
            rep.err("invalid_question_type", qid, q["question_type"])
            bad = True
        if not q["reason"] or len(q["reason"]) < 8:
            rep.err("missing_reason", qid, "")
            bad = True
        if not q["expected_investigation"]:
            rep.err("missing_expected_investigation", qid, "")
            bad = True
        text = q["question"]
        if len(text) < 20 or len(text) > 500:
            rep.err("unnatural_question_length", qid, str(len(text)))
            bad = True
        if re.search(r"[{}]|None|nan|TODO|placeholder|<[^>]+>", text):
            rep.err("unnatural_placeholder", qid, "问题含占位符或残留标记")
            bad = True
        # 岗位专业词泄漏
        own = r_by_id.get(q["resume_id"], {}).get("position_id")
        if own:
            for pid, toks in exclusive.items():
                if pid == own:
                    continue
                for t in toks:
                    if t and t in text and t not in kbs[own]["tools"] + kbs[own]["core_skills"]:
                        rep.warn("foreign_position_token", qid, f"{t} 属于 {pid}")
                        break
        if bad:
            hard_fail_qids.add(qid)

    # ---------------------------------------------------------- 4. 问题覆盖与多样性
    q_per = Counter(q["resume_id"] for q in qs)
    for rid in r_by_id:
        n = q_per[rid]
        if not (GC["questions_per_resume_min"] <= n <= GC["questions_per_resume_max"]):
            rep.err("question_count_out_of_range", rid, str(n))
        covered = {q["experience_id"] for q in q_by_rid[rid]}
        if len(covered) < GC["min_distinct_experiences_per_resume"]:
            rep.err("experience_coverage_insufficient", rid, f"仅覆盖 {len(covered)} 个经历")
        dims = {q["dimension"] for q in q_by_rid[rid]}
        if len(dims) < 4:
            rep.warn("dimension_variety_low", rid, f"仅 {len(dims)} 个主维度")
    dup_q = [t for t, n in Counter(q["question"] for q in qs).items() if n > 1]
    dup_ratio = len(dup_q) / max(1, len(qs))
    if dup_ratio > GC["quality_gate"]["max_duplicate_question_ratio"]:
        rep.err("duplicate_question_ratio", "dataset", f"{dup_ratio:.3f}")
    dup_resume = len(resumes) - len({r["resume_text"] for r in resumes})
    if dup_resume:
        rep.err("duplicate_resume_text", "dataset", f"{dup_resume} 份完全重复")

    def signature(q: dict[str, Any]) -> str:
        s = re.sub(r"「[^」]*」", "「…」", q["question"])
        s = re.sub(r"《[^》]*》", "《…》", s)
        s = re.sub(r"\d+", "N", s)
        return s
    sig_counts = Counter(signature(q) for q in qs)
    top_ratio = (max(sig_counts.values()) / len(qs)) if qs else 0
    if top_ratio > GC["quality_gate"]["max_template_concentration"]:
        rep.err("template_concentration", "dataset", f"最高模板占比 {top_ratio:.3f}")
    qtype_counts = Counter(q["question_type"] for q in qs)
    if qs and max(qtype_counts.values()) / len(qs) > 0.42:
        rep.warn("question_type_concentration", "dataset", dict(qtype_counts))
    dim_counts = Counter(q["dimension"] for q in qs)
    need_dims = 15 if stage == "full" else 10
    if len(dim_counts) < need_dims:
        rep.warn("dimension_coverage_low", "dataset", f"仅覆盖 {len(dim_counts)} 个维度")

    # ---------------------------------------------------------- 5. 追问链
    for c in chains:
        cid = c["chain_id"]
        root = q_by_id.get(c["root_question_id"])
        if root is None:
            rep.err("chain_root_missing", cid, "根问题不存在")
            continue
        if c["resume_id"] != root["resume_id"] or c["experience_id"] != root["experience_id"]:
            rep.err("chain_experience_consistent", cid, "追问链与根问题经历不一致")
        items = c["questions"]
        if c["chain_depth"] != len(items):
            rep.err("chain_depth_mismatch", cid, f"{c['chain_depth']} != {len(items)}")
        if not (GC["chain_depth_min"] <= len(items) <= GC["chain_depth_max"]):
            rep.err("chain_depth_out_of_range", cid, str(len(items)))
        levels = [x["level"] for x in items]
        if levels != LEVELS[:len(levels)]:
            rep.err("chain_progression_broken", cid, str(levels))
        if len({x["question"] for x in items}) != len(items):
            rep.err("chain_repeated_question", cid, "存在重复追问")
        quote = root["reference"]["original_text"]
        for it in items:
            if not it.get("purpose") or not it.get("expected_investigation") or not it.get("trigger_condition"):
                rep.err("chain_field_missing", cid, "追问缺少目的/预期信息/触发条件")
                break
            if quote not in it["question"]:
                rep.err("chain_experience_consistent", cid, f"第 {it['sequence']} 层未绑定同一原文")
                break
            if re.search(r"(候选人回答[:：]|答[:：]|我会回答|候选人说)", it["question"]):
                rep.err("chain_fabricated_answer", cid, "出现虚构候选人回答")
                break
        exp = e_by_id.get(c["experience_id"])
        if exp:
            for o in e_by_rid.get(c["resume_id"], []):
                if o["experience_id"] == c["experience_id"]:
                    continue
                if (len(o["title"]) >= 6 and o["title"] not in exp["title"]
                        and exp["title"] not in o["title"]
                        and any(o["title"] in it["question"].replace(quote, "") for it in items)):
                    rep.err("chain_experience_consistent", cid, "追问链跳到其它经历")
                    break
    for rid in r_by_id:
        if len(c_by_rid[rid]) < GC["chains_per_resume_min"]:
            rep.err("chain_count_insufficient", rid, f"{len(c_by_rid[rid])} 条")

    # ---------------------------------------------------------- 6. 规模与配额
    stats: dict[str, Any] = {
        "stage": stage,
        "resumes": len(resumes), "experiences": len(exps),
        "questions": len(qs), "chains": len(chains),
        "positions": dict(Counter(r["target_position"] for r in resumes)),
        "career_levels": dict(Counter(r["career_level"] for r in resumes)),
        "resume_qualities": dict(Counter(r["resume_quality"] for r in resumes)),
        "dimensions": dict(dim_counts),
        "question_types": dict(qtype_counts),
        "experience_types": dict(Counter(e["experience_type"] for e in exps)),
        "priority": dict(Counter(q["priority"] for q in qs)),
        "difficulty": dict(Counter(q["difficulty"] for q in qs)),
        "duplicate_question_ratio": round(dup_ratio, 5),
        "template_concentration": round(top_ratio, 5),
        "distinct_question_signatures": len(sig_counts),
        "hard_gate_failed_questions": len(hard_fail_qids),
        "avg_question_score": round(sum(q.get("quality_score", 0) for q in qs) / max(1, len(qs)), 2),
        "avg_resume_score": round(sum(r.get("quality_score", 0) for r in resumes) / max(1, len(resumes)), 2),
        "avg_experience_score": round(sum(e.get("quality_score", 0) for e in exps) / max(1, len(exps)), 2),
        "avg_chain_score": round(sum(c.get("quality_score", 0) for c in chains) / max(1, len(chains)), 2),
    }
    if stage == "pilot":
        if len(resumes) != GC["pilot_size"]:
            rep.warn("pilot_size", "dataset", f"试验样本 {len(resumes)} 份（目标 {GC['pilot_size']}）")
        if len(stats["positions"]) != 30:
            rep.err("pilot_position_coverage", "dataset", f"仅 {len(stats['positions'])} 个岗位")
        if len(stats["career_levels"]) != 5:
            rep.err("pilot_level_coverage", "dataset", f"仅 {len(stats['career_levels'])} 个年限档")
        if len(stats["resume_qualities"]) != 4:
            rep.err("pilot_quality_coverage", "dataset", f"仅 {len(stats['resume_qualities'])} 种质量型")
    else:
        if len(resumes) != GC["total_resumes"]:
            rep.err("total_resumes", "dataset", f"{len(resumes)} != {GC['total_resumes']}")
        exp_l = {x["key"]: x["count"] for x in QD["career_levels"]}
        exp_q = {x["key"]: x["count"] for x in QD["resume_qualities"]}
        if stats["career_levels"] != exp_l:
            rep.err("career_level_quota", "dataset", str(stats["career_levels"]))
        if stats["resume_qualities"] != exp_q:
            rep.err("quality_quota", "dataset", str(stats["resume_qualities"]))
        pos_counts = Counter(r["position_id"] for r in resumes)
        if len(pos_counts) != 30 or min(pos_counts.values()) < GC["min_resumes_per_position"]:
            rep.err("position_quota", "dataset", f"岗位数 {len(pos_counts)}，最少 {min(pos_counts.values())}")

    base = rep.as_dict()
    result = {"passed": base["error_total"] == 0, **base, "statistics": stats,
              "hard_gates": GC["quality_gate"]["hard_gates"],
              "scoring_rules": {"resume": rules()["resume_weights"],
                                "experience": rules()["experience_weights"],
                                "question": rules()["question_weights"],
                                "chain": rules()["chain_weights"]}}
    write_json(config.abspath("dataset/metadata/validation_result.json"), result, indent=2)
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="auto", choices=["auto", "pilot", "full"])
    ap.add_argument("--strict", action="store_true", help="存在错误时以非零状态退出")
    args = ap.parse_args()
    r = validate(args.stage)
    s = r["statistics"]
    log(f"校验完成 [{s['stage']}]：通过={r['passed']} 错误={r['error_total']} 警告={r['warning_total']}")
    log(f"规模：简历 {s['resumes']} / 经历 {s['experiences']} / 问题 {s['questions']} / 追问链 {s['chains']}")
    log(f"硬性门槛未过问题数：{s['hard_gate_failed_questions']}；"
        f"问题重复率 {s['duplicate_question_ratio']}；模板集中度 {s['template_concentration']}")
    if r["errors"]:
        for code, n in sorted(r["errors"].items(), key=lambda x: -x[1])[:12]:
            log(f"  错误 {code} x{n} | 示例：{r['error_samples'].get(code, [''])[0][:120]}")
    if r["warnings"]:
        for code, n in sorted(r["warnings"].items(), key=lambda x: -x[1])[:8]:
            log(f"  警告 {code} x{n}")
    if args.strict and not r["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
