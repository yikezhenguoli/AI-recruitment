"""训练入口：AdamW + 预热余弦调度 + 早停 + 温度/Platt 校准 + 自包含 checkpoint。"""
from __future__ import annotations

import copy
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

from .calibrate import Calibrator
from .config import NUMERIC_NAMES, Config
from .data import Corpus
from .dataset import batch_to_device, make_loader
from .evaluate import (classification_metrics, collect_logits,
                       expected_calibration_error, ranking_report, softmax)
from .losses import class_weights, compute_loss
from .model import JobFitModel
from .utils import (AverageMeter, ensure_dir, get_device, get_logger,
                    save_json, seconds_to_str, set_seed)

LOG = get_logger()
import time  # noqa: E402


def build_model(cfg: Config, corpus: Corpus, device: torch.device) -> JobFitModel:
    model = JobFitModel(cfg, vocab_size=len(corpus.vocab), n_jobs=corpus.n_jobs,
                        numeric_dim=len(NUMERIC_NAMES))
    model.set_job_text(corpus.job_arrays)
    return model.to(device)


def _scheduler(optimizer: torch.optim.Optimizer, total_steps: int, warmup: float):
    warm = max(1, int(total_steps * warmup))

    def rate(step: int) -> float:
        if step < warm:
            return (step + 1) / warm
        p = (step - warm) / max(1, total_steps - warm)
        return 0.5 * (1 + math.cos(math.pi * min(1.0, p)))

    return torch.optim.lr_scheduler.LambdaLR(optimizer, rate)


def train(cfg: Config, corpus: Corpus | None = None,
          data_dir: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    set_seed(cfg.seed)
    device = get_device(cfg.device)
    corpus = corpus or Corpus.build(cfg, data_dir)
    out_dir = ensure_dir(cfg.out_dir)
    model = build_model(cfg, corpus, device)
    LOG.info("模型参数量 %.2fM，设备 %s", sum(p.numel() for p in model.parameters()) / 1e6, device)

    loaders = {s: make_loader(corpus, s, cfg) for s in ("train", "val", "test")}
    weights = None
    if cfg.balanced:
        y_train = torch.as_tensor(corpus.label_array[corpus.splits["train"]], dtype=torch.long)
        weights = class_weights(y_train, corpus.n_jobs).to(device)

    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    total_steps = max(1, cfg.epochs * max(1, len(loaders["train"])))
    sch = _scheduler(opt, total_steps, cfg.warmup_ratio)

    best_state: dict | None = None
    best_score = -1.0
    best_epoch = 0
    bad = 0
    history: list[dict[str, float]] = []
    t0 = time.time()

    for epoch in range(1, cfg.epochs + 1):
        model.train()
        meter = AverageMeter()
        for step, batch in enumerate(loaders["train"], 1):
            batch = batch_to_device(batch, device)
            opt.zero_grad(set_to_none=True)
            out = model(batch)
            loss, parts = compute_loss(out, batch, cfg, weights)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sch.step()
            meter.add(parts["total"], len(batch["label"]))
            if cfg.log_every and step % cfg.log_every == 0:
                LOG.info("  epoch %d step %d/%d loss %.4f", epoch, step,
                         len(loaders["train"]), meter.avg)
        v_logits, v_labels, _ = collect_logits(model, loaders["val"], device)
        vm = classification_metrics(v_logits, v_labels)
        selection = 0.5 * vm.get("accuracy", 0) + 0.5 * vm.get("macro_f1", 0)
        rec = {"epoch": epoch, "train_loss": meter.avg, **vm, "selection": selection}
        history.append(rec)
        LOG.info("epoch %2d | loss %.4f | val acc %.3f f1 %.3f top3 %.3f | %s",
                 epoch, meter.avg, vm.get("accuracy", 0), vm.get("macro_f1", 0),
                 vm.get("top3_accuracy", 0), seconds_to_str(time.time() - t0))
        if selection > best_score + 1e-4:
            best_score, best_epoch, bad = selection, epoch, 0
            best_state = copy.deepcopy(model.state_dict())
        else:
            bad += 1
            if bad >= cfg.patience:
                LOG.info("早停：%d 轮无提升", bad)
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    LOG.info("最佳轮次 %d（selection %.4f）", best_epoch, best_score)

    # 校准只在验证集拟合
    v_logits, v_labels, _ = collect_logits(model, loaders["val"], device)
    calib = Calibrator().fit(v_logits, v_labels, corpus.n_jobs)
    LOG.info("校准 T=%.3f a=%.3f b=%.3f val_nll=%.4f",
             calib.T, calib.a, calib.b, calib.val_nll)

    # 测试集：分类 + 一岗多人排序
    t_logits, t_labels, t_rows = collect_logits(model, loaders["test"], device)
    test_cls = classification_metrics(t_logits, t_labels)
    test_rank = ranking_report(t_logits, t_labels, corpus.id2label, (1, 5, 10))
    probs = softmax(calib.z(t_logits))
    test_cls["ece"] = expected_calibration_error(probs, t_labels)
    test_report = {"classification": test_cls, "candidate_ranking": test_rank,
                   "n_test": int(len(t_labels))}
    LOG.info("测试集 acc %.3f macro-f1 %.3f top3 %.3f | 选人 P@10 %.3f nDCG@10 %.3f MAP %.3f",
             test_cls.get("accuracy", 0), test_cls.get("macro_f1", 0),
             test_cls.get("top3_accuracy", 0), test_rank.get("precision@10", 0),
             test_rank.get("ndcg@10", 0), test_rank.get("macro_ap", 0))

    ckpt: dict[str, Any] = {
        "model": model.state_dict(),
        "cfg": cfg.to_dict(),
        "vocab": corpus.vocab.to_dict(),
        "label2id": corpus.label2id,
        "id2label": corpus.id2label,
        "jobs": [asdict(j) for j in corpus.jobs],
        "splits": corpus.splits,
        "num_mean": corpus.num_mean,
        "num_std": corpus.num_std,
        "numeric_names": NUMERIC_NAMES,
        "X_ids": corpus.X_ids.astype(np.int32),
        "X_w": corpus.X_w,
        "X_seg": corpus.X_seg.astype(np.int32),
        "X_num": corpus.X_num,
        "meta": corpus.meta(),
        "calibrator": calib.to_dict(),
        "metrics": test_report,
        "best_epoch": best_epoch,
        "n_segments": model.resume_te.seg_emb.num_embeddings,
    }
    ckpt_path = out_dir / "jobfit.ckpt"
    torch.save(ckpt, ckpt_path)
    save_json({"history": history, "test": test_report, "corpus": corpus.summary(),
               "calibrator": calib.to_dict(), "best_epoch": best_epoch},
              out_dir / "training_report.json")
    LOG.info("checkpoint -> %s (%.1f MB)", ckpt_path, ckpt_path.stat().st_size / 1e6)
    return ckpt_path, {"history": history, "test": test_report, "calibrator": calib.to_dict()}
