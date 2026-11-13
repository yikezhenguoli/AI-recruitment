"""把原始 logits 变成可解释的 0-100 适配分。

三步校准（都只在验证集上拟合，不碰测试集）：
  1) Temperature T：最小化验证集 NLL，修掉余弦温度带来的过度自信；
  2) 锚点 z_lo / z_hi：取验证集全配对 z=logit/T 的 1% / 99.9% 分位数，
     用于把 z 线性铺到 0-100（默认主分 spread）；
  3) Platt (a,b)：把 z 通过 sigmoid 映射成"正负均衡前提下真正匹配的概率"，
     乘 100 得到 match_probability（强匹配会饱和到 ~99.7，故不作默认主分）。

关键性质：所有分数都是 z 的严格单调函数，因此
  「一人多岗」按列排序 和「一岗多人」按行排序 用的是同一把尺子，可跨简历比较。

四种分数模式：
  spread(默认) 100*clip((z-z_lo)/(z_hi-z_lo))，z_lo/z_hi 取验证集 1% / 99.9% 分位数。
               非饱和、铺满 0-100，是最适合"具体打分"的适配分。
  platt        100*sigmoid(a*z+b)，严格意义上的"匹配概率×100"，强匹配会挤在 99 分附近。
  share        一人多岗时各岗位的置信度分配（同一行合计 100）。
  percentile   本次查询候选池内的相对百分位（适合 top-x 选人）。

无论用哪种模式，输出里都会附带 match_probability（platt×100）作为概率参考。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import torch
import torch.nn.functional as F

from .evaluate import softmax


@dataclass
class Calibrator:
    T: float = 1.0
    a: float = 1.0
    b: float = 0.0
    z_lo: float = -2.0
    z_hi: float = 7.0
    n_jobs: int = 24
    fitted: bool = False
    val_nll: float = 0.0
    history: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    def fit(self, logits: np.ndarray, labels: np.ndarray, n_jobs: int | None = None) -> "Calibrator":
        if n_jobs is not None:
            self.n_jobs = int(n_jobs)
        elif logits.ndim > 1:
            self.n_jobs = int(logits.shape[1])
        else:
            self.n_jobs = 24
        z = torch.as_tensor(np.asarray(logits, dtype=np.float32))
        y = torch.as_tensor(np.asarray(labels, dtype=np.int64))
        if z.numel() == 0:
            return self
        self.T = _fit_temperature(z, y)
        z_all = (z / self.T).detach().numpy().reshape(-1)
        self.z_lo = float(np.percentile(z_all, 1.0))
        self.z_hi = float(np.percentile(z_all, 99.9))
        if self.z_hi - self.z_lo < 1e-3:
            self.z_lo, self.z_hi = float(z_all.min()), float(z_all.max()) + 1.0
        zz = (z / self.T).reshape(-1)
        yy = (y[:, None] == torch.arange(z.size(1))[None, :]).float().reshape(-1)
        self.a, self.b = _fit_platt(zz, yy, pos_weight=max(1.0, z.size(1) - 1))
        self.a = max(0.05, abs(self.a))          # 保证严格单调
        self.val_nll = float(F.cross_entropy(z / self.T, y).item())
        self.fitted = True
        self.history = {"T": self.T, "a": self.a, "b": self.b,
                        "z_lo": self.z_lo, "z_hi": self.z_hi, "val_nll": self.val_nll}
        return self

    # ------------------------------------------------------------------ #
    def z(self, logits: np.ndarray) -> np.ndarray:
        return np.asarray(logits, dtype=np.float64) / self.T

    def platt(self, logits: np.ndarray) -> np.ndarray:
        v = self.a * self.z(logits) + self.b
        return 100.0 / (1.0 + np.exp(-np.clip(v, -60, 60)))

    def spread(self, logits: np.ndarray) -> np.ndarray:
        """非饱和百分制适配分：验证集分位数锚定的线性映射，严格单调、跨查询可比。"""
        u = (self.z(logits) - self.z_lo) / max(1e-3, self.z_hi - self.z_lo)
        return 100.0 * np.clip(u, 0.0, 1.0)

    def share(self, logits: np.ndarray) -> np.ndarray:
        return 100.0 * softmax(self.z(logits), axis=-1)

    def absolute(self, logits: np.ndarray, mode: str = "spread") -> np.ndarray:
        """返回与 logits 同形状的 0-100 绝对分（percentile 模式先返回其底分）。"""
        if mode == "platt":
            return self.platt(logits)
        if mode == "share":
            return self.share(logits)
        if mode in ("spread", "percentile") or not self.fitted:
            return self.spread(logits)
        raise ValueError(f"未知 score_mode: {mode}（可选 spread / platt / share / percentile）")

    def scores(self, logits: np.ndarray, mode: str = "spread") -> np.ndarray:
        base = self.absolute(logits, mode)
        if mode == "percentile":
            shape = base.shape
            return percentile_scores(base.reshape(-1)).reshape(shape)
        return base

    def to_dict(self) -> dict:
        return {"T": self.T, "a": self.a, "b": self.b,
                "z_lo": self.z_lo, "z_hi": self.z_hi, "n_jobs": self.n_jobs,
                "fitted": self.fitted, "val_nll": self.val_nll, "history": self.history}

    @classmethod
    def from_dict(cls, d: dict) -> "Calibrator":
        return cls(**{k: v for k, v in d.items()
                      if k in {"T", "a", "b", "z_lo", "z_hi", "n_jobs",
                               "fitted", "val_nll", "history"}})


def percentile_scores(values: np.ndarray) -> np.ndarray:
    """按候选集合内的经验分布映射到 0-100；并列值取平均百分位，保持单调。"""
    v = np.asarray(values, dtype=np.float64).reshape(-1)
    if v.size == 0:
        return v
    if v.size == 1:
        return np.array([100.0])
    order = np.argsort(v)
    ranks = np.empty(v.size, dtype=np.float64)
    sorted_v = v[order]
    i = 0
    while i < v.size:
        j = i
        while j + 1 < v.size and sorted_v[j + 1] == sorted_v[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return 100.0 * ranks / (v.size - 1)


def _fit_temperature(logits: torch.Tensor, labels: torch.Tensor,
                     lo_T: float = 0.1, hi_T: float = 20.0) -> float:
    def nll(logT: float) -> float:
        return float(F.cross_entropy(logits / math.exp(logT), labels).item())
    lo, hi = math.log(lo_T), math.log(hi_T)
    phi = (math.sqrt(5) - 1) / 2
    c, d = hi - phi * (hi - lo), lo + phi * (hi - lo)
    fc, fd = nll(c), nll(d)
    for _ in range(35):
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - phi * (hi - lo)
            fc = nll(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + phi * (hi - lo)
            fd = nll(d)
    return float(math.exp((lo + hi) / 2))


def _fit_platt(z: torch.Tensor, y: torch.Tensor, pos_weight: float,
               steps: int = 400) -> tuple[float, float]:
    a = torch.nn.Parameter(torch.tensor(1.0))
    b = torch.nn.Parameter(torch.tensor(0.0))
    opt = torch.optim.Adam([a, b], lr=0.05)
    pw = torch.tensor(float(pos_weight))
    for _ in range(steps):
        opt.zero_grad()
        loss = F.binary_cross_entropy_with_logits(a * z + b, y, pos_weight=pw)
        loss.backward()
        opt.step()
    return float(a.detach()), float(b.detach())
