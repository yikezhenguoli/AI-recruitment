#!/usr/bin/env python3
"""24 类简历-岗位匹配的训练脚本（单卡/CPU 均可）。

设计要点：
  * 读固定划分 splits/split.csv，绝不重新划分；类别顺序 = sorted(category)。
  * 每 epoch 在 val 上算 accuracy 与 macro-F1，按 macro-F1 保存 best（24 类不平衡）。
  * label smoothing + warmup + 梯度裁剪 + 早停，随机种子全固定。
  * 日志写 runs/<timestamp>/train.log，每 epoch 覆写 metrics.json。
  * --dry-run 用 16 条训练样本跑通"数据→前向→反向→验证→保存"整条链路；
    默认先尝试真实模型，加载失败时（仅 dry-run）回落到随机初始化的微型 BERT，
    并打印醒目提示——绝不静默拿随机权重冒充训练结果。

用法示例：
    python train.py --csv ... --split ... --model-name microsoft/deberta-v3-base \
        --epochs 5 --batch-size 8 --grad-accum 2 --fp16
    python train.py --dry-run            # 本机无 GPU / 无网络时验证代码路径
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import math
import re
import sys
import time
import zlib
from pathlib import Path

# 让脚本在任意 cwd 下都能 import 同目录的 common.py（`python -I` 也能工作）
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import torch
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, Dataset
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        BertConfig,
        BertForSequenceClassification,
        get_linear_schedule_with_warmup,
    )
except ImportError as exc:  # pragma: no cover - 依赖缺失时的清晰提示
    print(
        f"train.py 需要 torch / transformers：{type(exc).__name__}: {exc}\n"
        "请先执行 `pip install -r requirements-train.txt`（建议 venv，见 README-train.md）。\n"
        "若只想检查代码路径，装好依赖后用 `python train.py --dry-run`。",
        file=sys.stderr,
    )
    raise SystemExit(3) from exc

from common import (  # noqa: E402  （必须在 sys.path 调整之后）
    DEFAULT_CSV,
    DEFAULT_SPLIT,
    build_examples,
    compute_metrics,
    dataset_stats,
    format_duration,
    load_labels,
    resolve_path,
    set_seed,
    time_tag,
    write_json,
)

LOGGER = logging.getLogger("train")

HF_HINT = """\
无法加载模型/分词器：{name}
可能原因与处理：
  1) 服务器没有外网：把模型目录整体拷到服务器，用 --model-name /path/to/local/model
  2) 国内镜像：export HF_ENDPOINT=https://hf-mirror.com
     并 export HF_HUB_DISABLE_XET=1（镜像不代理 xet，否则可能 401/超时）
  3) 代理报错 "Unknown scheme for proxy URL 'socks://...'"：unset ALL_PROXY 或改成
     socks5://... 并安装 socksio；httpx 只认 socks5://
  4) 私有/限流模型：export HF_TOKEN=...
  5) DeBERTa-v3 需要 sentencepiece：pip install sentencepiece
