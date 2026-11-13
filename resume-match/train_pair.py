#!/usr/bin/env python3
"""简历-岗位配对匹配（cross-encoder）训练。

做法与 train.py 的分类任务不同：模型读的是
    [CLS] 简历 [SEP] 岗位 JD [SEP]
输出一个匹配概率。JD 因此真正进入前向计算，而不是像分类任务那样
只存在于后端的接口参数里。

训练样本：
  * 正配对 —— 简历 × 它所属类别的 JD，标签 1
  * 负配对 —— 简历 × 随机异类 JD，标签 0（每个正样本配 --neg-per-pos 条）

中文数据（translate_zh.py 产物）只进训练集，配中文 JD；
val/test 保持纯英文，配英文 JD，翻译体不参与任何对外指标。

早停口径：验证集上「一条简历 × 24 个 JD 的 24 选 1 排名」的 Recall@1。
这是 JD 真的参与打分的直接证据——若 JD 不参与，正确 JD 不可能排到第一。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

from common import (
    DEFAULT_CSV,
    DEFAULT_JD,
    DEFAULT_SPLIT,
    DataError,
    build_examples,
    format_duration,
    load_jd_info,
    load_labels,
    set_seed,
    time_tag,
    write_json,
)

ROOT = Path(__file__).resolve().parent

JD_FIELDS = ("responsibilities", "required_skills")


# --------------------------------------------------------------------------- JD 文本
def build_jd_text(job: dict, lang: str) -> str:
    """把 yaml 里的结构化字段拼成一段 JD 文本。

    刻意不含 summary_*：Job summary 只是一句岗位定义，而中文版常被写成一整段
    百科式介绍（实测 ACCOUNTANT 的 summary_zh 有 300+ 字），会让中英两个版本的
    长度严重不对称。title + 职责 + 技能 + 学历 + 年限 已足够区分 24 个岗位。
    """
    parts: list[str] = []
    title = str(job.get(f"title_{lang}") or "").strip()
    if title:
        parts.append(title)
    for field in JD_FIELDS:
        value = job.get(f"{field}_{lang}") or []
        if isinstance(value, str):
            value = [value]
        parts.extend(str(item).strip() for item in value if str(item).strip())
    education = str(job.get(f"education_{lang}") or "").strip()
    if education:
        parts.append(education)
    years = job.get("experience_years")
    if years:
        parts.append(f"{years} 年经验" if lang == "zh" else f"{years}+ years experience")
    return "\n".join(parts)


def load_jd_texts(jd_path: Path, codes: list[str]) -> dict[str, dict[str, str]]:
    info = load_jd_info(jd_path)
    missing = [code for code in codes if code not in info]
    if missing:
        raise DataError(f"{jd_path} 缺少这些类别的 JD: {missing}")
    out: dict[str, dict[str, str]] = {}
    for code in codes:
        out[code] = {
            lang: build_jd_text(info[code], lang) for lang in ("en", "zh")
        }
        if not out[code]["en"]:
            raise DataError(f"{code} 的英文 JD 拼出来是空的")
    return out


# --------------------------------------------------------------------------- 配对样本
@dataclass
class PairRecord:
    text_a: str
    text_b: str
    label: int
    code: str
    lang: str


def load_zh_records(path: Path, codes: set[str]) -> list[dict]:
    """读翻译产物；坏行直接报错（静默丢样本会让训练集与预期条数对不上）。"""
    if not path.is_file():
        raise DataError(f"找不到中文简历文件: {path}（先跑 translate_zh.py）")
    records: list[dict] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DataError(f"{path}:{lineno} 不是合法 JSON") from exc
        code = row.get("category")
        text = (row.get("zh") or "").strip()
        rid = row.get("id")
        if code not in codes:
            raise DataError(f"{path}:{lineno} 类别 {code!r} 不在 24 类里")
        if not text:
            raise DataError(f"{path}:{lineno} 译文为空")
        if rid in seen:
            continue
        seen.add(rid)
        records.append({"id": rid, "category": code, "text": text})
    if not records:
        raise DataError(f"{path} 里没有任何可用样本")
    return records


def augment_jd(text: str, rng: random.Random, dropout: float) -> str:
    """随机丢弃 JD 的非首行。

    不这么做的话，模型只需记住 24 段固定文本就能把正负配对分开；到了线上，
    JD 来自数据库、措辞与这 24 段都不一样，分数会失真。首行是岗位名，始终保留。
    """
    if dropout <= 0:
        return text
    lines = text.split("\n")
    kept = [lines[0]] + [line for line in lines[1:] if rng.random() >= dropout]
    return "\n".join(kept)


def build_train_pairs(
    en_examples: list[dict],
    zh_records: list[dict],
    jd_texts: dict[str, dict[str, str]],
    codes: list[str],
    neg_per_pos: int,
    rng: random.Random,
    jd_dropout: float,
) -> list[PairRecord]:
    pairs: list[PairRecord] = []

    def add(text: str, code: str, lang: str) -> None:
        pairs.append(PairRecord(text, augment_jd(jd_texts[code][lang], rng, jd_dropout),
                                1, code, lang))
        for _ in range(neg_per_pos):
            wrong = rng.choice([c for c in codes if c != code])
            pairs.append(PairRecord(text, augment_jd(jd_texts[wrong][lang], rng, jd_dropout),
                                    0, code, lang))

    for ex in en_examples:
        add(ex["text"], ex["category"], "en")
    for rec in zh_records:
        add(rec["text"], rec["category"], "zh")
    rng.shuffle(pairs)
    return pairs


class PairDataset(Dataset):
    def __init__(self, records: list[PairRecord], tokenizer, max_length: int):
        self.records = records
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict:
        rec = self.records[index]
        encoded = self.tokenizer(
            rec.text_a,
            rec.text_b,
            truncation="only_first",  # 简历太长时截简历，JD 保持完整
            max_length=self.max_length,
            padding=False,
            return_token_type_ids=False,  # DeBERTa-v2 的 type_vocab_size=0
        )
        encoded["labels"] = float(rec.label)
        return encoded


def collate(batch: list[dict], tokenizer) -> dict:
    features = [{k: v for k, v in item.items() if k != "labels"} for item in batch]
    padded = tokenizer.pad(features, padding=True, return_tensors="pt")
    padded["labels"] = torch.tensor([item["labels"] for item in batch], dtype=torch.float32)
    return padded


# --------------------------------------------------------------------------- 模型
def load_tokenizer_and_model(model_name: str):
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, num_labels=1, ignore_mismatched_sizes=True
    )
    # 同 train.py：ModelScope 的 deberta-v3-base 基座权重是 fp16，
    # DeBERTa-v3 在 fp16 参数下前向直接 NaN；半精度只能由 autocast 在算子级做。
    if next(model.parameters()).dtype != torch.float32:
        print(f"[warn] 基座权重是 {next(model.parameters()).dtype}，已强制转为 fp32")
        model = model.float()
    return tokenizer, model


def move_to(device: torch.device, batch: dict) -> dict:
    return {k: v.to(device) if torch.is_tensor(v) else v for k, v in batch.items()}


# --------------------------------------------------------------------------- 训练
def train_one_epoch(model, loader, optimizer, scheduler, device, args, epoch) -> dict:
    model.train()
    total_loss = 0.0
    steps = 0
    bad_steps = 0
    started = time.time()
    for step, batch in enumerate(loader, 1):
        batch = move_to(device, batch)
        labels = batch.pop("labels")
        if args.bf16:
            with torch.autocast(device_type=device.type, dtype=torch.bfloat16):
                logits = model(**batch).logits.squeeze(-1)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(
                logits.float(), labels
            )
        else:
            logits = model(**batch).logits.squeeze(-1)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, labels)

        if not bool(torch.isfinite(loss).all()):
            bad_steps += 1
            optimizer.zero_grad(set_to_none=True)
            if bad_steps <= 5 or bad_steps % 50 == 0:
                print(f"  [warn] epoch {epoch} step {step}/{len(loader)} loss 非有限，"
                      f"跳过（累计 {bad_steps} 次）")
            if args.max_bad_steps and bad_steps > args.max_bad_steps:
                raise SystemExit(
                    f"累计 {bad_steps} 步 loss 为 NaN/Inf，训练已发散。"
                    "请去掉 --bf16 按 fp32 重跑，并核对基座权重是否为 fp16。"
                )
            continue

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
        optimizer.step()
        scheduler.step()
        optimizer.zero_grad(set_to_none=True)

        total_loss += float(loss.detach())
        steps += 1
        if step % args.log_every == 0 or step == len(loader):
            rate = step / max(1e-9, time.time() - started)
            print(f"  epoch {epoch} {step}/{len(loader)} loss={total_loss / max(1, steps):.4f} "
                  f"lr={scheduler.get_last_lr()[0]:.2e} {rate:.2f} it/s", flush=True)
    return {
        "train_loss": total_loss / max(1, steps),
        "steps": steps,
        "bad_steps": bad_steps,
        "seconds": time.time() - started,
    }


@torch.no_grad()
def score_pairs(model, tokenizer, resumes: list[str], jd_texts: list[str],
                device, max_length: int, batch_size: int) -> torch.Tensor:
    """返回 [len(resumes), len(jd_texts)] 的匹配概率矩阵。"""
    model.eval()
    out = torch.zeros(len(resumes), len(jd_texts))
    # 扁平化成一维配对列表，避免重复构造 24 次同一批简历的嵌套结构
    flat_a = [text for text in resumes for _ in jd_texts]
    flat_b = [jd for _ in resumes for jd in jd_texts]
    for start in range(0, len(flat_a), batch_size):
        chunk_a = flat_a[start:start + batch_size]
        chunk_b = flat_b[start:start + batch_size]
        encoded = tokenizer(
            chunk_a, chunk_b, truncation="only_first", max_length=max_length,
            padding=True, return_tensors="pt", return_token_type_ids=False,
        )
        logits = model(**{k: v.to(device) for k, v in encoded.items()}).logits.squeeze(-1)
        probs = torch.sigmoid(logits.float()).cpu()
        out.view(-1)[start:start + len(chunk_a)] = probs
    return out


def evaluate_ranking(model, tokenizer, val_records: list[dict], jd_texts: dict[str, dict[str, str]],
                     codes: list[str], device, max_length: int, batch_size: int) -> dict:
    resumes = [rec["text"] for rec in val_records]
    jd_list = [jd_texts[code]["en"] for code in codes]
    probs = score_pairs(model, tokenizer, resumes, jd_list, device, max_length, batch_size)

    hits = {1: 0, 3: 0, 5: 0}
    rr_sum = 0.0
    margins: list[float] = []
    for i, rec in enumerate(val_records):
        true_index = codes.index(rec["category"])
        row = probs[i]
        order = torch.argsort(row, descending=True).tolist()
        rank = order.index(true_index) + 1
        for k in hits:
            if rank <= k:
                hits[k] += 1
        rr_sum += 1.0 / rank
        others = torch.cat([row[:true_index], row[true_index + 1:]])
        margins.append(float(row[true_index] - others.mean()))

    n = len(val_records)
    return {
        "n": n,
        "recall_at_1": hits[1] / n,
        "recall_at_3": hits[3] / n,
        "recall_at_5": hits[5] / n,
        "mrr": rr_sum / n,
        # 负配对敏感性：正配概率减掉其余 23 个 JD 的平均概率。
        # 若 JD 没真正参与打分，这个差值会贴近 0。
        "mean_margin": sum(margins) / n,
        "min_margin": min(margins),
    }


# --------------------------------------------------------------------------- 保存
def save_checkpoint(model, tokenizer, out_dir: Path, args, run_id: str,
                    model_version: str, codes: list[str],
                    jd_texts: dict[str, dict[str, str]]) -> Path:
    with torch.no_grad():
        broken = [n for n, p in model.named_parameters() if not torch.isfinite(p).all()]
    if broken:
        raise SystemExit(
            f"拒绝保存：{len(broken)} 个参数含 NaN/Inf（例如 {broken[:3]}）。"
            "这份权重推理时只会输出同一个概率，不能交付。"
        )
    best_dir = out_dir / "best"
    best_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(best_dir)
    tokenizer.save_pretrained(best_dir)

    config = {
        "task": "pair",
        "model_version": model_version,
        "run_id": run_id,
        "base_model": args.model_name,
        "num_labels": 1,
        "labels": codes,
        "max_length": args.max_length,
        "truncation": "only_first",
        "neg_per_pos": args.neg_per_pos,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    # JD 文本随权重一起存，推理时不再依赖 jd/jobs_24.yaml 是否被改动
    write_json(best_dir / "infer_config.json", config)
    write_json(out_dir / "infer_config.json", config)
    write_json(best_dir / "jds.json", {code: jd_texts[code] for code in codes})
    # infer.py 按 label2id.json 决定 24 个参考 JD 的顺序，必须与训练时的 codes 一致
    label2id = {code: index for index, code in enumerate(codes)}
    write_json(best_dir / "label2id.json", label2id)
    write_json(best_dir / "id2label.json", {str(i): code for i, code in enumerate(codes)})
    write_json(out_dir / "label2id.json", label2id)
    write_json(out_dir / "id2label.json", {str(i): code for i, code in enumerate(codes)})
    write_json(out_dir / "model_version.json", {
        "model_version": model_version,
        "run_id": run_id,
        "task": "pair",
        "base_model": args.model_name,
        "created_at": config["created_at"],
    })
    return best_dir


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="简历-JD 配对匹配训练")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--jd", type=Path, default=DEFAULT_JD)
    parser.add_argument("--zh-data", type=Path, default=ROOT / "data" / "resume_zh.jsonl")
    parser.add_argument("--no-zh", action="store_true", help="只用英文数据（消融用）")
    parser.add_argument("--model-name", default="microsoft/deberta-v3-base")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--eval-batch-size", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-ratio", type=float, default=0.06)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--neg-per-pos", type=int, default=1)
    parser.add_argument("--jd-dropout", type=float, default=0.2,
                        help="训练时随机丢弃 JD 非首行的比例（0 关闭）")
    parser.add_argument("--patience", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--max-bad-steps", type=int, default=20)
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--limit-train", type=int, default=None)
    parser.add_argument("--limit-val", type=int, default=None)
    parser.add_argument("--resume-from", type=str, default=None)
    args = parser.parse_args(argv)

    set_seed(args.seed)
    codes, _, _ = load_labels(args.split)
    jd_texts = load_jd_texts(args.jd, codes)

    train_examples = build_examples(
        args.csv, args.split, "train", limit=args.limit_train, seed=args.seed
    )
    val_examples = build_examples(
        args.csv, args.split, "val", limit=args.limit_val, seed=args.seed
    )
    zh_records: list[dict] = []
    if not args.no_zh:
        zh_records = load_zh_records(args.zh_data, set(codes))
        if args.limit_train:
            # 冒烟测试时也把中文侧一起缩小，避免 64 条英文配 480 条中文失真
            zh_records = zh_records[: max(1, args.limit_train // len(codes)) * len(codes)]

    print(f"英文训练简历 {len(train_examples)} 条，中文训练简历 {len(zh_records)} 条，"
          f"验证简历 {len(val_examples)} 条，JD {len(codes)} 个")

    tokenizer, model = load_tokenizer_and_model(args.model_name)
    if args.resume_from:
        state = torch.load(args.resume_from, map_location="cpu")
        model.load_state_dict(state)
        print(f"已从 {args.resume_from} 恢复权重")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    print(f"设备 {device}，参数量 {sum(p.numel() for p in model.parameters()) / 1e6:.2f}M")

    run_id = time_tag()
    out_dir = args.out_dir or (ROOT / "runs" / run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    short_name = Path(args.model_name).name
    model_version = f"{short_name}@{run_id}-pair"

    no_decay = ("bias", "LayerNorm.weight")
    groups = [
        {"params": [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)],
         "weight_decay": args.weight_decay},
        {"params": [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)],
         "weight_decay": 0.0},
    ]
    optimizer = torch.optim.AdamW(groups, lr=args.lr, eps=1e-8)
    # 每个 epoch 的配对条数是固定的（同一批简历 × (1 + neg_per_pos)），
    # 调度器必须在外层建一次，放进循环里会每个 epoch 重新走一遍 warmup。
    steps_per_epoch = max(
        1, -(-(len(train_examples) + len(zh_records)) * (1 + args.neg_per_pos) // args.batch_size)
    )
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(steps_per_epoch * args.epochs * args.warmup_ratio),
        num_training_steps=steps_per_epoch * args.epochs,
    )

    rng = random.Random(args.seed)
    best = {"recall_at_1": -1.0}
    best_epoch = 0
    bad_epochs = 0
    history: list[dict] = []
    started = time.time()

    for epoch in range(1, args.epochs + 1):
        pairs = build_train_pairs(train_examples, zh_records, jd_texts, codes,
                                  args.neg_per_pos, rng, args.jd_dropout)
        loader = DataLoader(
            PairDataset(pairs, tokenizer, args.max_length),
            batch_size=args.batch_size,
            shuffle=True,
            collate_fn=lambda batch: collate(batch, tokenizer),
            num_workers=0,
        )
        print(f"\n== epoch {epoch}/{args.epochs}：{len(pairs)} 个配对 ==")
        train_stats = train_one_epoch(model, loader, optimizer, scheduler, device, args, epoch)
        val_stats = evaluate_ranking(
            model, tokenizer, val_examples, jd_texts, codes,
            device, args.max_length, args.eval_batch_size,
        )
        record = {"epoch": epoch, **train_stats, **{f"val_{k}": v for k, v in val_stats.items()}}
        history.append(record)
        print(f"  epoch {epoch} 结果: train_loss={train_stats['train_loss']:.4f} "
              f"Recall@1={val_stats['recall_at_1']:.4f} MRR={val_stats['mrr']:.4f} "
              f"margin={val_stats['mean_margin']:+.4f} 用时 {format_duration(train_stats['seconds'])}")

        if val_stats["recall_at_1"] > best["recall_at_1"]:
            best = val_stats
            best_epoch = epoch
            bad_epochs = 0
            save_checkpoint(model, tokenizer, out_dir, args, run_id, model_version,
                            codes, jd_texts)
            print(f"  [best] 已保存，Recall@1={val_stats['recall_at_1']:.4f}")
        else:
            bad_epochs += 1
            if bad_epochs >= args.patience:
                print(f"  {args.patience} 个 epoch 没有提升，提前停止")
                break

    elapsed = time.time() - started
    summary = {
        "task": "pair",
        "model_version": model_version,
        "run_id": run_id,
        "best_epoch": best_epoch,
        "best_val": best,
        "epochs_run": len(history),
        "elapsed_seconds": elapsed,
        "train_english": len(train_examples),
        "train_chinese": len(zh_records),
        "neg_per_pos": args.neg_per_pos,
        "history": history,
        "stopped_early": len(history) < args.epochs,
        "config": {
            "base_model": args.model_name,
            "batch_size": args.batch_size,
            "max_length": args.max_length,
            "lr": args.lr,
            "epochs": args.epochs,
            "seed": args.seed,
        },
    }
    write_json(out_dir / "metrics.json", summary)
    print(f"\n训练完成：best epoch={best_epoch} val Recall@1={best['recall_at_1']:.4f} "
          f"总用时 {format_duration(elapsed)}")
    print(f"产物目录：{out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
