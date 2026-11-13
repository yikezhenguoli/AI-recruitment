"""val.py / test.py 共用的评估逻辑。

包含：
  * 载入 best/ 跑神经模型，算 accuracy / macro-F1 / weighted-F1 / 每类 P-R-F1 / 混淆矩阵
  * 同划分训练 TF-IDF + LinearSVC / LogisticRegression 基线并排对照
  * 配对 bootstrap 置信区间（n=100 时，小数点后的差异很可能是噪声）
  * 类别不平衡诊断：被误判最多的 5 组混淆对、召回最低的类
产物：metrics.json / report.txt / confusion_matrix.csv / per_class.csv / predictions.csv
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score

from baseline import fit_and_eval_baselines
from common import (
    DEFAULT_CSV,
    DEFAULT_JD,
    DEFAULT_SPLIT,
    build_examples,
    compute_metrics,
    dataset_stats,
    format_duration,
    load_jd_info,
    load_labels,
    resolve_path,
    top_confusion_pairs,
    write_json,
)
from infer import ResumeMatcher


# --------------------------------------------------------------------------- 指标
def paired_bootstrap(
    y_true: list[int],
    pred_a: list[int],
    pred_b: list[int],
    *,
    n_boot: int = 1000,
    seed: int = 42,
) -> dict:
    """A(神经) 与 B(基线) 在同一批样本上的配对 bootstrap 差值区间。

    macro-F1 每次只在本次重采样出现的类别上求平均，避免"未出现的类自动算 0"
    带来的虚假下降。
    """
    y = np.asarray(y_true, dtype=np.int64)
    a = np.asarray(pred_a, dtype=np.int64)
    b = np.asarray(pred_b, dtype=np.int64)
    n = len(y)
    if n == 0 or n_boot <= 0:
        return {}

    rng = np.random.default_rng(seed)
    acc_diffs = np.empty(n_boot, dtype=np.float64)
    f1_diffs = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        ys = y[idx]
        a_s, b_s = a[idx], b[idx]
        acc_diffs[i] = float((a_s == ys).mean() - (b_s == ys).mean())
        present = np.unique(ys)
        f1_diffs[i] = f1_score(ys, a_s, labels=present, average="macro", zero_division=0) - f1_score(
            ys, b_s, labels=present, average="macro", zero_division=0
        )

    def summarize(arr: np.ndarray) -> dict:
        return {
            "mean": float(arr.mean()),
            "ci_low": float(np.percentile(arr, 2.5)),
            "ci_high": float(np.percentile(arr, 97.5)),
            "p_le_0": float((arr <= 0).mean()),
        }

    return {
        "n_boot": int(n_boot),
        "n_samples": int(n),
        "accuracy_diff": summarize(acc_diffs),
        "macro_f1_diff": summarize(f1_diffs),
    }


def _verdict(neural: dict, baseline: dict, boot: dict) -> str:
    if not boot:
        return "未做 bootstrap，无法判断差异是否只是噪声。"
    delta_acc = neural["accuracy"] - baseline["accuracy"]
    delta_f1 = neural["macro_f1"] - baseline["macro_f1"]
    acc_ci = boot["accuracy_diff"]
    f1_ci = boot["macro_f1_diff"]
    parts = [
        f"accuracy 差值 {delta_acc:+.4f}（95% CI [{acc_ci['ci_low']:+.4f}, {acc_ci['ci_high']:+.4f}]），"
        f"macro-F1 差值 {delta_f1:+.4f}（95% CI [{f1_ci['ci_low']:+.4f}, {f1_ci['ci_high']:+.4f}]）。"
    ]
    f1_clear = f1_ci["ci_low"] > 0 or f1_ci["ci_high"] < 0
    acc_clear = acc_ci["ci_low"] > 0 or acc_ci["ci_high"] < 0
    if not f1_clear and not acc_clear:
        parts.append(
            "两个指标的 95% CI 都跨 0：在这 100 条样本上，神经模型与经典基线的差异"
            "与随机波动无法区分，不能宣称“效果更好”。"
        )
    elif delta_f1 > 0 and f1_ci["ci_low"] > 0:
        parts.append(
            "macro-F1 的 95% CI 不跨 0 且方向为正：该 test 集上神经模型优于经典基线；"
            "但 n=100，换一批样本仍可能翻转，别把小数点后第三位当结论。"
        )
    elif delta_f1 < 0 and f1_ci["ci_high"] < 0:
        parts.append(
            "macro-F1 的 95% CI 整体小于 0：经典基线反而更好。按事实写结论，不要美化。"
        )
    else:
        parts.append(
            "两个指标方向不完全一致（例如 accuracy 与 macro-F1 一涨一跌）："
            "说明提升集中在头部大类，对小类没有帮助；结论必须同时给出两个指标。"
        )
    return " ".join(parts)


# --------------------------------------------------------------------------- 报告
def _per_class_rows(metrics: dict, labels: list[str], jd: dict[str, dict]) -> list[dict]:
    rows = []
    for code in labels:
        pc = metrics["per_class"][code]
        info = jd.get(code, {})
        rows.append(
            {
                "code": code,
                "title_en": info.get("title_en", ""),
                "title_zh": info.get("title_zh", ""),
                "support": pc["support"],
                "precision": pc["precision"],
                "recall": pc["recall"],
                "f1": pc["f1"],
            }
        )
    return rows


def _write_confusion_csv(path: Path, metrics: dict, labels: list[str]) -> None:
    matrix = metrics["confusion_matrix"]
    lines = ["true\\pred," + ",".join(labels)]
    for i, label in enumerate(labels):
        lines.append(label + "," + ",".join(str(v) for v in matrix[i]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_per_class_csv(path: Path, rows: list[dict]) -> None:
    lines = ["code,title_en,title_zh,support,precision,recall,f1"]
    for r in rows:
        title_en = str(r["title_en"]).replace(",", " ")
        title_zh = str(r["title_zh"]).replace(",", " ")
        lines.append(
            f"{r['code']},{title_en},{title_zh},{r['support']},"
            f"{r['precision']:.6f},{r['recall']:.6f},{r['f1']:.6f}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _confusion_text(metrics: dict, labels: list[str], top_n: int = 5) -> list[str]:
    """人类可读的 24x24 混淆矩阵（只打印非零元素所在行，仍保留全表结构说明）。"""
    matrix = metrics["confusion_matrix"]
    width = max(len(label) for label in labels)
    lines = ["混淆矩阵（行=真实类别，列=预测类别；x 表示该行/列的非零交叉）:"]
    header = " " * (width + 2) + " ".join(f"{i:>2}" for i in range(len(labels)))
    lines.append(header)
    for i, label in enumerate(labels):
        row = matrix[i]
        cells = " ".join(f"{v:>2}" if v else " ." for v in row)
        lines.append(f"{label:<{width}}  {cells}  | {sum(row):>3}")
    lines.append("")
    lines.append(f"非零交叉明细（最多 {top_n * 4} 条，按次数降序）:")
    pairs = top_confusion_pairs(metrics, labels, k=top_n * 4)
    if not pairs:
        lines.append("  无（全部预测正确）")
    else:
        for p in pairs:
            lines.append(
                f"  {p['true']:<{width}} → {p['pred']:<{width}}  {p['count']:>3} 次"
                f"（占真实类 {p['share_of_true_class'] * 100:.0f}%）"
            )
    return lines


def _write_predictions(path: Path, examples: list[dict], preds: list[int], confidences, labels: list[str]) -> None:
    lines = ["id,true_category,pred_category,confidence,correct"]
    for ex, pred, conf in zip(examples, preds, confidences):
        lines.append(
            f"{ex['id']},{ex['category']},{labels[pred]},{conf:.6f},{int(pred == ex['label'])}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- 主流程
def evaluate_split(
    which: str,
    *,
    model_dir: str | Path,
    csv_path: str | Path = DEFAULT_CSV,
    split_path: str | Path = DEFAULT_SPLIT,
    out_dir: str | Path | None = None,
    batch_size: int = 16,
    max_length: int | None = None,
    device: str = "auto",
    seed: int = 42,
    use_baseline: bool = True,
    bootstrap_n: int = 1000,
    max_features: int = 200_000,
    allow_dry_run: bool = False,
    print_report: bool = True,
) -> dict:
    if which not in ("val", "test"):
        raise ValueError("which 只能是 val 或 test")
    csv_path = resolve_path(csv_path, DEFAULT_CSV)
    split_path = resolve_path(split_path, DEFAULT_SPLIT)
    model_path = resolve_path(model_dir)
    if not model_path.is_dir():
        raise FileNotFoundError(f"模型目录不存在: {model_path}")
    out_path = resolve_path(out_dir) if out_dir is not None else model_path.parent / f"eval-{which}"
    out_path.mkdir(parents=True, exist_ok=True)

    labels, label2id, _ = load_labels(split_path)
    target = build_examples(csv_path, split_path, which, labels=labels, label2id=label2id)
    stats = dataset_stats(target, labels)
    jd = load_jd_info(DEFAULT_JD)

    t0 = time.time()
    matcher = ResumeMatcher(
        model_path, device=device, max_length=max_length, allow_dry_run=allow_dry_run
    )
    probs = matcher.predict_proba([ex["text"] for ex in target], batch_size=batch_size)
    preds = [int(np.argmax(p)) for p in probs]
    confidences = [float(max(p)) for p in probs]
    neural_seconds = time.time() - t0
    y_true = [ex["label"] for ex in target]

    neural = compute_metrics(y_true, preds, labels)
    top_pairs = top_confusion_pairs(neural, labels, k=5)

    baseline_result = None
    baseline_main = None
    baseline_pred = None
    boot = {}
    if use_baseline:
        train = build_examples(csv_path, split_path, "train", labels=labels, label2id=label2id)
        baseline_result = fit_and_eval_baselines(
            [ex["text"] for ex in train],
            [ex["label"] for ex in train],
            [ex["text"] for ex in target],
            y_true,
            labels,
            seed=seed,
            max_features=max_features,
        )
        baseline_main = baseline_result["models"][baseline_result["main"]]
        baseline_pred = baseline_main["pred"]
        boot = paired_bootstrap(y_true, preds, baseline_pred, n_boot=bootstrap_n, seed=seed)

    # ---------------------------------------------------------------- 写产物
    per_class_rows = _per_class_rows(neural, labels, jd)
    _write_confusion_csv(out_path / "confusion_matrix.csv", neural, labels)
    (out_path / "confusion_matrix.txt").write_text(
        "\n".join(_confusion_text(neural, labels, top_n=10)) + "\n", encoding="utf-8"
    )
    _write_per_class_csv(out_path / "per_class.csv", per_class_rows)
    _write_predictions(out_path / "predictions.csv", target, preds, confidences, labels)

    result = {
        "split": which,
        "n": len(target),
        "dataset": stats,
        "model_dir": str(model_path),
        "model_version": matcher.model_version,
        "device": matcher.device,
        "max_length": matcher.max_length,
        "neural": neural,
        "neural_inference_seconds": neural_seconds,
        "top_confusions": top_pairs,
        "baseline": baseline_result,
        "bootstrap": boot,
        "note": (
            "best checkpoint 是按 val macro-F1 选出的，因此 val 指标偏乐观；"
            "对外结论请用 test 集。"
            if which == "val"
            else "test 集不参与任何选择，是唯一可作为对外结论的指标。"
        ),
    }
    write_json(out_path / "metrics.json", result)

    lines: list[str] = []
    add = lines.append
    add("=" * 78)
    add(f"  简历-岗位匹配 · {which} 集评估")
    add("=" * 78)
    add(f"checkpoint    : {model_path}")
    add(f"model_version : {matcher.model_version}")
    add(f"split         : {which}（n={len(target)}，{len(labels)} 类）")
    add(f"样本覆盖      : {len(labels) - len(stats['missing_classes'])}/{len(labels)} 类"
        + (f"；缺失: {stats['missing_classes']}" if stats["missing_classes"] else ""))
    add(f"device        : {matcher.device}，max_length={matcher.max_length}")
    add(f"推理耗时      : {format_duration(neural_seconds)}")
    add("")
    add("指标对比")
    add(f"{'指标':<14}{'神经模型':>10}{'经典基线':>12}{'差值(神经-经典)':>18}")
    for key, name in (("accuracy", "accuracy"), ("macro_f1", "macro-F1"), ("weighted_f1", "weighted-F1")):
        if baseline_main is None:
            add(f"{name:<14}{neural[key]:>10.4f}{'—':>12}{'—':>18}")
        else:
            diff = neural[key] - baseline_main["metrics"][key]
            add(f"{name:<14}{neural[key]:>10.4f}{baseline_main['metrics'][key]:>12.4f}{diff:>+18.4f}")
    if baseline_result is not None:
        add("")
        add(
            f"基线: TF-IDF(1-2gram, min_df={baseline_result['vectorizer']['min_df']}, "
            f"{baseline_result['vectorizer']['n_features_actual']} 维) + "
            f"{baseline_main['estimator']}（主基线，按 macro-F1 选；另一模型 "
            + ", ".join(
                f"{v['estimator']} macro-F1={v['metrics']['macro_f1']:.4f}"
                for k, v in baseline_result["models"].items()
                if k != baseline_result["main"]
            )
            + "）"
        )
        add(f"耗时: 向量化 {baseline_result['vectorizer']['fit_seconds']:.1f}s，"
            f"基线拟合 {baseline_main['fit_seconds']:.1f}s")
    add("")
    add("结论（自动生成，按数字说话）")
    if baseline_main is None:
        add("  已关闭经典基线（--no-baseline），无法做对照。")
    else:
        for chunk in _verdict(neural, baseline_main["metrics"], boot).split("。"):
            if chunk.strip():
                add("  " + chunk.strip() + "。")
    add(f"  说明: {result['note']}")
    add("")
    add("类别不平衡诊断")
    add("  被误判最多的 5 组混淆对（真实 → 预测）:")
    if not top_pairs:
        add("    无（全部预测正确）")
    else:
        for p in top_pairs:
            true_zh = jd.get(p["true"], {}).get("title_zh", "")
            pred_zh = jd.get(p["pred"], {}).get("title_zh", "")
            add(
                f"    {p['true']:<24} ({true_zh}) → {p['pred']:<24} ({pred_zh})"
                f"  {p['count']:>3} 次，占真实类 {p['share_of_true_class'] * 100:>4.1f}%"
            )
    supported = [r for r in per_class_rows if r["support"] > 0]
    worst = sorted(supported, key=lambda r: (r["recall"], r["f1"]))[:3]
    if worst:
        add("  召回最低的类（小样本类的估计方差很大）:")
        for r in worst:
            add(
                f"    {r['code']:<24} support={r['support']:<3} "
                f"P={r['precision']:.3f} R={r['recall']:.3f} F1={r['f1']:.3f}"
            )
    add("")
    add("每类指标（support=该 split 内真实样本数）")
    add(f"{'code':<24}{'support':>8}{'precision':>11}{'recall':>9}{'f1':>9}")
    for r in per_class_rows:
        add(f"{r['code']:<24}{r['support']:>8}{r['precision']:>11.3f}{r['recall']:>9.3f}{r['f1']:>9.3f}")
    add("")
    add("混淆矩阵（完整 24x24，另见 confusion_matrix.csv）")
    lines.extend(_confusion_text(neural, labels, top_n=5))
    add("")
    add(f"产物目录: {out_path}")
    report = "\n".join(lines) + "\n"
    (out_path / "report.txt").write_text(report, encoding="utf-8")

    if print_report:
        print(report)
    return result
