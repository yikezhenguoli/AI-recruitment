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
                   f"{rng.choice(('责任心强', '沟通顺畅', '注重细节', '抗压能力好'))}。")
    else:
        summary = (f"自我评价：{years} 年{title}相关经验，"
                   f"{rng.choice(('熟悉', '熟练掌握', '能够独立完成'))}"
                   f"{rng.choice(core) if core else '本岗位核心工作'}，"
                   f"{rng.choice(('责任心强', '沟通顺畅', '注重细节', '抗压能力好'))}。")

    lines = header + ["工作经历："]
    for block in jobs:
        lines.extend(block)
    lines += ["项目经历："] + project_lines
    lines += [skill_line, summary, NOTE]
    return {"ID": f"SYN{index:04d}", "Resume_str": "\n".join(lines),
            "Category": job["code"], "variant": variant, "source": "synthetic"}


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
