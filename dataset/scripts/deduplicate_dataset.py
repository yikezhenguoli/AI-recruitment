#!/usr/bin/env python3
"""重复检测与去重分析。

默认只分析并输出报告；--apply 仅删除「同一份简历内完全相同」的问题文本，
并会检查删除后是否仍满足每份简历 8~12 道的约束（不满足则拒绝执行）。

用法： python3 scripts/deduplicate_dataset.py [--apply]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import config, pipeline  # noqa: E402
from lib.common import log, read_jsonl, write_json, write_jsonl  # noqa: E402


def signature(q: dict) -> str:
    s = re.sub(r"「[^」]*」", "「…」", q["question"])
    s = re.sub(r"《[^》]*》", "《…》", s)
    return re.sub(r"\d+", "N", s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    p = pipeline.paths()
    resumes = read_jsonl(p["resumes"])
    exps = read_jsonl(p["experiences"])
    qs = read_jsonl(p["questions"])

    resume_dup = Counter(r["resume_text"] for r in resumes)
    q_dup = Counter(q["question"] for q in qs)
    sig_dup = Counter(signature(q) for q in qs)
    exp_dup = Counter(e["original_content"] for e in exps)

    report = {
        "resume_total": len(resumes),
        "duplicate_resume_text_groups": sum(1 for v in resume_dup.values() if v > 1),
        "question_total": len(qs),
        "duplicate_question_groups": sum(1 for v in q_dup.values() if v > 1),
        "duplicate_question_ratio": round(sum(1 for v in q_dup.values() if v > 1) / max(1, len(qs)), 5),
        "max_identical_question_repeat": max(q_dup.values()) if q_dup else 0,
        "distinct_question_signatures": len(sig_dup),
        "max_signature_ratio": round(max(sig_dup.values()) / max(1, len(qs)), 5),
        "experience_total": len(exps),
        "duplicate_experience_content_groups": sum(1 for v in exp_dup.values() if v > 1),
        "top_duplicated_questions": [{"question": k[:160], "count": v}
                                     for k, v in q_dup.most_common(10) if v > 1],
        "top_signatures": [{"signature": k[:160], "count": v} for k, v in sig_dup.most_common(10)],
    }

    if args.apply:
        seen: set[tuple[str, str]] = set()
        kept = []
        removed = 0
        for q in qs:
            key = (q["resume_id"], q["question"])
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            kept.append(q)
        per = Counter(q["resume_id"] for q in kept)
        below = [rid for rid in per if per[rid] < 8]
        if below:
            report["apply_rejected"] = f"删除后 {len(below)} 份简历问题数不足 8，未写入"
            log("去重被拒绝：" + report["apply_rejected"])
        else:
            write_jsonl(p["questions"], kept)
            report["applied"] = True
            report["removed_questions"] = removed
            log(f"已删除同一简历内重复问题 {removed} 道（保留首条）")
    write_json(config.abspath("dataset/metadata/deduplication_report.json"), report, indent=2)
    log(f"重复分析：问题重复组 {report['duplicate_question_groups']} "
        f"({report['duplicate_question_ratio']})，模板签名 {report['distinct_question_signatures']} 种，"
        f"最高占比 {report['max_signature_ratio']}")


if __name__ == "__main__":
    main()
