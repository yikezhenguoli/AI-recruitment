"""双塔岗位适配模型（PyTorch）。

简历塔 : 字段感知 TextCNN + tf-idf 加权池化 + 结构化数值特征  -> 归一化向量 r
岗位塔 : 可学习岗位原型 proto + 岗位文本编码器（伪 JD / 真实 JD）  -> 归一化向量 j
打分层 : cos(r,j)/learnable_temp + 交叉交互 MLP + 岗位先验偏置 -> logits[B, n_jobs]

同一个 logits 同时服务两个任务：
  一人多岗：取同一行、按列排序
  一岗多人：取同一列、按行排序
因此排序天然一致，不需要两套模型。
"""
from __future__ import annotations

import math
from typing import Sequence

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import Config
from .text import N_SEGMENTS


class TextEncoder(nn.Module):
    """多卷积核 TextCNN + tf-idf 加权平均池化；seg 让模型知道每个词来自哪个简历字段。"""

    def __init__(self, vocab_size: int, n_seg: int, d_emb: int, d_model: int,
                 kernels: Sequence[int], dropout: float) -> None:
        super().__init__()
        self.emb = nn.Embedding(vocab_size, d_emb, padding_idx=0)
        self.seg_emb = nn.Embedding(n_seg, d_emb, padding_idx=0)
        self.convs = nn.ModuleList([nn.Conv1d(d_emb, d_emb, k, padding=k - 1)
                                    for k in kernels])
        self.drop = nn.Dropout(dropout)
        self.proj = nn.Sequential(
            nn.Linear(2 * d_emb, d_model), nn.LayerNorm(d_model), nn.Dropout(dropout)
        )

    def forward(self, ids: torch.Tensor, weights: torch.Tensor, seg: torch.Tensor,
                inputs_embeds: torch.Tensor | None = None) -> torch.Tensor:
        mask = (ids != 0).to(weights.dtype)                       # [B, L]
        x = self.emb(ids) if inputs_embeds is None else inputs_embeds
        x = self.drop(x + self.seg_emb(seg))
        w = weights * mask
        mean_pool = (x * w.unsqueeze(-1)).sum(1) / w.sum(1).clamp_min(1e-6).unsqueeze(-1)
        conv_in = x.transpose(1, 2)                               # [B, E, L]
        length = ids.size(1)
        pools = []
        for conv in self.convs:
            h = F.gelu(conv(conv_in))[:, :, :length]
            h = h.masked_fill((1 - mask).bool().unsqueeze(1), -1e4)
            pools.append(h.max(dim=2).values)
        cnn_pool = torch.stack(pools, dim=0).mean(0)
        out = self.proj(torch.cat([mean_pool, cnn_pool], dim=-1))
        return F.normalize(out, dim=-1)


class InteractionHead(nn.Module):
    """余弦尺度 + 交叉特征 MLP。初始时 deep 分支权重很小，等价于一个余弦分类器。"""

    def __init__(self, d_model: int, init_temp: float, dropout: float) -> None:
        super().__init__()
        self.log_temp = nn.Parameter(torch.tensor(math.log(max(0.01, init_temp))))
        self.mix = nn.Parameter(torch.tensor(-1.6))
        self.mlp = nn.Sequential(
            nn.Linear(4 * d_model, d_model), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(d_model, 1),
        )
        nn.init.normal_(self.mlp[-1].weight, std=0.01)
        nn.init.zeros_(self.mlp[-1].bias)

    def forward(self, r: torch.Tensor, j: torch.Tensor, bias: torch.Tensor) -> torch.Tensor:
        cos = r @ j.t()                                            # [B, M]
        B, M = cos.shape
        re = r.unsqueeze(1).expand(-1, M, -1)
        je = j.unsqueeze(0).expand(B, -1, -1)
        feats = torch.cat([re, je, re * je, (re - je).abs()], dim=-1)
        deep = self.mlp(feats).squeeze(-1)
        temp = self.log_temp.exp().clamp(0.02, 1.0)
        return cos / temp + torch.sigmoid(self.mix) * deep + bias.unsqueeze(0)

    def temperature(self) -> float:
        return float(self.log_temp.exp().clamp(0.02, 1.0).detach().cpu())


