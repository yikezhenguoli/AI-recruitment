"""简历生成器：事实句原子化 + 岗位知识库驱动 + 四种质量型 + 五年限档。

内部产生的每个事实句都携带 fact_type 等元数据，用于后续经历拆解与经历级问题生成。
所有姓名/学校/公司均为算法合成的虚构实体。
"""
from __future__ import annotations

import random
from typing import Any

from . import config
from .common import (jitter_numbers, load_banks, load_position_kb, months_between,
                     pick, sample, strip_tail_punct, ym_add, ym_str, ym_tuple)
from .scoring import score_experience, score_resume

FACT_TYPES = {
    "education_background", "course_project", "research_method", "research_result",
    "responsibility", "tech_stack", "tech_implementation", "optimization", "metric",
    "problem_solved", "decision", "collaboration", "leadership", "delivery",
    "achievement", "skill_application", "project_background", "competition_role",
    "competition_result", "learning", "vague_statement", "risk_statement", "reflection",
}


class Builder:
    def __init__(self, slot: dict[str, Any]):
        self.slot = slot
        self.rng = random.Random(slot["item_seed"])
        self.kb = load_position_kb(slot["position_id"])
        self.banks = load_banks()
        self.qp = config.get_config("quality_distribution")["quality_profiles"][slot["resume_quality"]]
        self.gc = config.get_config("generation_config")
        self.ridx = int(slot["resume_id"].split("_")[1])
        self._seen_sentences: set[str] = set()
        self._exp_seq = 0
        self.experiences: list[dict[str, Any]] = []
        self.asof_y, self.asof_m = ym_tuple(self.gc["as_of_date"])

    # ------------------------------------------------------------ 基础工具
    def r(self) -> random.Random:
        return self.rng

    def choice(self, seq: list[Any], default: Any = "") -> Any:
        return pick(self.rng, seq, default)

    def sample(self, seq: list[Any], n: int) -> list[Any]:
        return sample(self.rng, seq, n)

    def company(self) -> str:
        return self.choice(self.banks["company_prefix"]) + self.choice(self.banks["company_suffix"])

    def school(self) -> str:
        return self.choice(self.banks["school_prefix"]) + self.choice(self.banks["school_suffix"])

    def metric(self, from_project: dict[str, Any] | None = None) -> str:
        pool = list(self.kb["achievement_metrics"])
        if from_project:
            pool = pool + list(from_project["typical_metrics"])
        return jitter_numbers(self.choice(pool), self.rng)

    def fact(self, text: str, ftype: str, **kw: Any) -> dict[str, Any]:
        text = text.strip()
        if not text.endswith(("。", "；", "！")):
            text += "。"
        d = {"text": text, "fact_type": ftype}
        d.update(kw)
        return d

    def vague_fact(self) -> dict[str, Any]:
        a = self.choice(self.banks["vague_phrases"])
        b = self.choice(self.banks["vague_result_phrases"])
        text = a + ("，" + b if self.rng.random() < 0.55 else "")
        return self.fact(text, "vague_statement")

    def maybe_vague(self, normal_text: str, ftype: str, **kw: Any) -> dict[str, Any]:
        if self.rng.random() < self.qp["vague_sentence_prob"]:
            return self.vague_fact()
        if self.rng.random() > self.qp["personal_boundary_clarity"]:
            normal_text = normal_text.replace("独立负责", "参与并配合团队完成", 1)
        return self.fact(normal_text, ftype, **kw)

    def topic(self) -> str:
        return self.choice(self.kb["probe_topics"], "关键技术细节")

    def difficulty(self, proj: dict[str, Any] | None = None) -> str:
        pool = list(self.kb["technical_difficulties"])
        if proj:
            pool += list(proj["difficulties"])
        return self.choice(pool)

    def tool(self) -> str:
        return self.choice(self.kb["tools"])

    def skill(self) -> str:
        return self.choice(self.kb["core_skills"])

    def task(self) -> str:
        return self.choice(self.kb["common_tasks"])

    def task_phrase(self) -> str:
        """把知识库中的动宾式任务转成名词性短语，避免『完成使用 X 做 Y』这类病句。"""
        t = self.task()
        for p in ("使用 ", "基于 ", "通过 ", "编写 ", "执行 ", "组织 ", "完成 ", "设计 ",
                  "配置 ", "实现 ", "开展 ", "跟进 ", "维护 ", "输出 ", "拆解 ", "建立 ",
                  "推进 ", "搭建 ", "对接 ", "梳理 ", "制定 ", "跟踪 ", "分析 "):
            if t.startswith(p):
                return t[len(p):]
        return t

    def is_tech(self) -> bool:
        return self.slot["family"] in ("软件研发", "算法与数据", "质量与运维", "硬件与制造")

    def delivery_sentence(self) -> str:
        if self.is_tech():
            return "按迭代节奏完成发布与回滚预案，交付后持续跟进监控指标。"
        return "按节点完成交付与复核，形成过程记录并同步相关方。"

    def collaboration_sentence(self) -> str:
        team = self.choice(self.banks["team_names"])
        if self.is_tech():
            return f"与{team}协同完成联调与验收，明确交付节点与接口约定。"
        return f"与{team}协同推进事项落地，明确分工、口径与交付节点。"

    def scene(self) -> str:
        return self.choice(self.kb["business_scenarios"])

    def sub_window(self, start: str, end: str) -> tuple[str, str]:
        """在一段工作经历内部取一个合理的子区间作为项目周期。"""
        sy, sm = ym_tuple(start)
        total = max(1, months_between(start, end))
        span = min(total, self.rng.randint(4, 14))
        offset = self.rng.randint(0, max(0, total - span))
        s = ym_add(sy, sm, offset)
        e = ym_add(sy, sm, offset + span - 1)
        return ym_str(*s), ym_str(*e)

    # ------------------------------------------------------------ 经历单元
    def add_experience(self, etype: str, title: str, org: str, start: str, end: str,
                       facts: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
        # 去重事实句，保证 original_content 不出现重复语句
        uniq: list[dict[str, Any]] = []
        for f in facts:
            key = f["text"]
            if not key or key in self._seen_sentences:
                continue
            self._seen_sentences.add(key)
            uniq.append(f)
        if not uniq:
            uniq = [self.fact(f"参与{title}相关工作并配合团队推进。", "vague_statement")]
        self._exp_seq += 1
        eid = f"EXP_{self.ridx:06d}{self._exp_seq:02d}"
        content = "".join(f["text"] for f in uniq)
        skills = []
        for f in uniq:
            for k in ("skill", "tool"):
                if f.get(k) and f[k] not in skills:
                    skills.append(f[k])
        for s in self.sample(self.kb["core_skills"], 2):
            if s not in skills:
                skills.append(s)
        achievements = [strip_tail_punct(f["text"]) for f in uniq
                        if f["fact_type"] in ("metric", "optimization", "achievement",
                                              "research_result", "competition_result")
                        or f.get("metric")]
        missing: list[str] = []
        types = {f["fact_type"] for f in uniq}
        if "vague_statement" in types:
            missing.append("未说明本人独立承担的具体工作与个人/团队边界")
        if types & {"metric", "optimization", "achievement", "research_result"}:
            missing.append("未说明指标的测量方法、数据来源与对比基准")
        if "tech_stack" in types:
            missing.append("未说明技术选型依据与考虑过的替代方案")
        if "tech_implementation" in types:
            missing.append("未说明异常处理方式与边界条件")
        if "decision" in types:
            missing.append("未说明方案权衡过程与评估标准")
        if "collaboration" in types or "leadership" in types:
            missing.append("未说明跨团队协作中的职责划分")
        if "risk_statement" in types:
            missing.append("存在时间线或统计口径需要进一步核实的信息")
        if not missing:
            missing.append("未说明该经历中个人贡献与团队贡献的具体划分")
        missing = list(dict.fromkeys(missing))[:4]
        risks = self.sample(self.kb["work_risks"], 1 if self.slot["resume_quality"] != "contradictory" else 2)
        for f in uniq:
            if f.get("risk_note"):
                risks.append(f["risk_note"])
        risks = list(dict.fromkeys(risks))

        exp = {
            "experience_id": eid,
            "resume_id": self.slot["resume_id"],
            "experience_type": etype,
            "title": title,
            "organization": org,
            "start_date": start,
            "end_date": end,
            "original_content": content,
            "key_points": [strip_tail_punct(f["text"]) for f in uniq[:4]],
            "skills_involved": skills[:8],
            "achievements": achievements[:4],
            "potential_risks": risks,
            "missing_information": missing,
            "fact_count": len(uniq),
            "position_id": self.slot["position_id"],
            "career_level": self.slot["career_level"],
            "_facts": uniq,
        }
        if extra:
            exp.update(extra)
        exp["quality_score"] = score_experience(exp)
        self.experiences.append(exp)
        return exp

    # ------------------------------------------------------------ 事实句构造
    def education_facts(self, degree: str, school: str, major: str) -> list[dict[str, Any]]:
        rng = self.rng
        courses = self.banks["courses_by_family"].get(self.slot["family"], self.banks["courses_by_family"]["软件研发"])
        c1, c2, c3 = self.sample(courses, 3)
        proj = self.choice(self.kb["project_types"])
        facts = [self.fact(f"就读于{school}{major}{degree}，核心课程包括{c1}、{c2}与{c3}。",
                           "education_background", skill=c1)]
        if degree in ("硕士", "博士") or rng.random() < 0.45:
            facts.append(self.fact(f"围绕{self.difficulty()}开展专题研究，负责{self.task_phrase()}与资料整理。",
                                   "research_method", skill=self.skill()))
        facts.append(self.maybe_vague(
            f"毕业设计围绕《{proj['name']}》展开，{proj['goal']}，使用{proj['tech_focus'][0]}完成实现。",
            "course_project", skill=proj["tech_focus"][0], tool=self.tool()))
        if rng.random() < 0.6:
            facts.append(self.fact(f"通过{c1}课程掌握{self.skill()}的基础原理，并在课程项目中完成验证。",
                                   "learning", skill=c1))
        return facts

    def project_facts(self, proj: dict[str, Any], is_course: bool = False) -> list[dict[str, Any]]:
        rng = self.rng
        qp = self.qp
        tech = proj["tech_focus"]
        tool_pool = [t for t in self.kb["tools"] if t not in tech]
        t0, t1 = (self.sample(tool_pool, 2) + ["—", "—"])[:2]
        diff = self.difficulty(proj)
        diff2 = self.choice(proj["difficulties"], diff)
        facts: list[dict[str, Any]] = []
        facts.append(self.fact(f"项目面向{self.scene()}场景，目标是{proj['goal']}。", "project_background"))
        facts.append(self.maybe_vague(
            f"本人独立负责{tech[0]}相关模块的设计与实现，并承担{tech[1]}的联调验证。",
            "responsibility", skill=tech[0], tool=t0))
        facts.append(self.fact(f"技术方案以{tech[0]}、{tech[1]}与{t0}为主，重点处理{diff}。",
                               "tech_stack", skill=tech[1], tool=t0))
        if rng.random() < qp["tech_detail_prob"]:
            facts.append(self.fact(f"实现过程中针对{diff}，结合{self.task_phrase()}完成处理并补充异常分支。",
                                   "tech_implementation", skill=tech[0], tool=t0, difficulty=diff))
        if rng.random() < qp["tech_detail_prob"] * 0.75:
            facts.append(self.fact(f"方案选型阶段比较了{t0}与{t1}的适用性，最终选择{tech[0]}以兼顾{diff2}。",
                                   "decision", skill=tech[0], tool=t0))
        metric = jitter_numbers(self.choice(proj["typical_metrics"]), rng)
        if rng.random() < qp["metric_prob"]:
            facts.append(self.fact(f"项目交付后{metric}，相关指标在验收阶段复核确认。",
                                   "metric", metric=metric, tool=t0))
        elif rng.random() < 0.4:
            facts.append(self.fact(f"项目按计划完成交付，整体运行平稳。", "delivery"))
        if rng.random() < 0.55:
            facts.append(self.fact(f"推进过程中出现由{diff2}引发的异常，通过分步排查定位根因后完成修复，并补充验证记录。",
                                   "problem_solved", skill=tech[1], difficulty=diff2))
        if rng.random() < 0.35:
            facts.append(self.fact(f"复盘后调整了{tech[1]}的处理顺序，并在后续迭代中沿用。", "reflection"))
        if is_course and rng.random() < 0.5:
            facts.append(self.fact(f"该课题由{rng.randint(3, 5)}人小组完成，本人负责方案设计与结果汇报。",
                                   "collaboration"))
        return facts

    def work_facts(self, role: str, org: str) -> list[dict[str, Any]]:
        rng = self.rng
        qp = self.qp
        scene = self.scene()
        t0, t1 = (self.sample(self.kb["tools"], 2) + ["-", "-"])[:2]
        diff = self.difficulty()
        facts = [self.maybe_vague(
            f"担任{role}，独立负责{self.choice(self.kb['core_responsibilities'])}，主要面向{scene}场景。",
            "responsibility", skill=self.skill(), tool=t0)]
        if rng.random() < qp["tech_detail_prob"]:
            facts.append(self.fact(f"日常使用{t0}、{t1}完成{self.task_phrase()}，并维护相关配置与文档。",
                                   "tech_stack", skill=t0, tool=t0))
        if rng.random() < qp["tech_detail_prob"]:
            facts.append(self.fact(f"针对{diff}，结合{self.task_phrase()}完成处理并补充异常分支。",
                                   "tech_implementation", skill=self.skill(), tool=t1, difficulty=diff))
        if rng.random() < qp["metric_prob"]:
            m = self.metric()
            facts.append(self.fact(f"通过专项优化，{m}。", "optimization", metric=m, tool=t0))
        if self.slot["career_level"] in ("senior", "expert"):
            facts.append(self.fact(f"带领{rng.randint(3, 12)}人小组完成排期与方案评审，并协调{self.choice(self.banks['team_names'])}推进交付。",
                                   "leadership", skill=self.skill()))
        else:
            facts.append(self.fact(self.collaboration_sentence(), "collaboration"))
        if rng.random() < 0.7:
            facts.append(self.fact(self.delivery_sentence(), "delivery"))
        return facts

    def internship_facts(self, org: str) -> list[dict[str, Any]]:
        rng = self.rng
        intern_role = self.choice(self.banks["role_titles"]["fresh"])
        facts = [self.maybe_vague(
            f"在{org}担任{intern_role}，参与{self.task()}，熟悉{self.scene()}业务流程。",
            "responsibility", skill=self.skill())]
        facts.append(self.fact(f"协助整理业务数据与过程文档，跟进{self.choice(self.banks['team_names'])}的日常对接。",
                               "learning", skill=self.skill()))
        if rng.random() < self.qp["tech_detail_prob"]:
            facts.append(self.fact(f"在导师指导下使用{self.tool()}完成{self.task()}，并学习{self.skill()}的实际应用。",
                                   "skill_application", skill=self.skill(), tool=self.tool()))
        if rng.random() < self.qp["metric_prob"] * 0.5:
            facts.append(self.fact(f"实习期间参与的优化使{self.metric()}。", "metric"))
        return facts

    def research_facts(self, topic: str) -> list[dict[str, Any]]:
        rng = self.rng
        facts = [
            self.fact(f"参与《{topic}》课题，负责{self.task_phrase()}与过程记录。", "research_method",
                      skill=self.skill()),
            self.fact(f"使用{self.tool()}完成{self.task_phrase()}，形成阶段性分析报告。", "tech_implementation",
                      skill=self.skill(), tool=self.tool()),
        ]
        if rng.random() < self.qp["metric_prob"]:
            facts.append(self.fact(f"课题结果显示{self.metric()}，结论在组内汇报中通过复核。",
                                   "research_result"))
        if rng.random() < 0.6:
            facts.append(self.fact(f"研究局限主要在于样本范围与{self.difficulty()}，后续计划扩大验证。", "reflection"))
        return facts

    def competition_facts(self, comp: str) -> list[dict[str, Any]]:
        rng = self.rng
        award = self.choice(self.banks["awards"])
        facts = [
            self.fact(f"参加{comp}，团队{rng.randint(3, 5)}人，本人负责方案设计，并承担{self.skill()}相关工作。",
                      "competition_role", skill=self.skill()),
            self.fact(f"使用{self.tool()}完成{self.task_phrase()}，并在决赛环节负责成果演示。",
                      "tech_implementation", tool=self.tool()),
            self.fact(f"最终获得{award}，评审反馈集中在{self.difficulty()}的处理上。",
                      "competition_result"),
        ]
        return facts

    def achievement_facts(self, org: str) -> list[dict[str, Any]]:
        rng = self.rng
        m = self.metric()
        honor = self.choice(self.banks["honor_titles"])
        return [
            self.fact(f"在{org}任职期间主导的专项工作实现{m}，获评{honor}。", "achievement", metric=m),
            self.fact(f"该成果由{self.choice(self.banks['team_names'])}共同确认，并纳入部门年度复盘。",
                      "collaboration"),
            self.fact(f"复盘后把相关做法整理为内部规范，在后续{self.scene()}场景中沿用。", "reflection"),
        ]

    def skill_application_facts(self, org: str) -> list[dict[str, Any]]:
        t0, t1 = (self.sample(self.kb["tools"], 2) + ["-", "-"])[:2]
        if self.is_tech():
            decision = f"比较{t0}与{t1}在{self.scene()}场景下的边界，明确适用条件与降级方案。"
            detail = f"针对{self.difficulty()}补充异常处理与监控口径。"
        else:
            decision = f"比较{t0}与{t1}在{self.scene()}场景下的适用边界，明确判断标准与审批路径。"
            detail = f"针对{self.difficulty()}补充复核环节与例外情形的处理规则。"
        return [
            self.fact(f"在{org}推动{self.skill()}的规范化应用，围绕{self.difficulty()}形成内部实践指引。",
                      "skill_application", skill=self.skill(), tool=t0),
            self.fact(decision, "decision", tool=t0),
            self.fact(detail, "tech_implementation",
                      skill=self.skill(), tool=t1, difficulty=self.difficulty()),
        ]

    # ------------------------------------------------------------ 疑点注入
    def risk_fact(self) -> dict[str, Any]:
        rng = self.rng
        patterns = self.banks["risk_patterns"]
        kind = self.choice(list(patterns.keys()))
        m = self.metric()
        if kind == "time_overlap":
            text = "该阶段同时参与另一并行项目，两段工作在时间上存在部分重叠，具体投入安排需要进一步核实。"
        elif kind == "metric_without_baseline":
            text = f"在较短周期内实现{m}，简历中未附对比基准与测试条件说明。"
        elif kind == "scope_mismatch":
            text = f"独立负责{self.skill()}相关模块的整体交付，团队同期共有{rng.randint(6, 15)}人参与该模块。"
        elif kind == "tech_result_mismatch":
            ta, tb = (self.sample(self.kb["tools"], 2) + ["-", "-"])[:2]
            text = f"采用{ta}实现核心模块，而交付验收材料中的技术栈记录为{tb}。"
        elif kind == "role_level_mismatch":
            text = f"以{self.choice(self.banks['role_titles']['fresh'])}身份主导{m}的达成。"
        else:
            text = f"阶段性成果为{m}，其中部分数据指标缺少计算方式与来源说明。"
        f = self.fact(text, "risk_statement", metric=m if m in text else "")
        f["risk_note"] = patterns[kind]
        return f

    # ------------------------------------------------------------ 主流程
    def build(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rng = self.rng
        slot = self.slot
        level = slot["career_level"]
        Y = slot["total_work_years"]
        quality = slot["resume_quality"]

        # ---- 身份（全部为合成虚构实体）
        name = self.choice(self.banks["surnames"]) + self.choice(self.banks["given_chars_1"])
        if rng.random() < 0.72:
            name += self.choice(self.banks["given_chars_2"])
        city = self.choice(self.banks["cities"])
        school = self.school()
        major = self.choice(self.banks["majors_by_family"].get(slot["family"], self.banks["majors"]))
        companies = list(dict.fromkeys(self.company() for _ in range(5)))[:4]
        while len(companies) < 4:
            companies.append(self.company())
        intern_org = self.company()

        # ---- 时间线
        if Y == 0:
            grad_y, grad_m = self.asof_y, 6
            work_segments: list[tuple[str, str, str]] = []
        else:
            ws_y, ws_m = ym_add(self.asof_y, self.asof_m, -Y * 12)
            grad_y = ws_y if ws_m >= 7 else ws_y - 1
            grad_m = 6
            k = 1 if Y <= 3 else (2 if Y <= 8 else 3)
            cuts = sorted(rng.sample(range(8, Y * 12 - 4), k - 1)) if k > 1 else []
            bounds = [0] + cuts + [Y * 12]
            overlap = rng.randint(2, 4) if quality == "contradictory" else 0
            work_segments = []
            for i in range(k):
                s = ym_add(ws_y, ws_m, bounds[i] - (overlap if i > 0 else 0))
                e = ym_str(self.asof_y, self.asof_m) if i == k - 1 else ym_add(ws_y, ws_m, bounds[i + 1] - 1)
                work_segments.append((ym_str(*s) if isinstance(s, tuple) else s,
                                      e if isinstance(e, str) else ym_str(*e),
                                      companies[i % len(companies)]))

        degree_pool = ["本科"] * 6 + ["硕士"] * (4 if level in ("fresh", "mid", "senior", "expert") else 2)
        if slot["family"] in ("算法与数据",) and level in ("expert", "senior"):
            degree_pool += ["博士"]
        degree = self.choice(degree_pool)
        if degree == "本科":
            edu_start, edu_end = f"{grad_y - 4}-09", f"{grad_y}-06"
        else:
            edu_start, edu_end = f"{grad_y - 3}-09", f"{grad_y}-06"
        age = 22 + (self.asof_y - grad_y) + (2 if degree in ("硕士", "博士") else 0) + rng.randint(-1, 1)

        # ---- 教育经历（1~2 个单元）
        self.add_experience("education", f"{major}（{degree}）", school, edu_start, edu_end,
                            self.education_facts(degree, school, major))
        if degree != "本科" and rng.random() < 0.55:
            school2 = self.school()
            self.add_experience("education", f"{self.choice(self.banks['majors_by_family'].get(slot['family'], self.banks['majors']))}（本科）", school2,
                                f"{grad_y - 7}-09", f"{grad_y - 3}-06",
                                [self.fact(f"本科阶段就读于{school2}，"
                                           f"主修{self.choice(self.banks['courses_by_family'].get(slot['family'], ['数据结构与算法']))}等课程。",
                                           "education_background"),
                                 self.fact(f"参与课程实践，完成{self.task_phrase()}相关训练。", "learning")])

        # ---- 正式工作经历
        role = self.choice(self.banks["role_titles"][level])
        work_exps = []
        for i, (s, e, org) in enumerate(work_segments):
            title = f"{role}（{self.scene()}方向）" if i == len(work_segments) - 1 else f"{role}（第{i + 1}阶段）"
            facts = self.work_facts(role, org)
            work_exps.append(self.add_experience("work_experience", title, org, s, e, facts))

        # ---- 项目经历（2~3 个）
        n_proj = rng.randint(2, 3)
        projs = self.sample(self.kb["project_types"], n_proj)
        for i, p in enumerate(projs):
            if Y == 0:
                suffix = self.choice(["（课程设计）", "（毕业设计）", "（课程项目）", "（校内实践）"])
                s, e = f"{grad_y - 1}-09", f"{grad_y}-05"
                org = school
                is_course = True
            else:
                suffix = self.choice(["", "（二期）", "专项", "（深化）"])
                ws = work_segments[min(i, len(work_segments) - 1)]
                s, e = self.sub_window(ws[0], ws[1])
                org = ws[2]
                is_course = False
            title = p["name"] + suffix
            self.add_experience("project_experience", title, org, s, e,
                                self.project_facts(p, is_course))

        # ---- 实习 / 科研 / 竞赛
        if Y == 0:
            self.add_experience("internship", f"{slot['target_position']}实习", intern_org,
                                f"{grad_y - 1}-07", f"{grad_y - 1}-12", self.internship_facts(intern_org))
            if rng.random() < 0.55:
                org2 = self.company()
                self.add_experience("internship", "业务实践实习", org2,
                                    f"{grad_y - 2}-07", f"{grad_y - 2}-09",
                                    self.internship_facts(org2))
        else:
            if level in ("junior", "mid") and rng.random() < 0.45:
                self.add_experience("internship", "毕业前实习", intern_org,
                                    f"{grad_y - 1}-07", f"{grad_y - 1}-12",
                                    self.internship_facts(intern_org))

        if rng.random() < (0.75 if Y == 0 else 0.35):
            research_title = f"{self.difficulty()}专题研究"
            self.add_experience("research", research_title, school,
                                f"{grad_y - 2}-03", f"{grad_y}-04", self.research_facts(research_title))
        if rng.random() < (0.7 if Y == 0 else 0.28):
            comp = self.choice(self.banks["competitions"])
            self.add_experience("competition", comp,
                                "校级赛事组委会", f"{grad_y - 2}-04", f"{grad_y - 2}-06",
                                self.competition_facts(comp))

        # ---- 成果 / 技能应用（中高阶）
        if level in ("senior", "expert") and work_exps:
            org = work_segments[-1][2]
            self.add_experience("achievement", "年度专项成果", org,
                                work_segments[-1][0], work_segments[-1][1],
                                self.achievement_facts(org))
        if level in ("mid", "senior", "expert") and work_exps:
            org = work_segments[-1][2]
            self.add_experience("skill_application", f"{self.skill()}专项建设", org,
                                work_segments[-1][0], work_segments[-1][1],
                                self.skill_application_facts(org))

        # ---- 疑点型：注入需核实的事实句（不标记为造假）
        if quality == "contradictory":
            candidates = [e for e in self.experiences if e["experience_type"] in ("work_experience", "project_experience")]
            target = self.choice(candidates)
            rf = self.risk_fact()
            if rf["text"] not in self._seen_sentences:
                self._seen_sentences.add(rf["text"])
                target["_facts"].append(rf)
                target["original_content"] += rf["text"]
                target["fact_count"] += 1
                target["key_points"].append(strip_tail_punct(rf["text"]))
                target["potential_risks"].append(rf["risk_note"])
                target["potential_risks"] = list(dict.fromkeys(target["potential_risks"]))
                target["missing_information"] = list(dict.fromkeys(
                    target["missing_information"] + ["存在时间线或统计口径需要进一步核实的信息"]))[:4]
                target["quality_score"] = score_experience(target)

        # ---- 简历结构化字段
        def section(etype: str, extra_key: str | None = None) -> list[dict[str, Any]]:
            out = []
            for e in self.experiences:
                if e["experience_type"] != etype:
                    continue
                d = {"experience_id": e["experience_id"], "title": e["title"],
                     "organization": e["organization"], "start_date": e["start_date"],
                     "end_date": e["end_date"], "original_content": e["original_content"]}
                if extra_key:
                    d[extra_key] = e.get(extra_key, [])
                out.append(d)
            return out

        skills = []
        for s in self.sample(self.kb["core_skills"], 5):
            skills.append({"name": s, "level": self.choice(["熟练", "掌握", "精通"]),
                           "application": f"应用于{self.scene()}场景"})
        for t in self.sample(self.kb["tools"], 3):
            skills.append({"name": t, "level": self.choice(["熟练", "掌握"]),
                           "application": f"在{self.choice(self.kb['project_types'])['name']}中使用"})
        achievements = []
        for e in self.experiences:
            for a in e["achievements"][:1]:
                achievements.append({"description": a, "related_experience_id": e["experience_id"]})
        certs = self.sample(self.banks["certifications_by_family"].get(slot["family"], ["岗位相关培训证书"]),
                            rng.randint(0, 2))

        vague_count = sum(1 for e in self.experiences for f in e["_facts"] if f["fact_type"] == "vague_statement")
        metric_count = sum(1 for e in self.experiences for f in e["_facts"]
                           if f["fact_type"] in ("metric", "optimization", "achievement", "research_result"))
        risk_count = sum(1 for e in self.experiences for f in e["_facts"] if f["fact_type"] == "risk_statement")
        total_facts = sum(e["fact_count"] for e in self.experiences)

        resume = {
            "resume_id": slot["resume_id"],
            "candidate_id": slot["candidate_id"],
            "target_position": slot["target_position"],
            "position_id": slot["position_id"],
            "family": slot["family"],
            "career_level": slot["career_level"],
            "career_level_label": slot["career_level_label"],
            "total_work_years": Y,
            "resume_quality": slot["resume_quality"],
            "resume_quality_label": slot["resume_quality_label"],
            "basic_info": {
                "name": name, "age": age, "city": city,
                "phone": f"138****{self.ridx % 10000:04d}",
                "email": f"candidate_{self.ridx:06d}@example.test",
                "is_fictional": True,
            },
            "education": section("education"),
            "work_experiences": section("work_experience"),
            "project_experiences": section("project_experience"),
            "internship_experiences": section("internship"),
            "skills": skills,
            "achievements": achievements,
            "certifications": [{"name": c} for c in certs],
            "research_experiences": section("research"),
            "competitions": section("competition"),
            "achievement_experiences": section("achievement"),
            "skill_application_experiences": section("skill_application"),
            "quality_signals": {
                "vague_sentence_count": vague_count,
                "metric_count": metric_count,
                "risk_statement_count": risk_count,
                "total_fact_count": total_facts,
                "quantified_ratio": round(metric_count / max(1, total_facts), 3),
            },
            "generation": {
                "seed": slot["item_seed"], "batch_id": slot["batch_id"],
                "as_of_date": self.gc["as_of_date"], "generator_version": "1.0.0",
                "source": "local_rule_based",
            },
        }
        resume["resume_text"] = self.render(resume)
        resume["quality_score"] = score_resume(resume, self.experiences)
        return resume, self.experiences

    # ------------------------------------------------------------ 简历文本
    def render(self, resume: dict[str, Any]) -> str:
        b = resume["basic_info"]
        lines = [
            f"姓名：{b['name']}　年龄：{b['age']}　城市：{b['city']}　联系方式：{b['phone']} / {b['email']}（虚构信息）",
            f"求职意向：{resume['target_position']}　工作年限：{resume['career_level_label']}　简历类型：{resume['resume_quality_label']}",
            "",
            "【教育背景】",
        ]
        groups = [
            ("教育背景", "education"),
            ("工作经历", "work_experiences"),
            ("项目经历", "project_experiences"),
            ("实习经历", "internship_experiences"),
            ("科研经历", "research_experiences"),
            ("竞赛经历", "competitions"),
            ("专项成果", "achievement_experiences"),
            ("专项能力建设", "skill_application_experiences"),
        ]
        for label, key in groups:
            if label != "教育背景":
                lines += ["", f"【{label}】"]
            items = resume[key]
            if not items:
                lines.append("（无）")
            for it in items:
                lines.append(f"{it['start_date']} ~ {it['end_date']}　{it['title']}　{it['organization']}")
                lines.append(it["original_content"])
        lines += ["", "【专业技能】"]
        lines.append("；".join(f"{s['name']}（{s['level']}，{s['application']}）" for s in resume["skills"]))
        if resume["achievements"]:
            lines += ["", "【工作成果】"]
            lines += [f"- {a['description']}" for a in resume["achievements"]]
        if resume["certifications"]:
            lines += ["", "【证书】"]
            lines.append("、".join(c["name"] for c in resume["certifications"]))
        return "\n".join(lines)


def build_one(slot: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return Builder(slot).build()
