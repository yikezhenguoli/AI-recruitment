"""命令行入口。所有命令都从项目根目录执行：python -m jobfit.cli <子命令>

  python -m jobfit.cli train --data-dir /path/to/resume_html --epochs 40
  python -m jobfit.cli info  --ckpt outputs/jobfit.ckpt
  python -m jobfit.cli eval  --ckpt outputs/jobfit.ckpt
  python -m jobfit.cli match-jobs       --ckpt outputs/jobfit.ckpt --resume-id 3 --top-k 5 --explain
  python -m jobfit.cli match-candidates --ckpt outputs/jobfit.ckpt --job HR --top-x 10 --csv top10.csv
  python -m jobfit.cli match-candidates --ckpt outputs/jobfit.ckpt --jd-file jd.txt --top-x 10
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from .config import Config
from .evaluate import classification_metrics, expected_calibration_error, ranking_report, softmax
from .utils import save_json


def _common(p: argparse.ArgumentParser, ckpt: bool = False) -> None:
    p.add_argument("--config", default=None, help="JSON 配置文件")
    p.add_argument("--set", action="append", default=[], metavar="K=V",
                   help="覆盖任意 Config 字段，可重复，如 --set lr=0.001")
    p.add_argument("--data-dir", default=None, help="存放 resumes.csv / tag.csv 的目录")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--device", default=None, help="auto / cpu / cuda / mps")
    if ckpt:
        p.add_argument("--ckpt", default="outputs/jobfit.ckpt")


def _cfg_from(args: argparse.Namespace) -> Config:
    cfg = Config.load(args.config)
    ov: dict[str, Any] = {}
    for item in getattr(args, "set", []) or []:
        if "=" in item:
            k, v = item.split("=", 1)
            ov[k.strip()] = v
    for k in ("data_dir", "out_dir", "device", "epochs", "batch_size", "lr",
              "max_samples", "score_mode", "patience"):
        v = getattr(args, k, None)
        if v is not None:
            ov[k] = v
    return cfg.update(ov)


def _fmt(v: Any, width: int = 46) -> str:
    s = str(v).replace("\n", " ")
    return s if len(s) <= width else s[:width - 1] + "…"


def cmd_train(args: argparse.Namespace) -> None:
    from .train import train
    cfg = _cfg_from(args)
    ckpt, report = train(cfg, data_dir=cfg.data_dir)
    print("\n训练完成：", ckpt)
    print(json.dumps(report["test"]["classification"], ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report["test"]["candidate_ranking"].items()
                      if k != "per_job"}, ensure_ascii=False, indent=2))


def cmd_info(args: argparse.Namespace) -> None:
    from .inference import JobFitPredictor
    p = JobFitPredictor(args.ckpt, device=args.device or "auto")
    info = p.info()
    print(f"简历 {info['n_resumes']} 份 | 岗位 {info['n_jobs']} 个 | 词表 {info['n_vocab']}")
    print(f"校准 T={p.calib.T:.3f} a={p.calib.a:.3f} b={p.calib.b:.3f} "
          f"z锚点=[{p.calib.z_lo:.2f}, {p.calib.z_hi:.2f}] | 默认分数模式 {info['score_mode']}")
    print("\n岗位表：")
    for j in info["jobs"]:
        print(f"  {j['job_id']:2d}  {j['label']:<24s} {j['title']:<26s} 训练样本 {j['n_train']}")
    if info["metrics"]:
        print("\n训练时测试集表现：", json.dumps(info["metrics"]["classification"],
                                          ensure_ascii=False))


def cmd_eval(args: argparse.Namespace) -> None:
    from .inference import JobFitPredictor
    p = JobFitPredictor(args.ckpt, device=args.device or "auto")
    rows = p.splits.get("test", [])
    if not rows:
        print("checkpoint 中没有 test 划分信息")
        return
    arrays = p._rows_arrays(rows)
    logits = p._logits(arrays)
    labels = np.asarray([p.label2id[p.meta[r]["label"]] for r in rows])
    cls = classification_metrics(logits, labels)
    cls["ece"] = expected_calibration_error(softmax(p.calib.z(logits)), labels)
    rank = ranking_report(logits, labels, p.id2label, (1, 5, 10))
    report = {"n_test": len(rows), "classification": cls,
              "candidate_ranking": {k: v for k, v in rank.items() if k != "per_job"}}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    out = Path(args.out or "outputs/eval_report.json")
    save_json(report, out)
    print("已写入", out)


def cmd_match_jobs(args: argparse.Namespace) -> None:
    from .inference import JobFitPredictor, write_csv
    p = JobFitPredictor(args.ckpt, device=args.device or "auto")
    text = None
    if args.resume_file:
        text = Path(args.resume_file).read_text(encoding="utf-8", errors="replace")
    elif args.resume_text:
        text = args.resume_text
    job_ids = [int(x) for x in args.jobs.split(",")] if args.jobs else None
    res = p.rank_jobs_for_resume(resume_id=args.resume_id, resume_text=text,
                                 job_ids=job_ids, top_k=args.top_k,
                                 score_mode=args.score_mode, explain=args.explain)
    print(f"\n{'排名':<5}{'适配分':>8}{'匹配概率':>10}{'岗位占比':>10}{'百分位':>9}  {'岗位标签':<24}{'岗位名称'}")
    for m in res:
        print(f"{m.rank:<5}{m.score:>8.2f}{m.match_probability:>10.2f}"
              f"{m.job_share:>10.2f}{m.percentile:>9.2f}  {m.label:<24}{m.title}")
        if args.explain:
            fld = ", ".join(f"{x['field']}:{x['logit_drop']:+.2f}"
                            for x in m.evidence.get("field_contribution", [])[:3])
            print(f"      依据 | 字段贡献 {fld}")
            print(f"            | 命中关键词 {', '.join(m.evidence.get('matched_terms', [])[:8])}")
    if args.csv:
        write_csv((m.as_dict() for m in res), args.csv)
        print("已写入", args.csv)


def cmd_match_candidates(args: argparse.Namespace) -> None:
    from .inference import JobFitPredictor, write_csv
    p = JobFitPredictor(args.ckpt, device=args.device or "auto")
    cand = None
    if args.candidates:
        cand = [x.strip() for x in args.candidates.split(",") if x.strip()]
    jd_text = args.jd_text
    res = p.rank_resumes_for_job(job=args.job, jd_text=jd_text, jd_file=args.jd_file,
                                 job_title=args.job_title or "Custom Position",
                                 required_skills=args.required_skills or "",
                                 candidate_ids=cand, top_x=args.top_x,
                                 score_mode=args.score_mode, explain=args.explain)
    target = args.job or "自定义 JD"
    print(f"\n岗位 {target} | 候选人 {len(res)} 名（按适配分降序）")
    print(f"{'排名':<5}{'适配分':>8}{'匹配概率':>10}{'百分位':>9}  {'resume_id':<11}{'姓名/抬头':<40}{'原标签'}")
    for m in res:
        print(f"{m.rank:<5}{m.score:>8.2f}{m.match_probability:>10.2f}"
              f"{m.percentile:>9.2f}  {m.resume_id:<11}"
              f"{_fmt(m.name, 38):<40}{m.true_label}")
        if args.explain:
            fld = ", ".join(f"{x['field']}:{x['logit_drop']:+.2f}"
                            for x in m.evidence.get("field_contribution", [])[:3])
            print(f"      依据 | 字段贡献 {fld}")
            print(f"            | 命中关键词 {', '.join(m.evidence.get('matched_terms', [])[:8])}")
    if args.csv:
        write_csv((m.as_dict() for m in res), args.csv)
        print("已写入", args.csv)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="jobfit", description="简历-岗位适配度模型（PyTorch）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("train", help="训练 + 校准 + 评估")
    _common(p)
    for k, t in [("epochs", int), ("batch_size", int), ("lr", float),
                 ("max_samples", int), ("patience", int)]:
        p.add_argument("--" + k.replace("_", "-"), type=t, default=None)
    p.add_argument("--score-mode", default=None,
                   choices=["spread", "platt", "share", "percentile"])
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("info", help="查看 checkpoint 中的岗位表与指标")
    _common(p, ckpt=True)
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("eval", help="在 test 划分上重新评估分类与选人排序")
    _common(p, ckpt=True)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("match-jobs", help="功能1：一个求职者匹配多个岗位")
    _common(p, ckpt=True)
    p.add_argument("--resume-id", default=None)
    p.add_argument("--resume-text", default=None)
    p.add_argument("--resume-file", default=None, help="新简历 txt 文件")
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--jobs", default=None, help="限定岗位编号，逗号分隔")
    p.add_argument("--score-mode", default=None,
                   choices=["spread", "platt", "share", "percentile"])
    p.add_argument("--explain", action="store_true")
    p.add_argument("--csv", default=None)
    p.set_defaults(func=cmd_match_jobs)

    p = sub.add_parser("match-candidates", help="功能2：一个岗位选最合适的前 x 人")
    _common(p, ckpt=True)
    p.add_argument("--job", default=None, help="岗位标签或编号，如 HR / INFORMATION-TECHNOLOGY / 0")
    p.add_argument("--jd-text", default=None, help="自定义岗位描述文本")
    p.add_argument("--jd-file", default=None, help="自定义 JD 的 txt 文件")
    p.add_argument("--job-title", default=None)
    p.add_argument("--required-skills", default=None)
    p.add_argument("--candidates", default=None, help="限定候选 resume_id，逗号分隔")
    p.add_argument("--top-x", type=int, default=10)
    p.add_argument("--score-mode", default=None,
                   choices=["spread", "platt", "share", "percentile"])
    p.add_argument("--explain", action="store_true")
    p.add_argument("--csv", default=None)
    p.set_defaults(func=cmd_match_candidates)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