本脚本不会自动回落到随机权重。只想验证链路请用 --dry-run。
"""


# --------------------------------------------------------------------------- 参数
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="24 类简历-岗位匹配：微调 DeBERTa/BERT（单卡 GPU 或 CPU）。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Resume.csv 路径")
    p.add_argument("--split", type=Path, default=DEFAULT_SPLIT, help="固定划分 split.csv 路径（只读）")
    p.add_argument("--model-name", default="microsoft/deberta-v3-base", help="HF 模型名或本地模型目录")
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--batch-size", type=int, default=8, help="单卡 batch size（不含梯度累积）")
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--max-length", type=int, default=512)
    p.add_argument("--out-dir", type=Path, default=None, help="默认 runs/<timestamp>/")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--fp16", action="store_true", help="CUDA 上启用 fp16 混合精度（CPU 自动忽略）")
    p.add_argument("--bf16", action="store_true",
                   help="CUDA 上启用 bf16 混合精度（比 fp16 稳，无需 GradScaler；A10/A100 等支持）")
    p.add_argument("--grad-accum", type=int, default=1, help="梯度累积步数")
    p.add_argument("--freeze-layers", type=int, default=0, help="冻结底部 N 层编码器；-1 冻结整个底座")
    p.add_argument("--dry-run", action="store_true", help="用 16 条样本跑通全链路（可无网络）")

    # 额外但实用的训练旋钮
    p.add_argument("--device", default="auto", help="auto/cpu/cuda/cuda:0")
    p.add_argument("--weight-decay", type=float, default=0.01)
    p.add_argument("--warmup-ratio", type=float, default=0.06)
    p.add_argument("--label-smoothing", type=float, default=0.1)
    p.add_argument("--max-grad-norm", type=float, default=1.0)
    p.add_argument("--patience", type=int, default=3, help="早停耐心（按 val macro-F1）")
    p.add_argument("--min-delta", type=float, default=5e-4, help="视为提升的最小 macro-F1 增量")
    p.add_argument("--class-weights", action="store_true", help="按训练集频次反比加权 CE，可能抬高 macro-F1")
    p.add_argument("--truncation", choices=("head", "head_tail"), default="head",
                   help="长简历截断方式；head_tail 保留开头与结尾（未经实测的启发式，建议在 val 上对比）")
    p.add_argument("--limit-train", type=int, default=None, help="调试用：只用 N 条训练样本")
    p.add_argument("--limit-val", type=int, default=None, help="调试用：只用 N 条验证样本")
    p.add_argument("--num-workers", type=int, default=0)
    p.add_argument("--log-every", type=int, default=50, help="每 N 个优化步打印一次训练进度")
    p.add_argument("--max-bad-steps", type=int, default=20,
                   help="loss 为 NaN/Inf 的步数超过该值就中止（0 表示不限）")
    p.add_argument("--dry-run-tiny", action="store_true",
                   help="dry-run 时直接使用随机微型模型，不尝试下载（完全离线）")
    return p


def setup_logging(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(out_dir / "train.log", mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    LOGGER.addHandler(fh)
    LOGGER.addHandler(sh)
    LOGGER.propagate = False


# ---------------------------------------------------------------------- 微型回落模型
class TinyHashTokenizer:
    """仅用于 --dry-run 的离线分词器。

    用 crc32 把词映射到固定词表（不依赖 Python 随机化 hash），保证同一文本每次得到
    同样的 id。它不是任何真实模型的分词器，保存出来的目录带 DRY_RUN.txt 标记，
    infer_cli 默认拒绝加载。
    """

    def __init__(self, vocab_size: int = 2048):
        self.vocab_size = int(vocab_size)
        self.pad_token = "[PAD]"
        self.pad_token_id = 0
        self.cls_token_id = 101
        self.sep_token_id = 102
        self.unk_token_id = 100
        self.model_input_names = ["input_ids", "attention_mask"]
        self._re = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9]")

    def __call__(self, texts, truncation=True, max_length=512, padding=False, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        limit = max(2, int(max_length or 512) - 2)
        all_ids = []
        for text in texts:
            tokens = self._re.findall(str(text).lower())
            if truncation:
                tokens = tokens[:limit]
            ids = [self.cls_token_id]
            ids += [1 + (zlib.crc32(tok.encode("utf-8")) % (self.vocab_size - 2)) for tok in tokens]
            ids.append(self.sep_token_id)
            all_ids.append(ids)
        return {
            "input_ids": all_ids,
            "attention_mask": [[1] * len(ids) for ids in all_ids],
        }

    def save_pretrained(self, out_dir):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "tiny_hash_tokenizer.json").write_text(
            json.dumps(
                {"type": "TinyHashTokenizer", "vocab_size": self.vocab_size,
                 "note": "dry-run 用的随机分词器，不能用于真实推理"},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )


def build_tiny_model(num_labels: int, max_length: int, seed: int):
    tokenizer = TinyHashTokenizer()
    config = BertConfig(
        vocab_size=tokenizer.vocab_size,
        hidden_size=64,
        num_hidden_layers=2,
        num_attention_heads=2,
        intermediate_size=128,
        max_position_embeddings=max(128, int(max_length) + 4),
        type_vocab_size=2,
        num_labels=num_labels,
    )
    torch.manual_seed(seed)
    model = BertForSequenceClassification(config)
    return tokenizer, model, "tiny-random-hash"


def load_tokenizer_and_model(args, num_labels: int):
    """返回 (tokenizer, model, short_name, is_tiny)。真实模型失败时绝不静默回落。"""
    if args.dry_run_tiny and not args.dry_run:
        raise SystemExit("--dry-run-tiny 只能和 --dry-run 一起用")

    if args.dry_run_tiny:
        LOGGER.warning("=" * 70)
        LOGGER.warning("--dry-run-tiny：使用随机初始化的微型 BERT，仅验证代码路径，权重没有任何意义")
        LOGGER.warning("=" * 70)
        tok, model, short = build_tiny_model(num_labels, args.max_length, args.seed)
        return tok, model, short, True

    try:
        tokenizer = None
        tokenizer_error: Exception | None = None
        for use_fast in (True, False):
            try:
                tokenizer = AutoTokenizer.from_pretrained(args.model_name, use_fast=use_fast)
                break
            except Exception as exc:  # noqa: BLE001 - 记录后尝试 slow tokenizer
                tokenizer_error = exc
        if tokenizer is None:
            raise tokenizer_error or RuntimeError("AutoTokenizer 加载失败")
        model = AutoModelForSequenceClassification.from_pretrained(
            args.model_name, num_labels=num_labels
        )
        # 部分镜像仓库（ModelScope 的 microsoft/deberta-v3-base 就是）把基座权重存成
        # fp16，from_pretrained 会照单全收；DeBERTa-v3 在 fp16 参数下前向直接出 NaN。
        # 半精度只能由 autocast 在算子级做，参数本身必须保持 fp32。
        if next(model.parameters()).dtype != torch.float32:
            LOGGER.warning(
                "基座权重是 %s，已强制转为 fp32（DeBERTa-v3 在 fp16 下会发散）",
                next(model.parameters()).dtype,
            )
            model = model.float()
        short = Path(str(args.model_name).rstrip("/")).name or "model"
        return tokenizer, model, short, False
    except Exception as exc:  # noqa: BLE001 - 要把原始错误带给用户
        if not args.dry_run:
            sys.stderr.write(
                HF_HINT.format(name=args.model_name)
                + f"\n底层错误: {type(exc).__name__}: {exc}\n"
            )
            raise SystemExit(3) from exc
        LOGGER.warning("=" * 70)
        LOGGER.warning("--dry-run：加载 %r 失败（%s: %s）", args.model_name, type(exc).__name__, exc)
        LOGGER.warning("回落到随机初始化的微型 BERT —— 只验证数据/训练/保存链路，权重无意义。")
        LOGGER.warning("要测试真实模型路径：联网后去掉 --dry-run-tiny，或 --model-name 指向本地模型目录。")
        LOGGER.warning("=" * 70)
        tok, model, short = build_tiny_model(num_labels, args.max_length, args.seed)
        return tok, model, short, True


# --------------------------------------------------------------------------- 数据
def encode_texts(tokenizer, texts: list[str], max_length: int, truncation_mode: str) -> list[dict]:
    """批量分词；head_tail 模式保留开头一半 + 结尾一半 token。"""
    features: list[dict] = []
    chunk_size = 256
    for start in range(0, len(texts), chunk_size):
        chunk = texts[start : start + chunk_size]
        if truncation_mode == "head":
            enc = tokenizer(
                chunk, truncation=True, max_length=max_length, padding=False, return_attention_mask=True
            )
            ids_batch, mask_batch = enc["input_ids"], enc["attention_mask"]
        else:
            enc = tokenizer(chunk, truncation=False, padding=False, return_attention_mask=True)
            ids_batch, mask_batch = [], []
            for ids in enc["input_ids"]:
                if len(ids) > max_length:
                    head = max_length // 2
                    ids = ids[:head] + ids[-(max_length - head):]
                ids_batch.append(ids)
                mask_batch.append([1] * len(ids))
        for ids, mask in zip(ids_batch, mask_batch):
            features.append({"input_ids": list(ids), "attention_mask": list(mask)})
    return features


class ResumeDataset(Dataset):
    def __init__(self, features: list[dict], labels: list[int]):
        if len(features) != len(labels):
            raise ValueError("features 与 labels 长度不一致")
        self.features = features
        self.labels = labels

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        item = dict(self.features[idx])
        item["labels"] = int(self.labels[idx])
        return item


def make_collate(pad_token_id: int):
    def collate(batch: list[dict]) -> dict:
        max_len = max(len(b["input_ids"]) for b in batch)
        input_ids = torch.full((len(batch), max_len), int(pad_token_id), dtype=torch.long)
        attention = torch.zeros((len(batch), max_len), dtype=torch.long)
        labels = torch.empty(len(batch), dtype=torch.long)
        for i, item in enumerate(batch):
            n = len(item["input_ids"])
            input_ids[i, :n] = torch.tensor(item["input_ids"], dtype=torch.long)
            attention[i, :n] = torch.tensor(item["attention_mask"], dtype=torch.long)
            labels[i] = int(item["labels"])
        return {"input_ids": input_ids, "attention_mask": attention, "labels": labels}

    return collate


# --------------------------------------------------------------------------- 设备/冻结
def resolve_device(device: str):
    requested = (device or "auto").lower()
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested.startswith("cuda") and not torch.cuda.is_available():
        LOGGER.warning("指定了 %s 但 CUDA 不可用，回落到 CPU", requested)
        return torch.device("cpu")
    return torch.device(requested)


def freeze_lower_layers(model, n: int) -> tuple[int, int]:
    """冻结底部 n 层（n<0 冻结整个底座），返回 (冻结层数, 冻结后剩余可训练参数)。"""
    if n == 0:
        return 0, sum(p.numel() for p in model.parameters() if p.requires_grad)
    base = getattr(model, "base_model", model)
    layers = None
    for attr in ("encoder", "transformer"):
        enc = getattr(base, attr, None)
        if enc is not None and hasattr(enc, "layer"):
            layers = enc.layer
            break
    if layers is None:
        raise SystemExit(
            "无法定位编码器层（既没有 base.encoder.layer 也没有 base.transformer.layer）；"
            "请把 --freeze-layers 设为 0。"
        )
    if n < 0 or n >= len(layers):
        for p in base.parameters():
            p.requires_grad = False
        frozen_layers = len(layers)
    else:
        emb = getattr(base, "embeddings", None)
        if emb is not None:
            for p in emb.parameters():
                p.requires_grad = False
        for layer in layers[:n]:
            for p in layer.parameters():
                p.requires_grad = False
        frozen_layers = n
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return frozen_layers, trainable


# --------------------------------------------------------------------------- 精度/优化器
def amp_context(enabled: bool, dtype=None):
    if not enabled:
        return contextlib.nullcontext()
    dtype = dtype or torch.float16
    try:
        return torch.amp.autocast("cuda", dtype=dtype)
    except TypeError:  # torch < 2.4
        return torch.cuda.amp.autocast(dtype=dtype)


def make_grad_scaler(enabled: bool):
    if not enabled:
        return None
    try:
        return torch.amp.GradScaler("cuda", enabled=True)
    except TypeError:  # torch < 2.4
        return torch.cuda.amp.GradScaler(enabled=True)


def build_optimizer(model, lr: float, weight_decay: float):
    no_decay = ("bias", "LayerNorm.weight", "LayerNorm.bias", "layer_norm.weight", "layer_norm.bias")
    decay, no_dec = [], []
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        (no_dec if any(nd in name for nd in no_decay) else decay).append(param)
    groups = []
    if decay:
        groups.append({"params": decay, "weight_decay": weight_decay})
    if no_dec:
        groups.append({"params": no_dec, "weight_decay": 0.0})
    return torch.optim.AdamW(groups, lr=lr)


# --------------------------------------------------------------------------- 训练/验证
def train_one_epoch(model, loader, optimizer, scheduler, scaler, device, use_amp, amp_dtype, args, class_weights, epoch):
    model.train()
    total_loss = 0.0
    seen = 0
    update_steps = 0
    bad_steps = 0
    t0 = time.time()
    optimizer.zero_grad(set_to_none=True)

    for step, batch in enumerate(loader):
        batch = {k: v.to(device, non_blocking=True) for k, v in batch.items()}
        labels = batch.pop("labels")
        with amp_context(use_amp, amp_dtype):
            logits = model(**batch).logits
            loss = F.cross_entropy(
                logits,
                labels,
                weight=class_weights,
                label_smoothing=args.label_smoothing,
            )
        # loss 一旦是 NaN/Inf，梯度范数也是 NaN，clip_grad_norm_ 拦不住，
        # 一次 optimizer.step 就能把全部参数写成 NaN。这里直接丢弃该步。
        if not bool(torch.isfinite(loss).all()):
            bad_steps += 1
            optimizer.zero_grad(set_to_none=True)
            if bad_steps <= 5 or bad_steps % 50 == 0:
                LOGGER.warning("step %d/%d loss=%s 非有限，跳过该步（累计 %d 次）",
                               step + 1, len(loader), float(loss), bad_steps)
            if args.max_bad_steps and bad_steps > args.max_bad_steps:
                raise SystemExit(
                    f"累计 {bad_steps} 步 loss 为 NaN/Inf，训练已发散。"
                    "请去掉 --fp16/--bf16 按 fp32 重跑，并核对基座权重是否为 fp16。"
                )
            continue
        scaled_loss = loss / args.grad_accum
        if scaler is not None:
            scaler.scale(scaled_loss).backward()
        else:
            scaled_loss.backward()

        is_last = step + 1 == len(loader)
        if (step + 1) % args.grad_accum == 0 or is_last:
            if scaler is not None:
                try:
                    scaler.unscale_(optimizer)
                except ValueError as exc:
                    raise SystemExit(
                        "当前环境的 fp16 梯度缩放不可用（Attempting to unscale FP16 "
                        "gradients）。请改用 --bf16，或去掉精度参数按 fp32 训练。"
                    ) from exc
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
            if scaler is not None:
                scaler.step(optimizer)
                scaler.update()
            else:
                optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            update_steps += 1
            if args.log_every and update_steps % args.log_every == 0:
                lr_now = scheduler.get_last_lr()[0]
                LOGGER.info(
                    "  epoch %d | step %d/%d | loss %.4f | lr %.2e | %.1f samples/s",
                    epoch, step + 1, len(loader), loss.item(), lr_now,
                    seen / max(1e-9, time.time() - t0),
                )

        batch_size = labels.size(0)
        total_loss += loss.item() * batch_size
        seen += batch_size

    return total_loss / max(1, seen), update_steps


@torch.inference_mode()
def evaluate_model(model, loader, device, use_amp, amp_dtype):
    model.eval()
    total_loss = 0.0
    seen = 0
    y_true: list[int] = []
    y_pred: list[int] = []
    for batch in loader:
        batch = {k: v.to(device, non_blocking=True) for k, v in batch.items()}
        labels = batch.pop("labels")
        with amp_context(use_amp, amp_dtype):
            logits = model(**batch).logits
            loss = F.cross_entropy(logits, labels)
        pred = logits.argmax(dim=-1)
        total_loss += loss.item() * labels.size(0)
        seen += labels.size(0)
        y_true.extend(labels.detach().cpu().tolist())
        y_pred.extend(pred.detach().cpu().tolist())
    return total_loss / max(1, seen), y_true, y_pred


# --------------------------------------------------------------------------- 保存
def save_checkpoint(model, tokenizer, out_dir: Path, labels, label2id, args, run_id, model_version, is_tiny):
    # 存盘前兜底：NaN 权重能被 safetensors 正常写出，却在推理时全给同一个类，
    # 看起来"训练完成了"但完全没法用。宁可在这里失败。
    with torch.no_grad():
        broken = [n for n, p in model.named_parameters() if not torch.isfinite(p).all()]
    if broken:
        raise SystemExit(
            f"拒绝保存：{len(broken)}/{sum(1 for _ in model.parameters())} 个参数含 NaN/Inf"
            f"（例如 {broken[:3]}）。这份权重推理时只会输出同一个类别，不能交付。"
        )
    best_dir = out_dir / ("dryrun-best" if args.dry_run else "best")
    best_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(best_dir)
    tokenizer.save_pretrained(best_dir)

    label2id_path = out_dir / "label2id.json"
    id2label_path = out_dir / "id2label.json"
    write_json(label2id_path, label2id)
    write_json(id2label_path, {str(i): label for i, label in enumerate(labels)})
    # infer 时 model-dir 通常指向 best/，因此副本也放一份
    write_json(best_dir / "label2id.json", label2id)
    write_json(best_dir / "id2label.json", {str(i): label for i, label in enumerate(labels)})

    infer_config = {
        "model_version": model_version,
        "run_id": run_id,
        "base_model": args.model_name,
        "num_labels": len(labels),
        "labels": labels,
        "max_length": args.max_length,
        "truncation": args.truncation,
        "pooler": "cls",
        "is_dry_run": bool(args.dry_run or is_tiny),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_json(out_dir / "infer_config.json", infer_config)
    write_json(best_dir / "infer_config.json", infer_config)
    model_version_doc = {
        "model_version": model_version,
        "run_id": run_id,
        "base_model": args.model_name,
        "is_dry_run": bool(args.dry_run or is_tiny),
        "created_at": infer_config["created_at"],
    }
    write_json(out_dir / "model_version.json", model_version_doc)
    write_json(best_dir / "model_version.json", model_version_doc)

    if args.dry_run or is_tiny:
        for target in (out_dir, best_dir):
            (target / "DRY_RUN.txt").write_text(
                "本目录由 --dry-run / 微型随机模型生成，权重没有训练意义，不能用于推理。\n"
                "infer_cli.py 默认拒绝加载该目录（除非显式 --allow-dry-run）。\n",
                encoding="utf-8",
            )
    return best_dir


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.epochs < 1 or args.batch_size < 1 or args.grad_accum < 1:
        raise SystemExit("--epochs/--batch-size/--grad-accum 必须 >= 1")
    if not 16 <= args.max_length <= 4096:
        raise SystemExit("--max-length 应在 16..4096")
    if args.freeze_layers < -1:
        raise SystemExit("--freeze-layers 取 0、正整数或 -1")

    csv_path = resolve_path(args.csv, DEFAULT_CSV)
    split_path = resolve_path(args.split, DEFAULT_SPLIT)
    labels, label2id, _ = load_labels(split_path)

    # dry-run：16 条训练、16 条验证、64 token、1 epoch、小 batch
    limit_train = args.limit_train
    limit_val = args.limit_val
    if args.dry_run:
        limit_train = 16 if limit_train is None else min(limit_train, 16)
        limit_val = 16 if limit_val is None else min(limit_val, 16)
        args.epochs = min(args.epochs, 1)
        args.batch_size = min(args.batch_size, 4)
        args.max_length = min(args.max_length, 64)
        args.log_every = min(args.log_every, 10)

    set_seed(args.seed)

    out_dir = (
        resolve_path(args.out_dir)
        if args.out_dir is not None
        else (Path(__file__).resolve().parent / "runs" / (f"dryrun-{time_tag()}" if args.dry_run else time_tag()))
    )
    setup_logging(out_dir)
    run_id = out_dir.name

    LOGGER.info("=" * 70)
    LOGGER.info("简历-岗位匹配训练%s", "（DRY-RUN）" if args.dry_run else "")
    LOGGER.info("csv          : %s", csv_path)
    LOGGER.info("split        : %s", split_path)
    LOGGER.info("out_dir      : %s", out_dir)
    LOGGER.info("model_name   : %s", args.model_name)
    LOGGER.info("classes      : %d -> %s", len(labels), labels)
    LOGGER.info("args         : epochs=%d batch=%d grad_accum=%d lr=%g max_len=%d fp16=%s bf16=%s "
                "freeze=%d truncation=%s label_smoothing=%g",
                args.epochs, args.batch_size, args.grad_accum, args.lr, args.max_length,
                args.fp16, args.bf16, args.freeze_layers, args.truncation, args.label_smoothing)

    train_examples = build_examples(
        csv_path, split_path, "train", labels=labels, label2id=label2id, limit=limit_train, seed=args.seed
    )
    val_examples = build_examples(
        csv_path, split_path, "val", labels=labels, label2id=label2id, limit=limit_val, seed=args.seed
    )
    train_stats = dataset_stats(train_examples, labels)
    val_stats = dataset_stats(val_examples, labels)
    LOGGER.info("train n=%d  val n=%d", len(train_examples), len(val_examples))
    if train_stats["missing_classes"]:
        LOGGER.warning("训练集缺少类别（训练会照常进行）: %s", train_stats["missing_classes"])
    if val_stats["missing_classes"]:
        LOGGER.warning("验证集缺少类别（macro-F1 会把这些类算 0）: %s", val_stats["missing_classes"])

    device = resolve_device(args.device)
    if args.fp16 and args.bf16:
        raise SystemExit("--fp16 与 --bf16 只能选一个")
    use_fp16 = bool(args.fp16 and device.type == "cuda")
    use_bf16 = bool(args.bf16 and device.type == "cuda")
    if args.fp16 and not use_fp16:
        LOGGER.warning("--fp16 只在 CUDA 上启用；当前 device=%s，已自动关闭", device)
    if args.bf16 and not use_bf16:
        LOGGER.warning("--bf16 只在 CUDA 上启用；当前 device=%s，已自动关闭", device)
    use_amp = use_fp16 or use_bf16
    amp_dtype = torch.bfloat16 if use_bf16 else torch.float16
    LOGGER.info("device=%s  amp=%s", device,
                "bf16" if use_bf16 else "fp16" if use_fp16 else "off")

    tokenizer, model, short_name, is_tiny = load_tokenizer_and_model(args, len(labels))
    model.config.problem_type = "single_label_classification"
    model.config.label_smoothing_factor = 0.0  # 损失用我们自己的 label smoothing
    model.config.id2label = {i: label for i, label in enumerate(labels)}
    model.config.label2id = dict(label2id)

    if tokenizer.pad_token is None:
        fallback = tokenizer.eos_token or tokenizer.unk_token
        if fallback is None:
            raise SystemExit("tokenizer 没有 pad/eos/unk token，无法 padding")
        tokenizer.pad_token = fallback
    pad_token_id = int(tokenizer.pad_token_id if tokenizer.pad_token_id is not None else 0)

    frozen_layers, trainable = 0, sum(p.numel() for p in model.parameters())
    if args.freeze_layers:
        frozen_layers, trainable = freeze_lower_layers(model, args.freeze_layers)
        LOGGER.info("已冻结底部 %d 层编码器；可训练参数 %.2fM", frozen_layers, trainable / 1e6)
    else:
        LOGGER.info("可训练参数 %.2fM", trainable / 1e6)

    model.to(device)
    model_version = f"{short_name}@{run_id}"
    LOGGER.info("model_version: %s%s", model_version, "（随机微型模型，仅供冒烟测试）" if is_tiny else "")

    t_enc = time.time()
    train_features = encode_texts(tokenizer, [e["text"] for e in train_examples], args.max_length, args.truncation)
    val_features = encode_texts(tokenizer, [e["text"] for e in val_examples], args.max_length, args.truncation)
    LOGGER.info("分词完成（%.1fs）；平均 token 数 train=%.0f val=%.0f", time.time() - t_enc,
                sum(len(f["input_ids"]) for f in train_features) / max(1, len(train_features)),
                sum(len(f["input_ids"]) for f in val_features) / max(1, len(val_features)))

    collate = make_collate(pad_token_id)
    generator = torch.Generator()
    generator.manual_seed(args.seed)
    train_loader = DataLoader(
        ResumeDataset(train_features, [e["label"] for e in train_examples]),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        collate_fn=collate,
        generator=generator,
        pin_memory=device.type == "cuda",
    )
    val_loader = DataLoader(
        ResumeDataset(val_features, [e["label"] for e in val_examples]),
        batch_size=max(4, args.batch_size),
        shuffle=False,
        num_workers=args.num_workers,
        collate_fn=collate,
        pin_memory=device.type == "cuda",
    )

    class_weights = None
    if args.class_weights:
        counts = torch.bincount(
            torch.tensor([e["label"] for e in train_examples]), minlength=len(labels)
        ).float()
        weights = counts.sum() / (len(labels) * counts.clamp(min=1.0))
        class_weights = weights.to(device)
        LOGGER.info("启用 class weights: min=%.2f max=%.2f", weights.min().item(), weights.max().item())

    optimizer = build_optimizer(model, args.lr, args.weight_decay)
    steps_per_epoch = math.ceil(len(train_loader) / args.grad_accum)
    total_steps = max(1, steps_per_epoch * args.epochs)
    warmup_steps = int(total_steps * args.warmup_ratio)
    scheduler = get_linear_schedule_with_warmup(optimizer, warmup_steps, total_steps)
    scaler = make_grad_scaler(use_fp16)
    LOGGER.info("优化步数: %d（warmup %d）", total_steps, warmup_steps)

    metrics_state = {
        "run_id": run_id,
        "model_name": args.model_name,
        "short_name": short_name,
        "model_version": model_version,
        "seed": args.seed,
        "device": str(device),
        "dry_run": bool(args.dry_run),
        "is_tiny_model": bool(is_tiny),
        "labels": labels,
        "dataset": {"train": train_stats, "val": val_stats},
        "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "epochs": [],
        "best_epoch": None,
        "best_val_macro_f1": None,
        "stopped_early": False,
        "total_train_seconds": None,
    }
    write_json(out_dir / "metrics.json", metrics_state)

    best_f1 = -1.0
    best_epoch = None
    bad_epochs = 0
    best_dir = out_dir / ("dryrun-best" if args.dry_run else "best")
    train_start = time.time()

    for epoch in range(1, args.epochs + 1):
        epoch_start = time.time()
        LOGGER.info("-" * 70)
        LOGGER.info("epoch %d/%d", epoch, args.epochs)
        train_loss, update_steps = train_one_epoch(
            model, train_loader, optimizer, scheduler, scaler, device, use_amp, amp_dtype,
            args, class_weights, epoch
        )
        val_loss, y_true, y_pred = evaluate_model(model, val_loader, device, use_amp, amp_dtype)
        val_metrics = compute_metrics(y_true, y_pred, labels)
        elapsed = time.time() - epoch_start
        LOGGER.info(
            "epoch %d | train_loss %.4f | val_loss %.4f | val_acc %.4f | val_macro_f1 %.4f "
            "| val_weighted_f1 %.4f | %.1fs | optim_steps %d",
            epoch, train_loss, val_loss, val_metrics["accuracy"], val_metrics["macro_f1"],
            val_metrics["weighted_f1"], elapsed, update_steps,
        )

        improved = val_metrics["macro_f1"] > best_f1 + args.min_delta
        if improved:
            best_f1 = val_metrics["macro_f1"]
            best_epoch = epoch
            bad_epochs = 0
            best_dir = save_checkpoint(
                model, tokenizer, out_dir, labels, label2id, args, run_id, model_version, is_tiny
            )
            LOGGER.info("  ✓ 新的 best（val macro-F1=%.4f）已保存到 %s", best_f1, best_dir)
        else:
            bad_epochs += 1
            LOGGER.info("  val macro-F1 未提升（best=%.4f，连续 %d 个 epoch）", best_f1, bad_epochs)

        metrics_state["epochs"].append(
            {
                "epoch": epoch,
                "train_loss": train_loss,
                "val_loss": val_loss,
                "val_accuracy": val_metrics["accuracy"],
                "val_macro_f1": val_metrics["macro_f1"],
                "val_weighted_f1": val_metrics["weighted_f1"],
                "elapsed_seconds": elapsed,
                "optimizer_steps": update_steps,
                "lr_end": scheduler.get_last_lr()[0],
                "improved": improved,
            }
        )
        metrics_state["best_epoch"] = best_epoch
        metrics_state["best_val_macro_f1"] = best_f1 if best_epoch is not None else None
        write_json(out_dir / "metrics.json", metrics_state)

        if bad_epochs >= args.patience:
            LOGGER.info("早停：连续 %d 个 epoch 无提升（patience=%d）", bad_epochs, args.patience)
            metrics_state["stopped_early"] = True
            break

    total_seconds = time.time() - train_start
    metrics_state["total_train_seconds"] = total_seconds
    metrics_state["best_dir"] = str(best_dir)
    write_json(out_dir / "metrics.json", metrics_state)

    LOGGER.info("=" * 70)
    LOGGER.info("训练结束：best epoch=%s  val macro-F1=%.4f  用时 %s",
                best_epoch, best_f1, format_duration(total_seconds))
    LOGGER.info("best: %s", best_dir)
    if args.dry_run or is_tiny:
        LOGGER.warning("本次是 DRY-RUN / 随机微型模型，best 目录含 DRY_RUN.txt，不能用于推理。")
    LOGGER.info("下一步：python val.py --model-dir %s", best_dir)
    LOGGER.info("        python test.py --model-dir %s", best_dir)
    LOGGER.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
