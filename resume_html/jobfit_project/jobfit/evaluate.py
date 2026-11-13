"""评估：分类指标 + 两个业务方向各自的排序指标 + 置信度校准误差。"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import torch
from torch.utils.data import DataLoader

from .model import JobFitModel
from .utils import get_device


@torch.no_grad()
def collect_logits(model: JobFitModel, loader: DataLoader, device: torch.device | None = None
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    device = device or get_device("cpu")
    model.eval()
    logits, labels, rows = [], [], []
    for batch in loader:
        batch = {k: v.to(device) for k, v in batch.items()}
        logits.append(model(batch)["logits"].float().cpu().numpy())
        labels.append(batch["label"].cpu().numpy())
        rows.append(batch["row"].cpu().numpy())
    if not logits:
        return np.zeros((0, model.n_jobs), np.float32), np.zeros(0, np.int64), np.zeros(0, np.int64)
    return np.concatenate(logits), np.concatenate(labels), np.concatenate(rows)


def classification_metrics(logits: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    if len(labels) == 0:
        return {}
    pred = logits.argmax(1)
    n_classes = logits.shape[1]
    acc = float((pred == labels).mean())
    top3 = float(np.mean([labels[i] in np.argsort(-row)[:3] for i, row in enumerate(logits)]))
    ranks = np.array([1 + int((row > row[labels[i]]).sum()) for i, row in enumerate(logits)])
    mrr = float(np.mean(1.0 / ranks))
    f1s = []
    for c in range(n_classes):
        tp = int(((pred == c) & (labels == c)).sum())
        fp = int(((pred == c) & (labels != c)).sum())
        fn = int(((pred != c) & (labels == c)).sum())
        f1s.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return {"accuracy": acc, "top3_accuracy": top3, "macro_f1": float(np.mean(f1s)),
            "mrr": mrr, "mean_rank": float(ranks.mean())}


def ranking_report(logits: np.ndarray, labels: np.ndarray, id2label: Sequence[str],
                   x_values: Sequence[int] = (1, 5, 10)) -> dict:
    """「一岗多人」评估：固定岗位列，把该次测试集所有简历按该列打分排序，
    看前 x 名里有多少是真正的该岗位人才。"""
    n_jobs = logits.shape[1]
    max_x = max(x_values)
    p_at = {x: [] for x in x_values}
    ndcg_at = {x: [] for x in x_values}
    ap_all = []
    per_job = {}
    for j in range(min(n_jobs, len(id2label))):
        order = np.argsort(-logits[:, j])
        rel = (labels[order] == j).astype(np.int32)
        n_rel = int(rel.sum())
        if n_rel == 0:
            continue
        for x in x_values:
            hit = rel[:x]
            p_at[x].append(float(hit.sum() / x))
            dcg = float(np.sum(hit / np.log2(np.arange(2, x + 2))))
            idcg = float(np.sum(np.ones(min(x, n_rel)) / np.log2(np.arange(2, min(x, n_rel) + 2))))
            ndcg_at[x].append(dcg / idcg if idcg > 0 else 0.0)
        hits = 0
        prec = 0.0
        for i, v in enumerate(rel):
            if v:
                hits += 1
                prec += hits / (i + 1)
        ap_all.append(prec / n_rel)
        per_job[id2label[j]] = {"support": n_rel, "precision@10": p_at[10][-1]}
    out: dict = {"macro_ap": float(np.mean(ap_all)) if ap_all else 0.0,
                 "n_eval_jobs": len(ap_all), "per_job": per_job}
    for x in x_values:
        out[f"precision@{x}"] = float(np.mean(p_at[x])) if p_at[x] else 0.0
        out[f"ndcg@{x}"] = float(np.mean(ndcg_at[x])) if ndcg_at[x] else 0.0
    return out


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, bins: int = 10) -> float:
    """ECE：预测置信度与实际命中率的平均偏差。"""
    conf = probs.max(1)
    pred = probs.argmax(1)
    ece = 0.0
    edges = np.linspace(0, 1, bins + 1)
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.sum():
            ece += m.mean() * abs(float((pred[m] == labels[m]).mean()) - float(conf[m].mean()))
    return float(ece)


def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    z = x - x.max(axis=axis, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=axis, keepdims=True)
