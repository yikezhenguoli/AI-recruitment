"""训练目标：分类交叉熵 + 难负样本排序间隔 + 可选人工分数回归。

只用交叉熵也能学，但本项目的核心诉求是"排序"，因此加一项
硬负样本 margin loss，专门拉开 正类岗位 与 得分最高的几个错误岗位 的间距。
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import Config


def class_weights(labels: torch.Tensor, n_jobs: int, power: float = 0.5) -> torch.Tensor:
    """按频率倒数平方根加权：缓解 BPO(22) vs IT(120) 的不平衡，又不过度补偿。"""
    counts = torch.bincount(labels, minlength=n_jobs).float().clamp_min(1.0)
    w = (counts.mean() / counts).pow(power)
    return (w / w.mean()).to(labels.device)


def compute_loss(out: dict[str, torch.Tensor], batch: dict[str, torch.Tensor],
                 cfg: Config, weights: torch.Tensor | None = None
                 ) -> tuple[torch.Tensor, dict[str, float]]:
    logits, y = out["logits"], batch["label"]
    n_jobs = logits.size(1)
    parts: dict[str, float] = {}

    ce = F.cross_entropy(logits, y, weight=weights,
                         label_smoothing=cfg.label_smoothing)
    parts["ce"] = float(ce.detach())
    total = ce

    if cfg.margin_weight > 0 and n_jobs > 1:
        pos = logits.gather(1, y[:, None])
        neg = logits.masked_fill(F.one_hot(y, n_jobs).bool(), -1e4)
        k = min(3, n_jobs - 1)
        hard, _ = neg.topk(k, dim=1)
        ml = F.relu(cfg.margin - (pos - hard)).mean()
        total = total + cfg.margin_weight * ml
        parts["margin"] = float(ml.detach())

    if cfg.use_score_supervision and "pred_score" in out:
        mask = batch["score_mask"] > 0
        if mask.any():
            mse = F.mse_loss(out["pred_score"][mask], batch["score"][mask])
            total = total + 0.01 * mse
            parts["score_mse"] = float(mse.detach())

    parts["total"] = float(total.detach())
    return total, parts
