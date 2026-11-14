#!/usr/bin/env python3
"""与模型无关的泄漏体检。

判据只看「简历文本与它自己那份 JD 的表面重合，是否明显高于与别的 JD 的重合」。
如果高得多，说明简历是按该岗位的 JD 造出来的（构造性泄漏），模型学到的只是抄词。

用法：
  python audit_leakage.py --csv synth_hard/resumes.csv
  python audit_leakage.py --jsonl data/resume_zh.jsonl   # 真实语料参照

指标（越小越不像泄漏）：
  title      简历直接写出自身岗位名的比例
  skill_own  简历命中自身 JD 技能短语的平均比例
  skill_oth  命中随机三份其他 JD 技能短语的平均比例
  copy_top1  按字三元组重合排序，自身 JD 排第一的比例
  hard_top1  自身 JD 的重合率比第二名高出 50% 以上的比例
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
JD = ROOT / "jd" / "jobs_24.yaml"

PUNCT = re.compile(r"[\s，。、；：！？（）()\[\]【】<>《》“”‘’\"'`~!@#$%^&*_+=|\\/—…·,.;:?\-]+")


def terms_of(job: dict) -> list[str]:
    out: list[str] = []
    for item in job.get("required_skills_zh") or []:
        body = str(item).split("：", 1)[-1]
        body = re.sub(r"[（(【\[]", "、", body)
        body = re.sub(r"[）)】\]]", "、", body)
        for term in re.split(r"[、，,；;]", body):
            term = term.strip(" 。.")
            if len(term) >= 2:
                out.append(term)
    return list(dict.fromkeys(out))


def grams(text: str, n: int = 3) -> set[str]:
    clean = PUNCT.sub("", text)
    if len(clean) < n:
        return {clean} if clean else set()
    return {clean[i:i + n] for i in range(len(clean) - n + 1)}


def containment(part: set[str], whole: set[str]) -> float:
    return len(part & whole) / len(part) if part else 0.0


def load_rows(path: Path) -> list[dict]:
    if path.suffix == ".jsonl":
        return [{"id": r["id"], "category": r["category"], "text": r["zh"]}
                for r in (json.loads(line) for line in path.open(encoding="utf-8"))]
    with path.open(encoding="utf-8") as handle:
        return [{"id": r["ID"], "category": r["Category"], "text": r["Resume_str"]}
                for r in csv.DictReader(handle)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--jd", type=Path, default=JD)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    rows = load_rows(args.csv or args.jsonl)
    jobs = {job["code"]: job for job in yaml.safe_load(args.jd.read_text(encoding="utf-8"))}
    codes = list(jobs)
    rng = random.Random(args.seed)

    stats = {k: [] for k in ("title", "skill_own", "skill_oth",
                             "copy_top1", "hard_top1", "margin")}
    per_class: dict[str, list[int]] = {}

    for row in rows:
        text = row["text"]
        own = jobs[row["category"]]
        own_terms = terms_of(own)
        own_g = grams(text)
        hits = {code: sum(1 for t in terms_of(jobs[code]) if t in text) / max(len(terms_of(jobs[code])), 1)
                for code in codes}
        overlap = {code: containment(own_g, grams(" ".join(
            [jobs[code].get("title_zh", ""), *(jobs[code].get("responsibilities_zh") or [])]
            + [str(x) for x in jobs[code].get("required_skills_zh") or []]))) for code in codes}

        others = [c for c in codes if c != row["category"]]
        sampled = rng.sample(others, 3)
        ranked = sorted(overlap.items(), key=lambda kv: kv[1], reverse=True)
        best_code, best = ranked[0]
        second = ranked[1][1]

        stats["title"].append(float(own["title_zh"] in text))
        stats["skill_own"].append(hits[row["category"]])
        stats["skill_oth"].append(statistics.mean(hits[c] for c in sampled))
        stats["copy_top1"].append(float(best_code == row["category"]))
        stats["hard_top1"].append(float(best_code == row["category"] and best > second * 1.5))
        stats["margin"].append(overlap[row["category"]] - max(overlap[c] for c in others))
        bucket = per_class.setdefault(row["category"], [0, 0])
        bucket[0] += int(best_code == row["category"])
        bucket[1] += 1

    def pct(key: str) -> float:
        return 100 * statistics.mean(stats[key])

    name = (args.csv or args.jsonl).name
    print(f"== {name}  n={len(rows)} ==")
    print(f"title      简历写出自身岗位名        {pct('title'):5.1f}%")
    print(f"skill_own  命中自身 JD 技能短语       {100 * statistics.mean(stats['skill_own']):5.1f}%")
    print(f"skill_oth  命中其他 JD 技能短语       {100 * statistics.mean(stats['skill_oth']):5.1f}%")
    print(f"copy_top1  字三元组重合第一名=自身    {pct('copy_top1'):5.1f}%")
    print(f"hard_top1  且比第二名高 50% 以上      {pct('hard_top1'):5.1f}%")
    print(f"margin     自身重合率 − 最高他人      {statistics.mean(stats['margin']):+.4f}")
    worst = sorted(per_class.items(), key=lambda kv: kv[1][0] / kv[1][1])[:5]
    print("最难类别(命中率):", ", ".join(f"{c} {v[0]}/{v[1]}" for c, v in worst))
    if args.json_out:
        args.json_out.write_text(json.dumps({
            "n": len(rows),
            "title_pct": pct("title"),
            "skill_own": statistics.mean(stats["skill_own"]),
            "skill_oth": statistics.mean(stats["skill_oth"]),
            "copy_top1_pct": pct("copy_top1"),
            "hard_top1_pct": pct("hard_top1"),
            "margin": statistics.mean(stats["margin"]),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
