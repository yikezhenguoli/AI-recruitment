#!/usr/bin/env python3
"""pair 模型的对外评测：一条简历 × 24 个 JD 的 24 选 1 排名。

报告三组数字，缺一不可：
  1. 模型 Recall@1/3/5、MRR
  2. TF-IDF 余弦基线（同一个 24 选 1 任务）
  3. **四条证伪判据**：
     * 负配对敏感性 —— 正配概率减掉其余 23 个 JD 的平均概率，贴近 0 说明 JD 没起作用
     * 只看标题 —— JD 正文全部删掉、只留岗位名，若排名不掉说明模型没在读 JD 正文
     * 只看正文 —— 删掉岗位名、只留职责与要求；若它也接近满分，说明"标题是关键"这个
       结论不成立（另一种解释是模型只要 JD 里有字就行，那判据本身需要重设计）
     * 打乱 JD —— 用别的类别的 JD 来打分，Recall@1 应回落到约 1/24
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from common import (
    DEFAULT_CSV,
    DEFAULT_JD,
    DEFAULT_SPLIT,
    build_examples,
    load_jd_info,
    load_labels,
    write_json,
)
from infer import ResumeMatcher
from train_pair import build_jd_text
ROOT = Path(__file__).resolve().parent


def load_reference_jds(jd_path: Path, codes: list[str], lang: str) -> dict[str, str]:
    info = load_jd_info(jd_path)
    return {code: build_jd_text(info[code], lang) for code in codes}


def body_only(job: dict, lang: str = "en") -> str:
    """去掉岗位标题，只留职责、技能、学历与年限。"""
    text = build_jd_text(job, lang)
    title = str(job.get(f"title_{lang}") or "").strip()
    if title and text.startswith(title):
        text = text[len(title):].lstrip("\n")
    return text


def rank_of_true(probs: np.ndarray, true_index: int) -> int:
    order = np.argsort(-probs)
    return int(np.where(order == true_index)[0][0]) + 1


def ranking_metrics(probs: np.ndarray, true_indices: list[int]) -> dict:
    ranks = [rank_of_true(probs[i], true) for i, true in enumerate(true_indices)]
    n = len(ranks)
    margins = []
    for i, true in enumerate(true_indices):
        others = np.delete(probs[i], true)
        margins.append(float(probs[i, true] - others.mean()))
    return {
        "n": n,
        "recall_at_1": sum(r <= 1 for r in ranks) / n,
        "recall_at_3": sum(r <= 3 for r in ranks) / n,
        "recall_at_5": sum(r <= 5 for r in ranks) / n,
        "mrr": sum(1.0 / r for r in ranks) / n,
        "mean_rank": statistics.fmean(ranks),
        "median_rank": statistics.median(ranks),
        "mean_margin": statistics.fmean(margins),
        "min_margin": min(margins),
        "p10_margin": float(np.percentile(margins, 10)),
    }, ranks


def bootstrap_diff(hits_a: list[int], hits_b: list[int], n_boot: int, seed: int) -> dict:
    """对两条 Recall@1 的差值做配对 bootstrap（同一批简历重采样）。"""
    rng = np.random.default_rng(seed)
    a = np.asarray(hits_a, dtype=np.float64)
    b = np.asarray(hits_b, dtype=np.float64)
    n = len(a)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        diffs[i] = a[idx].mean() - b[idx].mean()
    return {
        "mean": float(a.mean() - b.mean()),
        "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
        "p_two_sided": float(min(1.0, 2 * min((diffs <= 0).mean(), (diffs >= 0).mean()))),
    }


def tfidf_ranking(train_texts: list[str], eval_texts: list[str],
                  jd_texts: list[str], true_indices: list[int]) -> dict:
    vectorizer = TfidfVectorizer(sublinear_tf=True, min_df=2, ngram_range=(1, 2))
    vectorizer.fit(train_texts + jd_texts)
    eval_vecs = vectorizer.transform(eval_texts)
    jd_vecs = vectorizer.transform(jd_texts)
    sims = cosine_similarity(eval_vecs, jd_vecs)
    metrics, ranks = ranking_metrics(sims, true_indices)
    return metrics, ranks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--jd", type=Path, default=DEFAULT_JD)
    parser.add_argument("--which", default="test", choices=["val", "test"])
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--bootstrap-n", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    codes, label2id, _ = load_labels(args.split)
    examples = build_examples(args.csv, args.split, args.which)
    true_indices = [label2id[ex["category"]] for ex in examples]
    texts = [ex["text"] for ex in examples]
    jds = load_reference_jds(args.jd, codes, "en")
    jd_list = [jds[code] for code in codes]
    titles = [str(load_jd_info(args.jd)[code].get("title_en") or code) for code in codes]
    bodies = [body_only(load_jd_info(args.jd)[code]) for code in codes]

    matcher = ResumeMatcher(model_dir=args.model_dir, device=args.device)
    if matcher.task != "pair":
        print(f"错误：{args.model_dir} 是 {matcher.task} 模型，不是 pair 模型", file=sys.stderr)
        return 2

    def matrix(reference: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            rows.append(matcher.score_pairs([(text, ref) for ref in reference], args.batch_size))
        return np.asarray(rows)

    full = matrix(jd_list)
    title_only = matrix(titles)
    body_only_m = matrix(bodies)
    # 打乱 JD：第 i 条简历配的是"别的类别"的 JD 集合（整体循环右移一位），
    # 正确 JD 已不在候选里，Recall@1 应当塌到约 1/24 的随机水平。
    shuffled_ref = jd_list[1:] + jd_list[:1]
    shuffled = matrix(shuffled_ref)

    full_metrics, ranks = ranking_metrics(full, true_indices)
    title_metrics, title_ranks = ranking_metrics(title_only, true_indices)
    body_metrics, body_ranks = ranking_metrics(body_only_m, true_indices)
    shuffled_metrics, shuffled_ranks = ranking_metrics(shuffled, true_indices)

    hits_full = [1 if r <= 1 else 0 for r in ranks]
    hits_title = [1 if r <= 1 else 0 for r in title_ranks]
    hits_body = [1 if r <= 1 else 0 for r in body_ranks]
    train_texts = [ex["text"] for ex in build_examples(args.csv, args.split, "train")]
    tfidf_metrics, tfidf_ranks = tfidf_ranking(train_texts, texts, jd_list, true_indices)
    hits_tfidf = [1 if r <= 1 else 0 for r in tfidf_ranks]

    per_class = {}
    for i, ex in enumerate(examples):
        per_class.setdefault(ex["category"], []).append(ranks[i])
    per_class_report = [
        {"category": code, "n": len(rs), "recall_at_1": sum(r <= 1 for r in rs) / len(rs),
         "mean_rank": statistics.fmean(rs)}
        for code, rs in sorted(per_class.items())
    ]

    report = {
        "which": args.which,
        "model_dir": str(args.model_dir),
        "model_version": matcher.model_version,
        "n_examples": len(examples),
        "task": "24-choose-1 ranking",
        "model": full_metrics,
        "tfidf_cosine": tfidf_metrics,
        "bootstrap_model_minus_tfidf": bootstrap_diff(hits_full, hits_tfidf, args.bootstrap_n, args.seed),
        "falsification": {
            "title_only_jd": title_metrics,
            "body_only_jd": body_metrics,
            "shuffled_jd": shuffled_metrics,
            "note": (
                "若 title_only 的 Recall@1 与完整 JD 接近，说明模型没在读 JD 正文；"
                "body_only 用来排除「只要有字就行」这一替代解释；"
                "shuffled_jd 的正确 JD 不在候选内，应接近 1/24=0.042。"
            ),
        },
        "ablation_diff": {
            "full_minus_title": bootstrap_diff(hits_full, hits_title, args.bootstrap_n, args.seed),
            "full_minus_body": bootstrap_diff(hits_full, hits_body, args.bootstrap_n, args.seed),
            "title_minus_body": bootstrap_diff(hits_title, hits_body, args.bootstrap_n, args.seed),
            "note": "同一批样本上的配对 bootstrap，避免拿两个独立读数直接相减。",
        },
        "per_class": per_class_report,
    }
    out_dir = args.out_dir or (args.model_dir.parent / f"eval-{args.which}")
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "metrics.json", report)
    with (out_dir / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "true_category", "top1", "rank", "prob_true", "prob_top1"])
        for i, ex in enumerate(examples):
            top = int(np.argmax(full[i]))
            writer.writerow([ex["id"], ex["category"], codes[top], ranks[i],
                             f"{full[i, true_indices[i]]:.6f}", f"{full[i, top]:.6f}"])

    print(f"\n== {args.which} 集 {len(examples)} 条，模型 {matcher.model_version} ==")
    print(f"模型       Recall@1={full_metrics['recall_at_1']:.4f} "
          f"@3={full_metrics['recall_at_3']:.4f} @5={full_metrics['recall_at_5']:.4f} "
          f"MRR={full_metrics['mrr']:.4f} 平均名次={full_metrics['mean_rank']:.2f}")
    print(f"TF-IDF 余弦 Recall@1={tfidf_metrics['recall_at_1']:.4f} "
          f"@3={tfidf_metrics['recall_at_3']:.4f} MRR={tfidf_metrics['mrr']:.4f}")
    diff = report["bootstrap_model_minus_tfidf"]
    print(f"差值       {diff['mean']:+.4f} 95%CI [{diff['ci95'][0]:+.4f}, {diff['ci95'][1]:+.4f}] "
          f"p={diff['p_two_sided']:.4f}")
    print(f"证伪 | JD 只留标题 Recall@1={title_metrics['recall_at_1']:.4f} "
          f"（完整 JD {full_metrics['recall_at_1']:.4f}）")
    print(f"证伪 | JD 只留正文 Recall@1={body_metrics['recall_at_1']:.4f} "
          f"@3={body_metrics['recall_at_3']:.4f} @5={body_metrics['recall_at_5']:.4f} "
          f"MRR={body_metrics['mrr']:.4f}")
    for name, label in (("full_minus_title", "完整减只留标题"),
                        ("full_minus_body", "完整减只留正文"),
                        ("title_minus_body", "只留标题减只留正文")):
        diff = report["ablation_diff"][name]
        print(f"消融 | {label} {diff['mean']:+.4f} "
              f"95%CI [{diff['ci95'][0]:+.4f}, {diff['ci95'][1]:+.4f}] p={diff['p_two_sided']:.4f}")
    print(f"证伪 | JD 打乱     Recall@1={shuffled_metrics['recall_at_1']:.4f}（随机水平 0.0417）")
    print(f"负配对敏感性       平均 margin={full_metrics['mean_margin']:+.4f} "
          f"p10={full_metrics['p10_margin']:+.4f}")
    print(f"产物：{out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