class JobFitModel(nn.Module):
    def __init__(self, cfg: Config, vocab_size: int, n_jobs: int,
                 numeric_dim: int, n_seg: int = N_SEGMENTS) -> None:
        super().__init__()
        self.cfg = cfg
        self.n_jobs = n_jobs
        self.resume_te = TextEncoder(vocab_size, n_seg, cfg.d_emb, cfg.d_model,
                                     cfg.cnn_kernels, cfg.dropout)
        self.job_te = TextEncoder(vocab_size, n_seg, cfg.d_emb, cfg.d_model,
                                  cfg.cnn_kernels, cfg.dropout)
        self.proto = nn.Embedding(n_jobs, cfg.d_model)
        nn.init.normal_(self.proto.weight, std=0.02)
        self.unk_proto = nn.Parameter(torch.zeros(1, cfg.d_model))
        self.gate = nn.Parameter(torch.tensor(0.0))               # sigmoid(0)=0.5
        self.num_mlp = nn.Sequential(nn.Linear(numeric_dim, cfg.d_model), nn.ReLU(),
                                     nn.Linear(cfg.d_model, cfg.d_model))
        self.num_gate = nn.Parameter(torch.tensor(0.0))
        self.head = InteractionHead(cfg.d_model, cfg.init_temp, cfg.dropout)
        self.job_bias = nn.Parameter(torch.zeros(n_jobs))
        self.unk_bias = nn.Parameter(torch.zeros(1))
        if cfg.use_score_supervision:
            self.score_head = nn.Sequential(nn.Linear(4 * cfg.d_model, cfg.d_model),
                                            nn.ReLU(), nn.Linear(cfg.d_model, 1))
        else:
            self.score_head = None
        self.register_buffer("job_txt_ids", torch.zeros(1, cfg.max_job_len, dtype=torch.long))
        self.register_buffer("job_txt_w", torch.zeros(1, cfg.max_job_len, dtype=torch.float))
        self.register_buffer("job_txt_seg", torch.zeros(1, cfg.max_job_len, dtype=torch.long))

    def set_job_text(self, arrays: Sequence) -> None:
        ids, w, seg = arrays
        self.job_txt_ids = torch.as_tensor(ids, dtype=torch.long)
        self.job_txt_w = torch.as_tensor(w, dtype=torch.float)
        self.job_txt_seg = torch.as_tensor(seg, dtype=torch.long)

    def encode_resume(self, ids: torch.Tensor, weights: torch.Tensor,
                      seg: torch.Tensor, numeric: torch.Tensor) -> torch.Tensor:
        t = self.resume_te(ids, weights, seg)
        n = F.normalize(self.num_mlp(numeric), dim=-1)
        return F.normalize(t + torch.sigmoid(self.num_gate) * n, dim=-1)

    def job_vectors(self, job_ids: torch.Tensor | None = None,
                    custom: Sequence[torch.Tensor] | None = None
                    ) -> tuple[torch.Tensor, torch.Tensor]:
        """返回 (岗位向量 [M,d], 先验偏置 [M])。custom 用于全新的 JD 文本。"""
        if custom is not None:
            t = self.job_te(*custom)
            p = self.unk_proto.expand(t.size(0), -1)
            bias = self.unk_bias.expand(t.size(0))
        else:
            if job_ids is None:
                job_ids = torch.arange(self.n_jobs, device=self.proto.weight.device)
            else:
                job_ids = torch.as_tensor(job_ids, dtype=torch.long,
                                          device=self.proto.weight.device)
            t = self.job_te(self.job_txt_ids[job_ids], self.job_txt_w[job_ids],
                            self.job_txt_seg[job_ids])
            p = F.normalize(self.proto(job_ids), dim=-1)
            bias = self.job_bias[job_ids]
        j = F.normalize(p + torch.sigmoid(self.gate) * t, dim=-1)
        return j, bias

    def forward(self, batch: dict[str, torch.Tensor],
                job_ids: torch.Tensor | list[int] | None = None,
                custom_job: Sequence[torch.Tensor] | None = None,
                return_vectors: bool = False) -> dict[str, torch.Tensor]:
        r = self.encode_resume(batch["ids"], batch["weights"], batch["seg"],
                               batch["numeric"])
        j, bias = self.job_vectors(job_ids, custom_job)
        logits = self.head(r, j, bias)
        out: dict[str, torch.Tensor] = {"logits": logits}
        if return_vectors:
            out["r"], out["j"] = r, j
        if self.score_head is not None and "label" in batch:
            y = batch["label"].clamp(max=j.size(0) - 1)
            jt = j[y]
            feat = torch.cat([r, jt, r * jt, (r - jt).abs()], dim=-1)
            out["pred_score"] = 100.0 * torch.sigmoid(self.score_head(feat).squeeze(-1))
        return out

    def score_vectors(self, r: torch.Tensor, j: torch.Tensor,
                      bias: torch.Tensor | None = None) -> torch.Tensor:
        if bias is None:
            bias = j.new_zeros(j.size(0))
        return self.head(r, j, bias)
