#!/usr/bin/env python3
"""生成 500 份全合成简历（300 训练 / 100 验证 / 100 测试）。

数据来源只有 `jd/jobs_24.yaml`：岗位名、职责、技能、学历、年限都是模板素材，
姓名/公司/学校/联系方式全部虚构，邮箱统一 example.com、电话统一 138-0000-xxxx，
文末标注「本简历为合成数据」。不读取、不混合任何真人简历。

用法：
  python generate_synthetic.py --out synth
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from pathlib import Path

import yaml

try:  # 直接 `python scripts/generate_synthetic.py` 运行时走第一支
    import lexicon
except ImportError:  # 作为包导入时
    from scripts import lexicon

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JD = ROOT / "jd" / "jobs_24.yaml"
TOTAL = 500
TARGETS = (300, 100, 100)

SURNAMES = ("李王张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾"
            "萧田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦")
GIVEN = ("伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀霞平刚文华晨子涵雨桐浩然嘉怡"
         "思远若彤宇航欣怡明轩佳琪俊杰婉清志强慧敏思琪一鸣若曦")
COMPANIES = ("云帆科技", "星海数据", "北辰智造", "青岚咨询", "恒远物流", "明诚软件",
             "光华传媒", "瑞丰商贸", "海拓电子", "长风能源", "安泰医疗", "知行教育",
             "新元金融", "德润建筑", "锦程汽车", "绿源环保", "启明信息", "嘉禾食品")
SCHOOLS = ("云岭大学", "青川理工学院", "北辰职业技术大学", "东江学院", "南屏大学")
DEGREES = ("大专", "本科", "硕士", "博士")
NOISE_SKILLS = ("Excel", "Python", "SQL", "项目管理", "英语六级", "数据分析",
                "沟通协调", "团队管理", "PPT", "公文写作")

NOTE = "备注：本简历为合成数据，仅用于算法评测。"

# v3：以 2026.06 为时间锚点（月序号 = year*12 + month-1）
ANCHOR_MONTH = 2026 * 12 + 5

# v3 的通用段落：真实简历里大量出现，与具体职业无关
V3_CITIES = ["杭州", "苏州", "成都", "武汉", "南京", "宁波", "合肥", "郑州",
             "长沙", "西安", "青岛", "厦门"]
V3_SUMMARY = [
    "性格稳重，做事有条理，能按计划推进手头工作。",
    "遇到问题会主动同步进度，习惯先确认再动手。",
    "愿意学习新工具和新流程，能较快适应岗位变化。",
    "能和同事配合，服从排班安排，能承担一定压力。",
    "执行力和时间观念较强，能够按时交付。",
    "做事有始有终，离职交接时会把资料整理清楚。",
    "平时注意积累工作方法，会把常见问题记成笔记。",
    "对重复性工作能沉住气，能在稳定中把细节做扎实。",
    "希望找一份长期稳定的工作，愿意从基础做起。",
    "接受公司安排的培训和轮岗，愿意学习新的业务流程。",
]
V3_OUTCOME = [
    "任职期间按时完成各项任务，未出现重大差错。",
    "任职期间配合团队完成年度目标，考核结果为良好。",
    "任职期间主动补位，得到部门同事的认可。",
    "任职期间按要求完成交接，资料留存完整。",
    "任职期间持续改进工作方法，效率有所提升。",
    "任职期间没有收到有效投诉，服务评价保持稳定。",
]
V3_STRENGTH = [
    "做事认真，能按流程完成交接。",
    "遇到突发情况先上报，再协助处理。",
    "能和同事配合，接受排班和临时加班。",
    "对数据和时间节点比较敏感。",
    "能承担重复性工作，稳定性较好。",
    "有较强的学习意愿，能快速上手新系统。",
    "做事不拖沓，当天的事情尽量当天完成。",
]
V3_CERT = [
    "证书：CET-4、计算机二级。",
    "证书：普通话二级甲等、机动车驾驶证 C1。",
    "培训：参加过办公软件应用与信息安全基础培训。",
    "培训：参加过内部新人带教与流程规范培训。",
    "证书：CET-6。",
    "培训：参加过消防安全与应急疏散演练。",
    "培训：参加过服务礼仪与客户接待培训。",
    "证书：办公软件操作证书（选考）。",
]
V3_LANGUAGE = [
    "语言能力：普通话流利，能用英语进行日常读写。",
    "语言能力：普通话标准，英语可作为工作语言。",
    "语言能力：普通话流利，能阅读英文资料。",
]
V3_AWARD = [
    "获奖情况：年度优秀员工（部门内部评选）。",
    "获奖情况：所在团队获得季度先进集体。",
    "获奖情况：参加过公司技能比武，获得参与奖。",
    "获奖情况：在校期间获得过奖学金。",
]
V3_ACTIVITY = [
    "社会活动：参加过社区志愿服务和公益捐步活动。",
    "社会活动：曾在学校社团负责活动组织和物资登记。",
    "社会活动：参加过行业协会的公开讲座和交流会。",
]
V3_EXTRA = [
    "工作习惯：每天上班先列待办清单，下班前检查完成情况。",
    "工作习惯：重要事项会留书面记录，方便同事接手。",
    "工作习惯：遇到不确定的问题先请教，再按统一口径执行。",
    "工作习惯：交接前会把手头资料按项目分类整理好。",
]


def split_terms(text: str) -> list[str]:
    """把 JD 的技能句拆成短语：去掉「XX技能：」前缀，再按顿号/逗号切。"""
    if not text:
        return []
    body = text.split("：", 1)[-1]
    # 括号里常是工具名的并列列表，直接把括号当分隔符，避免切出「CAD（Adobe」这种半截词
    body = re.sub(r"[（(【\[]", "、", body)
    body = re.sub(r"[）)】\]]", "、", body)
    terms = re.split(r"[、，,；;]", body)
    cleaned = (term.strip(" 。.") for term in terms)
    return [term for term in cleaned if len(term) >= 2]


def skills_of(job: dict) -> list[str]:
    terms: list[str] = []
    for item in job.get("required_skills_zh") or []:
        terms.extend(split_terms(item))
    seen: list[str] = []
    for term in terms:
        if term not in seen:
            seen.append(term)
    return seen


def fmt_month(index: int) -> str:
    """月序号（year*12 + month-1）→ YYYY.MM。"""
    return f"{index // 12:04d}.{index % 12 + 1:02d}"


def pick_years(spec: str, rng: random.Random) -> int:
    numbers = [int(n) for n in re.findall(r"\d+", spec or "")]
    if not numbers:
        return rng.randint(2, 6)
    low = numbers[0]
    high = numbers[-1] if len(numbers) > 1 else low + 4
    return max(1, rng.randint(low, max(low, high)))


def education_line(job: dict) -> str:
    text = str(job.get("education_zh") or "本科")
    for degree in ("博士", "硕士", "本科", "大专"):
        if degree in text:
            return degree
    return "本科"


TASK_PHRASES = ("项目交付", "日常运营", "季度目标", "客户需求", "流程优化", "质量检查")


def describe(job: dict, rng: random.Random, count: int, hard: bool = False) -> list[str]:
    if hard:
        # 不逐字复用 JD 职责句，只用技能短语改写，降低词面泄漏
        skills = skills_of(job)
        lines = []
        for _ in range(count):
            verb = rng.choice(("负责", "参与", "主导", "协助"))
            task = rng.choice(TASK_PHRASES)
            if skills:
                picks = rng.sample(skills, k=min(2, len(skills)))
                lines.append(f"- {verb}{'、'.join(picks)}相关的{task}，按计划完成记录与复盘。")
            else:
                lines.append(f"- {verb}{task}，按计划完成记录与复盘。")
        return lines
    responsibilities = job.get("responsibilities_zh") or []
    if not responsibilities:
        responsibilities = [f"负责{job.get('title_zh', '本岗位')}相关工作。"]
    picked = rng.sample(responsibilities, k=min(count, len(responsibilities)))
    lines = []
    for item in picked:
        item = item.rstrip("。")
        lines.append(f"- {rng.choice(('负责', '参与', '主导', '协助'))}{item}。")
    return lines


def build_resume(job: dict, all_jobs: list[dict], rng: random.Random, index: int,
                 hard: bool = False) -> dict:
    title = job["title_zh"]
    skills = skills_of(job)
    years = pick_years(str(job.get("experience_years") or ""), rng)
    variant = rng.choices(
        ["standard", "short", "career_switch", "senior"],
        weights=[55, 15, 15, 15])[0]
    if variant == "senior":
        years = max(years, rng.randint(8, 12))
    if variant == "short":
        years = min(years, 2)

    degree = education_line(job)
    school = rng.choice(SCHOOLS)
    major = rng.choice(("工商管理", "信息管理与信息系统", "市场营销", "汉语言文学",
                        "经济学", "计算机科学与技术", "机械工程", "设计学", "法学"))
    study_years = {"大专": 3, "本科": 4, "硕士": 3, "博士": 5}[degree]
    grad_month = (2026 - years) * 12 + 5
    study_start = grad_month - study_years * 12

    header = [
        f"姓名：{rng.choice(SURNAMES)}{rng.choice(GIVEN)}",
        f"电话：138-0000-{index % 10000:04d}",
        f"邮箱：user{index:04d}@example.com",
        f"工作经验：{years} 年",
        f"教育背景：{school} {major} {degree}（{fmt_month(study_start)}-{fmt_month(grad_month)}）",
    ]
    intent = rng.random()
    other = rng.choice([j for j in all_jobs if j["code"] != job["code"]])
    if hard:
        if intent < 0.15:
            header.insert(3, f"求职意向：{title}")
        elif intent < 0.35:
            header.insert(3, f"求职意向：{rng.choice(('互联网', '制造业', '金融', '服务业'))}相关岗位")
    elif intent < 0.70:
        header.insert(3, f"求职意向：{title}")
    elif intent < 0.85:
        related = rng.choice((f"{title}助理", f"高级{title}", f"{title}专员"))
        header.insert(3, f"求职意向：{related}")

    jobs: list[list[str]] = []
    job_count = 1 if variant == "short" else (3 if variant == "senior" else rng.randint(2, 3))
    total_months = max(years * 12, job_count * 6)
    per_job = total_months // job_count
    cursor = grad_month
    for slot in range(job_count):
        # career_switch 的第一段经历故意放在别的职业里，制造真实的转行文本
        source = other if (variant == "career_switch" and slot == 0) else job
        company = rng.choice(COMPANIES)
        if hard:
            role = rng.choice(("业务专员", "高级专员", "项目主管", "分析师", "顾问",
                               "团队负责人", "运营专员"))
        else:
            role = source["title_zh"] if slot == 0 else rng.choice(
                (title, f"高级{title}", f"{title}专员"))
        span_start = cursor
        span_end = grad_month + total_months if slot == job_count - 1 else cursor + per_job
        cursor = span_end
        lines = [f"{company} | {role} | {fmt_month(span_start)}-{fmt_month(span_end)}"]
        lines += describe(source, rng, 3 if variant == "senior" else 2, hard=hard)
        jobs.append(lines)

    project_lines = [f"项目：{rng.choice(COMPANIES)}{rng.choice(('数字化', '流程优化', '客户增长', '成本管控'))}项目"]
    project_lines += describe(job, rng, 2, hard=hard)

    if hard and skills:
        share = rng.uniform(0.40, 0.75)
        count = max(2, int(len(skills) * share))
        core = rng.sample(skills, k=min(len(skills), count))
    else:
        core = rng.sample(skills, k=min(len(skills), rng.randint(3, 6))) if skills else []
    noise = rng.sample(NOISE_SKILLS, k=rng.randint(0 if not hard else 1, 3 if hard else 2))
    if hard:
        other_skills = skills_of(other)
        if other_skills:
            noise += rng.sample(other_skills, k=min(2, len(other_skills)))
    skill_line = "技能特长：" + "、".join(core + noise) + "。"

    if hard:
        focus = f"熟悉{rng.choice(core)}，" if core and rng.random() < 0.6 else ""
        summary = (f"自我评价：具备{years}年相关工作经验，{focus}"
                   f"{rng.choice(('责任心强', '表达清楚', '注重细节', '抗压能力好'))}。")
    else:
        summary = (f"自我评价：{years} 年{title}相关经验，"
                   f"{rng.choice(('熟悉', '熟练掌握', '能够独立完成'))}"
                   f"{rng.choice(core) if core else '本岗位核心工作'}，"
                   f"{rng.choice(('责任心强', '表达清楚', '注重细节', '抗压能力好'))}。")

    lines = header + ["工作经历："]
    for block in jobs:
        lines.extend(block)
    lines += ["项目经历："] + project_lines
    lines += [skill_line, summary, NOTE]
    return {"ID": f"SYN{index:04d}", "Resume_str": "\n".join(lines),
            "Category": job["code"], "variant": variant, "source": "synthetic"}


# --------------------------------------------------------------------- v3 生成
def _pick(items: list[str], rng: random.Random) -> str:
    return rng.choice(items)


def _generic(prof: dict, key: str, rng: random.Random) -> str:
    """25% 的槽位用与职业无关的通用词，稀释领域密度（真实简历也大量是通用事务）。"""
    if rng.random() < 0.25:
        return _pick(lexicon.GENERIC_OBJECTS if key == "objects" else
                     lexicon.GENERIC_ACTIONS if key == "actions" else
                     lexicon.GENERIC_SCENES if key == "scenes" else
                     lexicon.GENERIC_QUALITY, rng)
    return _pick(prof[key], rng)


def _bullet(prof: dict, rng: random.Random, shared: str | None = None) -> str:
    """独立撰写的一条职责，不复用 JD 句子。

    shared 非空时只引入一个「相邻职业共享的名词」，动作仍用本职业的，
    避免把简历写成另一份职业的工作经历。
    """
    if shared is not None:
        act = _pick(prof["actions"], rng)
        partner = _pick(lexicon.PARTNERS, rng)
        cycle = _pick(lexicon.CYCLES, rng)
        verb = _pick(lexicon.VERBS, rng)
        return rng.choice([
            f"{verb}{act}，{cycle}整理{shared}相关记录。",
            f"配合{partner}对接{shared}方面的事项，参与{act}。",
            f"参与{shared}的协调工作，承担{act}，发现问题及时反馈。",
        ])
    partner = _pick(lexicon.PARTNERS, rng)
    cycle = _pick(lexicon.CYCLES, rng)
    verb = _pick(lexicon.VERBS, rng)
    # 领域句与通用句分开组合，避免「用炒锅整理学生」这类语义错配
    if rng.random() < 0.45:
        return rng.choice([
            f"{verb}部门日常事务，{cycle}更新工作台账，保持信息可追溯。",
            f"协助{partner}整理资料，按{cycle}汇总一次情况，重要事项单独标注。",
            f"参加例会并记录要点，跟进待办事项，完成后及时反馈。",
            f"负责文件归档与交接记录，保证{_pick(lexicon.GENERIC_QUALITY, rng)}，方便同事查找。",
            f"配合{partner}对接需求，及时反馈进度，遇到分歧先确认再执行。",
            f"按流程完成日常审批和登记，定期检查遗漏项并补齐。",
            f"按要求填写日报和交接班记录，异常情况当天说明。",
            f"协助整理会议材料，会后跟进责任人确认的时间节点。",
        ])
    act = _pick(prof["actions"], rng)
    obj = _pick(prof["objects"], rng)
    tool = _pick(prof["tools"], rng)
    scene = _pick(prof["scenes"], rng)
    qual = _pick(prof["quality"], rng)
    return rng.choice([
        f"{verb}{act}，{cycle}更新{obj}相关记录，并按节点向{partner}同步进展，保证{qual}。",
        f"使用{tool}完成{act}，对结果逐项登记；发现异常时先记录再上报，不擅自处理。",
        f"结合{scene}的要求，参与{act}，配合{partner}处理{obj}方面的问题，保证{qual}。",
        f"协助{partner}完成{act}，提前核对{obj}，发现差异先确认，保证{qual}。",
        f"负责{obj}的日常跟进，遇到异常及时向{partner}反馈，并留下处理记录。",
        f"按{cycle}核对{obj}相关信息，用{tool}复核相关记录，差异逐条说明并跟踪闭环。",
        f"参与{scene}相关工作，{cycle}汇总一次{obj}情况，形成简要记录备查。",
        f"{act}，并将过程整理成工作台账，标注关键节点，方便后续交接。",
    ])


def _skills(prof: dict, rng: random.Random, other: dict | None = None) -> list[str]:
    n = rng.randint(4, 8)
    n_common = max(1, round(n * prof["common_ratio"]))
    n_domain = max(1, n - n_common)
    picked = list(rng.sample(lexicon.COMMON_POOL, n_common))
    picked += list(rng.sample(prof["tools"], min(n_domain, len(prof["tools"]))))
    if other is not None and rng.random() < 0.85:
        picked.append(rng.choice(other["tools"]))
    seen: list[str] = []
    for item in picked:
        if item not in seen:
            seen.append(item)
    return seen


def _partition_months(total: int, n: int, rng: random.Random,
                      switch_first: bool = False) -> list[int]:
    """把 total 个月拆成 n 段正数，第一段在转行时给得更长一些。"""
    minimum = 4
    total = max(total, n * minimum)
    weights = [rng.uniform(0.6, 1.4) for _ in range(n)]
    if switch_first and n > 1:
        weights[0] *= 1.8
    rem = total - n * minimum
    scale = sum(weights)
    alloc = [minimum + int(rem * w / scale) for w in weights]
    alloc[-1] += total - sum(alloc)
    return alloc


def _v3_education(job: dict, prof: dict, rng: random.Random,
                  grad_month: int, degree: str) -> tuple[str, int]:
    school = rng.choice(SCHOOLS)
    major = rng.choice(prof["majors"])
    study_years = {"大专": 3, "本科": 4, "硕士": 3, "博士": 5}[degree]
    study_start = grad_month - study_years * 12
    line = (f"教育背景：{school} {major} {degree}"
            f"（{fmt_month(study_start)}-{fmt_month(grad_month)}）")
    return line, study_start


def build_resume_v3(job: dict, all_jobs: list[dict], rng: random.Random,
                    index: int) -> dict:
    """v3：正文完全由独立语汇集生成，不由目标 JD 派生。"""
    code = job["code"]
    prof = dict(lexicon.LEXICON[code])
    title = job["title_zh"]
    bridges = lexicon.BRIDGE.get(code) or []
    if bridges and rng.random() < 0.80:
        prof["objects"] = list(prof["objects"]) + rng.sample(bridges, k=min(len(bridges), 2))
    bridge_scenes = lexicon.BRIDGE_SCENE.get(code) or []
    if bridge_scenes and rng.random() < 0.85:
        prof["scenes"] = list(prof["scenes"]) + rng.sample(bridge_scenes, k=min(len(bridge_scenes), 3))

    variant = rng.choices(["standard", "short", "career_switch", "senior"],
                          weights=[40, 15, 30, 15])[0]
    years = pick_years(str(job.get("experience_years") or ""), rng)
    if variant == "senior":
        years = max(years, rng.randint(8, 12))
    if variant == "short":
        years = min(years, 2)
    if variant == "career_switch":
        # 转行至少要能容纳两段经历，且目标职业那段不能缺席
        years = max(years, rng.randint(3, 6))

    degree = education_line(job)
    grad_month = ANCHOR_MONTH - years * 12
    edu_line, _ = _v3_education(job, prof, rng, grad_month, degree)

    # 转行：第一段经历放在别的职业组，制造真实的跨职业文本
    switch = variant == "career_switch"
    other = None
    if switch:
        own_group = lexicon.CODE_GROUP[code]
        pool = [j for j in all_jobs if j["code"] != code and
                lexicon.CODE_GROUP.get(j["code"]) != own_group]
        other = rng.choice(pool)

    job_count = 1 if variant == "short" else (3 if variant == "senior"
                                              else rng.randint(2, 3))
    job_count = min(job_count, max(1, years))  # 年限太少时不要硬塞多段
    total_months = years * 12
    spans = _partition_months(total_months, job_count, rng, switch_first=switch)

    blocks: list[list[str]] = []
    cursor = grad_month
    for slot, length in enumerate(spans):
        source = other if (switch and slot == 0) else None
        source_prof = lexicon.LEXICON[source["code"]] if source else prof
        company = rng.choice(COMPANIES)
        role = rng.choice(lexicon.GENERIC_ROLES)
        span_start, span_end = cursor, cursor + length
        cursor = span_end
        lines = [f"{company} | {role} | {fmt_month(span_start)}-{fmt_month(span_end)}"]
        bullet_count = (8 if variant == "senior" else
                        4 if variant == "short" else
                        6 if variant == "career_switch" else rng.randint(6, 7))
        for k in range(bullet_count):
            if source is not None:
                lines.append("- " + _bullet(source_prof, rng))
            elif k == 0:
                # 每份简历的目标职业至少有一条自身领域职责，保证标签有正文支撑
                lines.append("- " + _bullet(prof, rng))
            elif rng.random() < 0.12 and prof["adjacent"]:
                group = lexicon.CODE_GROUP[code]
                shared = rng.choice(lexicon.GROUP_SHARED.get(group, ["协作"]))
                lines.append("- " + _bullet(prof, rng, shared=shared))
            else:
                lines.append("- " + _bullet(prof, rng))
        lines.append("- " + rng.choice(V3_OUTCOME))
        # 同一段经历里去掉重复表述
        deduped = []
        for line in lines:
            if line not in deduped:
                deduped.append(line)
        blocks.append(deduped)

    # 项目经历：领域密度略高，仍然独立措辞
    project_lines = [f"项目：{rng.choice(COMPANIES)}"
                     f"{rng.choice(('流程优化', '能力建设', '服务提升', '降本增效', '系统改造'))}项目"]
    for idx in range(3):
        if idx == 2 and rng.random() < 0.6:
            project_lines.append("- " + rng.choice([
                f"整理项目过程资料，按{_pick(lexicon.CYCLES, rng)}更新一次进度。",
                f"配合{_pick(lexicon.PARTNERS, rng)}完成验收与交接，问题逐项闭环。",
            ]))
            continue
        act = _pick(prof["actions"], rng)
        obj = _pick(prof["objects"], rng)
        tool = _pick(prof["tools"], rng)
        qual = _pick(prof["quality"], rng)
        project_lines.append("- " + rng.choice([
            f"承担{act}，用{tool}处理{obj}相关环节，交付前逐项核对。",
            f"围绕{obj}配合完成{act}，与{_pick(lexicon.PARTNERS, rng)}确认口径，确保{qual}。",
            f"负责项目中{obj}的跟进，按{_pick(lexicon.CYCLES, rng)}汇报进展。",
        ]))

    picked = _skills(prof, rng, other=lexicon.LEXICON[other["code"]] if other else None)
    own_skill_text = " ".join(str(x) for x in job.get("required_skills_zh") or [])
    if "Excel" not in own_skill_text and rng.random() < 0.55:
        picked.append("Excel 表格处理")
    if "PPT" not in own_skill_text and rng.random() < 0.50:
        picked.append("PPT 汇报材料")
    skill_line = "技能特长：" + "、".join(picked) + "。"

    trait = rng.choice(("做事踏实", "做事细致", "为人耐心", "责任感强",
                        "学习能力强", "表达清楚"))
    summary = (f"自我评价：{years} 年工作经验，{trait}，"
               f"能适应{_pick(prof['scenes'], rng)}的工作节奏，"
               f"希望长期在{prof['industry']}方向发展。")

    # 个人总结 / 核心优势 / 证书与培训：通用内容，增加真实简历的体量与噪音
    personal = rng.sample(V3_SUMMARY, k=4)
    strengths = rng.sample(V3_STRENGTH, k=5)
    if "保密" not in own_skill_text and rng.random() < 0.65:
        strengths.append("注意资料保密，不对外传播内部信息。")
    certs = rng.sample(V3_CERT, k=4)
    languages = [rng.choice(V3_LANGUAGE)]
    awards = rng.sample(V3_AWARD, k=2)
    activities = rng.sample(V3_ACTIVITY, k=2)
    extras = rng.sample(V3_EXTRA, k=2)
    other_info = [f"可到岗时间：{rng.choice(('一个月内', '两周内', '随时'))}。",
                  f"期望工作地点：{rng.choice(V3_CITIES)}。",
                  f"兴趣爱好：{rng.choice(('跑步、阅读', '羽毛球、摄影', '骑行、烹饪', '音乐、旅行'))}。"]

    header = [
        f"姓名：{rng.choice(SURNAMES)}{rng.choice(GIVEN)}",
        f"电话：138-0000-{index % 10000:04d}",
        f"邮箱：user{index:04d}@example.com",
        f"现居：{rng.choice(V3_CITIES)}",
        f"工作经验：{years} 年",
    ]
    # 只保留少量「行业大类」意向，绝不写精确岗位名
    if rng.random() < 0.35:
        header.append(f"求职意向：{prof['industry']}行业相关岗位")
    header.append(edu_line)

    lines = header
    lines += ["个人总结："] + personal
    lines += ["工作经历："]
    for block in blocks:
        lines.extend(block)
    lines += ["项目经历："] + project_lines
    lines += ["核心优势："] + ["- " + item for item in strengths]
    lines += [skill_line]
    lines += ["证书与培训："] + ["- " + item for item in certs]
    lines += languages
    lines += ["获奖情况："] + ["- " + item for item in awards]
    lines += ["社会活动："] + ["- " + item for item in activities]
    lines += ["工作习惯："] + ["- " + item for item in extras]
    lines += ["其他信息："] + ["- " + item for item in other_info]
    lines += [summary, NOTE]
    # 全篇同一条要点只保留一次，避免跨经历重复
    seen_bullets: set[str] = set()
    deduped_lines = []
    for line in lines:
        if line.startswith("- "):
            if line in seen_bullets:
                continue
            seen_bullets.add(line)
        deduped_lines.append(line)
    text = "\n".join(deduped_lines)

    if title and title in text:  # 硬性要求 5：正文不出现目标岗位名
        raise RuntimeError(f"{code}: 生成了目标岗位名 {title!r}")
    return {"ID": f"SYN{index:04d}", "Resume_str": text,
            "Category": code, "variant": variant, "source": "synthetic-v3"}


def allocate(counts: dict[str, int], targets: tuple[int, int, int]) -> dict[str, list[int]]:
    """最大余数法按类分层分到三个集合，保证总和精确等于 targets。"""
    total = sum(counts.values())
    quotas = {code: [n * target / total for target in targets] for code, n in counts.items()}
    alloc = {code: [int(q) for q in values] for code, values in quotas.items()}
    for slot, target in enumerate(targets):
        remainders = sorted(counts, key=lambda code: quotas[code][slot] - alloc[code][slot],
                            reverse=True)
        need = target - sum(values[slot] for values in alloc.values())
        for code in remainders[:need]:
            alloc[code][slot] += 1
    return alloc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jd", type=Path, default=DEFAULT_JD)
    parser.add_argument("--out", type=Path, default=ROOT / "synth")
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--hard", action="store_true",
                        help="去泄漏版：不写岗位名、按技能改写职责、只露部分技能")
    parser.add_argument("--v3", action="store_true",
                        help="v3：独立职业语汇集生成，正文不由目标 JD 派生")
    args = parser.parse_args()

    jobs = yaml.safe_load(args.jd.read_text(encoding="utf-8"))
    rng = random.Random(args.seed)
    counts = {job["code"]: 21 if index < TOTAL - 20 * len(jobs) else 20
              for index, job in enumerate(jobs)}
    alloc = allocate(counts, TARGETS)

    rows = []
    index = 0
    for job in jobs:
        for _ in range(counts[job["code"]]):
            if args.v3:
                rows.append(build_resume_v3(job, jobs, rng, index))
            else:
                rows.append(build_resume(job, jobs, rng, index, hard=args.hard))
            index += 1
    rng.shuffle(rows)

    by_category: dict[str, list[dict]] = {}
    for row in rows:
        by_category.setdefault(row["Category"], []).append(row)
    for code, items in by_category.items():
        rng.shuffle(items)
        train_n, val_n, _ = alloc[code]
        for position, item in enumerate(items):
            item["split"] = ("train" if position < train_n else
                             "val" if position < train_n + val_n else "test")

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "resumes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ID", "Resume_str", "Category",
                                                    "variant", "source", "split"])
        writer.writeheader()
        writer.writerows(rows)
    with (args.out / "split.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ID", "Category", "split"])
        for row in rows:
            writer.writerow([row["ID"], row["Category"], row["split"]])

    summary = {name: sum(1 for row in rows if row["split"] == name)
               for name in ("train", "val", "test")}
    print("总数", len(rows), summary)
    print("类别数", len(by_category), "每类", sorted(counts.values())[0], "-",
          sorted(counts.values())[-1])
    print("产物", args.out / "resumes.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
