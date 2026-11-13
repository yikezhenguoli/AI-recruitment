"""Python API 最小示例（复制整个 jobfit_project 后，从项目根目录运行）。

    python examples/demo_api.py --ckpt outputs/jobfit.ckpt
"""
from __future__ import annotations

import argparse
from pathlib import Path

from jobfit.inference import JobFitPredictor, write_csv


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="outputs/jobfit.ckpt")
    ap.add_argument("--out-dir", default="./demo_outputs")
    args = ap.parse_args()

    p = JobFitPredictor(args.ckpt)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # ---------- 功能 1：一个求职者 -> 多个岗位，按适配度排序 + 百分制打分 ----------
    matches = p.rank_jobs_for_resume(resume_id=3, top_k=5, explain=True)
    print("\n[简历 3] 岗位适配度排名")
    for m in matches:
        print(f"  {m.rank}. {m.title:<26} {m.score:6.2f} 分  "
              f"(岗位占比 {m.job_share:.1f}%, 百分位 {m.percentile:.1f})")
    top = matches[0]
    print("  打分依据:", top.evidence.get("field_contribution", []))
    print("  命中关键词:", ", ".join(top.evidence.get("matched_terms", [])))
    write_csv((m.as_dict() for m in matches), out / "resume3_job_ranking.csv")

    # ---------- 功能 2：一个岗位 -> 多个求职者，选最合适的前 x 人 ----------
    x = 10
    people = p.rank_resumes_for_job("INFORMATION-TECHNOLOGY", top_x=x,
                                    score_mode="spread", explain=True)
    print(f"\n[岗位 INFORMATION-TECHNOLOGY] 最合适的前 {x} 人")
    for c in people:
        print(f"  {c.rank:2d}. resume{c.resume_id:<6} {c.score:6.2f} 分  "
              f"{c.name[:38]:<40} (原标签 {c.true_label})")
    write_csv((c.as_dict() for c in people), out / "top10_it_candidates.csv")

    # 只在一部分候选人里挑人
    subset = ["0", "1", "2", "100", "101", "102"]
    small = p.rank_resumes_for_job("HR", candidate_ids=subset, top_x=3)
    print("\n[限定候选池] HR 前 3 人:", [(c.resume_id, round(c.score, 2)) for c in small])

    # ---------- 扩展：全新简历 / 全新岗位 JD ----------
    new_resume = ("Senior Python engineer with 8 years in machine learning, "
                  "pytorch, distributed training, SQL and AWS. Built recommendation systems.")
    print("\n[全新简历] 岗位 top3:",
          [(m.label, round(m.score, 2))
           for m in p.rank_jobs_for_resume(resume_text=new_resume, top_k=3)])

    jd = "We need an HR generalist: recruiting, payroll, benefits administration, employee relations."
    print("[全新 JD ] 候选人 top3:",
          [(c.resume_id, round(c.score, 2))
           for c in p.rank_resumes_for_job(jd_text=jd, job_title="HR Generalist", top_x=3)])

    print(f"\nCSV 已写入 {out.resolve()}")


if __name__ == "__main__":
    main()
