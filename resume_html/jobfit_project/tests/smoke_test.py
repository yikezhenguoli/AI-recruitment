"""端到端自测：用真实 CSV 的小子集训练 2 轮，再验证两个业务方向与自定义输入。

    python tests/smoke_test.py --data-dir /path/to/resume_html
正常机器约几十秒（CPU）。全部断言通过会打印 SMOKE TEST PASSED。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from jobfit.cli import main as cli_main  # noqa: E402
from jobfit.config import Config  # noqa: E402
from jobfit.data import Corpus  # noqa: E402
from jobfit.inference import JobFitPredictor, write_csv  # noqa: E402
from jobfit.train import train  # noqa: E402


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="./data")
    ap.add_argument("--max-samples", type=int, default=240)
    ap.add_argument("--epochs", type=int, default=2)
    args = ap.parse_args()

    runtime = Path(__file__).resolve().parents[1] / ".runtime"
    runtime.mkdir(exist_ok=True)
    out = str(runtime / "smoke_outputs")
    cfg = Config(data_dir=args.data_dir, out_dir=out, epochs=args.epochs,
                 batch_size=16, max_samples=args.max_samples,
                 max_len=160, max_job_len=64, min_df=2, max_vocab=8000,
                 d_emb=48, d_model=48, cnn_kernels=[2, 3],
                 patience=3, device="cpu", score_mode="spread")
    corpus = Corpus.build(cfg)
    check(corpus.n_jobs == 24, "应有 24 个岗位类别")
    check(all(len(v) > 0 for v in corpus.splits.values()), "train/val/test 均不能为空")
    check(len(corpus.vocab) > 100, "词表过小")
    check(corpus.X_ids.shape == (len(corpus.records), cfg.max_len), "特征矩阵形状错误")
    print(f"[1/6] 语料 OK: {len(corpus.records)} 份 / 词表 {len(corpus.vocab)}")

    ckpt, report = train(cfg, corpus)
    check(ckpt.exists(), "checkpoint 未生成")
    check("classification" in report["test"], "缺少测试指标")
    print(f"[2/6] 训练 OK: test acc={report['test']['classification'].get('accuracy', 0):.3f}")

    p = JobFitPredictor(ckpt, device="cpu")
    check(len(p.meta) == len(corpus.records), "checkpoint 简历数不一致")
    check(p.calib.fitted, "校准器未拟合")
    print(f"[3/6] 加载 OK: T={p.calib.T:.3f} a={p.calib.a:.3f} b={p.calib.b:.3f}")

    # 功能 1：一人多岗
    jobs = p.rank_jobs_for_resume(resume_id=0, top_k=5, explain=True)
    check(len(jobs) == 5, "岗位排序数量错误")
    check(all(0 <= m.score <= 100 for m in jobs), "适配分必须落在 0-100")
    check(all(jobs[i].score >= jobs[i + 1].score for i in range(4)), "岗位未按分数降序")
    check(abs(sum(p.calib.share(p._logits(p._rows_arrays([0]))).ravel()) - 100) < 1e-3,
          "job_share 应合计 100")
    check(bool(jobs[0].evidence.get("field_contribution")), "缺少字段归因")
    check(all(0 <= m.match_probability <= 100 for m in jobs), "匹配概率越界")
    alt = p.rank_jobs_for_resume(resume_id=0, top_k=3, score_mode="platt")
    check(len(alt) == 3 and all(0 <= m.score <= 100 for m in alt), "platt 模式失败")
    print(f"[4/6] 一人多岗 OK: top1={jobs[0].label} {jobs[0].score:.2f}分, "
          f"top5={[round(m.score, 1) for m in jobs]}")

    # 功能 2：一岗多人
    cands = p.rank_resumes_for_job("HR", top_x=5, explain=True)
    check(len(cands) == 5, "候选人数量错误")
    check(all(0 <= m.score <= 100 for m in cands), "适配分必须落在 0-100")
    check(all(cands[i].score >= cands[i + 1].score for i in range(4)), "候选人未按分数降序")
    print(f"[5/6] 一岗多人 OK: top1=resume{cands[0].resume_id} {cands[0].score:.2f}分")

    # 自定义输入 + 百分位模式 + CSV + CLI
    custom = p.rank_resumes_for_job(
        jd_text="Human resources recruiting payroll benefits employee relations HRIS onboarding",
        job_title="HR Manager", top_x=3, score_mode="percentile")
    check(len(custom) == 3 and all(0 <= m.score <= 100 for m in custom), "自定义 JD 失败")
    new_resume = p.rank_jobs_for_resume(
        resume_text="Senior software engineer. Python, pytorch, distributed systems, SQL, AWS.",
        top_k=3, score_mode="share")
    check(len(new_resume) == 3, "新简历文本推理失败")
    write_csv((m.as_dict() for m in jobs), runtime / "smoke_jobs.csv")
    write_csv((m.as_dict() for m in cands), runtime / "smoke_candidates.csv")
    cli_main(["match-candidates", "--ckpt", str(ckpt), "--job", "HR", "--top-x", "3"])
    cli_main(["match-jobs", "--ckpt", str(ckpt), "--resume-id", "0", "--top-k", "3"])
    print("[6/6] 自定义 JD / 新简历 / CSV / CLI 全部 OK")
    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    main()
