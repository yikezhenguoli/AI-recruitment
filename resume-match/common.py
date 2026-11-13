"""训练与评估脚本共用的小工具。

职责：
  * 路径解析（默认值一律相对本文件所在目录，云端任意 cwd 都能跑）
  * 读取固定划分 split.csv / 原始简历 CSV / JD yaml
  * 标签顺序（必须与 split.csv 中 sorted(category) 一致）
  * 指标计算、混淆对诊断、随机种子

不在这里做的事：模型加载、训练循环（见 train.py）、推理（见 infer.py）。
"""

from __future__ import annotations

import csv
import json
import os
import random
import re
import time
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)

# 所有默认路径都从本文件位置推导，避免依赖调用时的 cwd。
ROOT = Path(__file__).resolve().parent
DEFAULT_CSV = ROOT / "data" / "archive" / "archive" / "Resume" / "Resume.csv"
DEFAULT_SPLIT = ROOT / "splits" / "split.csv"
DEFAULT_JD = ROOT / "jd" / "jobs_24.yaml"

SPLITS = ("train", "val", "test")

# 原始 CSV 里 Resume_str 含 \xa0、连续空格与空行，做轻量归一化。
# 不做小写/去标点（那是 TF-IDF 那侧自己的事，BERT 类分词器需要原始大小写）。
_SPACE_RE = re.compile(r"[ \t]+")
_NEWLINE_RE = re.compile(r"\n{3,}")


class DataError(RuntimeError):
    """数据文件缺失、列不全、ID 对不上等硬错误。"""


def normalize_text(text: str) -> str:
    """仅清理不可见字符与冗余空白，保留换行与大小写。"""
    if not isinstance(text, str):
        return ""
    text = text.replace("\xa0", " ").replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACE_RE.sub(" ", text)
    text = _NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def resolve_path(path_like: str | os.PathLike | None, default: Path | None = None) -> Path:
    """用户显式传入的路径按 cwd 解析；未传时用脚本目录下的默认值。"""
    if path_like is None:
        if default is None:
            raise ValueError("path_like 与 default 不能同时为空")
        return default
    p = Path(path_like).expanduser()
    return p if p.is_absolute() else (Path.cwd() / p).resolve()


def read_split(split_path: str | os.PathLike) -> list[dict[str, str]]:
    """读取固定划分文件；只做格式校验，绝不重新划分。"""
    path = Path(split_path)
    if not path.is_file():
        raise DataError(f"找不到划分文件: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = {"id", "category", "split"} - set(reader.fieldnames or [])
        if missing:
            raise DataError(f"{path} 缺少列: {sorted(missing)}（实际列 {reader.fieldnames}）")
        rows = []
        for i, row in enumerate(reader, start=2):
            rid = (row.get("id") or "").strip()
            cat = (row.get("category") or "").strip()
            split = (row.get("split") or "").strip()
            if not rid or not cat:
                raise DataError(f"{path} 第 {i} 行 id/category 为空")
            if split not in SPLITS:
                raise DataError(f"{path} 第 {i} 行 split={split!r}，应为 {SPLITS}")
            rows.append({"id": rid, "category": cat, "split": split})
    return rows


def load_labels(split_path: str | os.PathLike) -> tuple[list[str], dict[str, int], dict[int, str]]:
    """返回与 prepare_split.py 完全一致的标签顺序：sorted(category)。"""
    categories = {row["category"] for row in read_split(split_path)}
    if not categories:
        raise DataError(f"{split_path} 没有可用行")
    labels = sorted(categories)
    label2id = {label: i for i, label in enumerate(labels)}
    id2label = {i: label for label, i in label2id.items()}
    return labels, label2id, id2label


def load_resume_texts(csv_path: str | os.PathLike) -> dict[str, dict[str, str]]:
    """用 csv.DictReader 显式读 ID / Resume_str / Category。

    Resume_str 里含换行、引号、\xa0，csv 模块能正确处理；这里不 chdir 到数据目录，
    也不在该目录里执行任何东西（外部归档数据按不可信处理）。
    """
    path = Path(csv_path)
    if not path.is_file():
        raise DataError(f"找不到简历 CSV: {path}")
    out: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        required = {"ID", "Resume_str", "Category"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise DataError(f"{path} 缺少列: {sorted(missing)}（实际列 {reader.fieldnames}）")
        for row in reader:
            rid = (row.get("ID") or "").strip()
            if not rid:
                continue
            out[rid] = {
                "text": row.get("Resume_str") or "",
                "category": (row.get("Category") or "").strip(),
            }
    if not out:
        raise DataError(f"{path} 没有读到任何行")
    return out


def build_examples(
    csv_path: str | os.PathLike,
    split_path: str | os.PathLike,
    which: str,
    *,
    labels: list[str] | None = None,
    label2id: dict[str, int] | None = None,
    limit: int | None = None,
    seed: int = 42,
) -> list[dict]:
    """按固定划分取出某一 split 的样本，返回 [{id,text,label,category}]。

    严格校验：split.csv 里的每条 ID 都能在 Resume.csv 找到、类别一致、文本非空。
    缺任何一条都直接报错，不静默丢弃（否则训练/评估口径会与 split.csv 不一致）。
    """
    if which not in SPLITS:
        raise ValueError(f"which 应为 {SPLITS}，收到 {which!r}")
    if labels is None or label2id is None:
        labels, label2id, _ = load_labels(split_path)

    split_rows = read_split(split_path)
    wanted = [r for r in split_rows if r["split"] == which]
    if not wanted:
        raise DataError(f"split.csv 中 {which} 为空，无法评估")

    resumes = load_resume_texts(csv_path)
    missing: list[str] = []
    empty: list[str] = []
    mismatch: list[str] = []
    examples: list[dict] = []
    for row in wanted:
        rid = row["id"]
        item = resumes.get(rid)
        if item is None:
            missing.append(rid)
            continue
        if item["category"] != row["category"]:
            mismatch.append(f"{rid}: split={row['category']} csv={item['category']}")
            continue
        text = normalize_text(item["text"])
        if not text:
            empty.append(rid)
            continue
        if row["category"] not in label2id:
            raise DataError(f"类别 {row['category']!r} 不在标签表里（{rid}）")
        examples.append(
            {"id": rid, "text": text, "category": row["category"], "label": label2id[row["category"]]}
        )

    if missing or empty or mismatch:
        parts = []
        if missing:
            parts.append(f"{len(missing)} 条 ID 在 Resume.csv 中不存在（例: {missing[:3]}）")
        if empty:
            parts.append(f"{len(empty)} 条 Resume_str 为空（例: {empty[:3]}）")
        if mismatch:
            parts.append(f"{len(mismatch)} 条类别不一致（例: {mismatch[:3]}）")
        raise DataError("；".join(parts))

    if limit is not None and 0 < limit < len(examples):
        examples = stratified_take(examples, limit, labels, seed)
    return examples


def stratified_take(examples: list[dict], n: int, labels: list[str], seed: int) -> list[dict]:
    """按类别轮流抽样，保证小样本冒烟测试也能覆盖多个类别。"""
    rng = random.Random(seed)
    by_label: dict[int, list[dict]] = {}
    for ex in examples:
        by_label.setdefault(ex["label"], []).append(ex)
    for items in by_label.values():
        rng.shuffle(items)
    order = [label for label in range(len(labels)) if label in by_label]
    rng.shuffle(order)
    picked: list[dict] = []
    round_idx = 0
    while len(picked) < n:
        added = False
        for label in order:
            items = by_label[label]
            if round_idx < len(items):
                picked.append(items[round_idx])
                added = True
                if len(picked) >= n:
                    break
        if not added:
            break
        round_idx += 1
    return picked


def dataset_stats(examples: list[dict], labels: list[str]) -> dict:
    counts = Counter(ex["category"] for ex in examples)
    return {
        "n": len(examples),
        "per_class": {label: counts.get(label, 0) for label in labels},
        "missing_classes": [label for label in labels if counts.get(label, 0) == 0],
    }


def compute_metrics(y_true, y_pred, labels: list[str]) -> dict:
    """accuracy / macro-F1 / weighted-F1 / 每类 P-R-F1 / 混淆矩阵。"""
    y_true = list(y_true)
    y_pred = list(y_pred)
    if not y_true:
        raise ValueError("y_true 为空，无法计算指标")
    label_ids = list(range(len(labels)))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=label_ids, average=None, zero_division=0
    )
    matrix = confusion_matrix(y_true, y_pred, labels=label_ids)
    return {
        "n": len(y_true),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=label_ids, average="macro", zero_division=0)),
        "weighted_f1": float(
            f1_score(y_true, y_pred, labels=label_ids, average="weighted", zero_division=0)
        ),
        "per_class": {
            labels[i]: {
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
            }
            for i in range(len(labels))
        },
        "confusion_matrix": matrix.tolist(),
    }


def top_confusion_pairs(metrics: dict, labels: list[str], k: int = 5) -> list[dict]:
    """被误判最多的真实类别 → 预测类别对（不含对角线）。"""
    matrix = metrics["confusion_matrix"]
    pairs = []
    for i, true_label in enumerate(labels):
        row_total = sum(matrix[i])
        if row_total == 0:
            continue
        for j, pred_label in enumerate(labels):
            if i == j:
                continue
            count = matrix[i][j]
            if count <= 0:
                continue
            pairs.append(
                {
                    "true": true_label,
                    "pred": pred_label,
                    "count": int(count),
                    "share_of_true_class": float(count / row_total),
                }
            )
    pairs.sort(key=lambda p: (-p["count"], p["true"], p["pred"]))
    return pairs[:k]


def load_jd_info(jd_path: str | os.PathLike = DEFAULT_JD) -> dict[str, dict]:
    """读取 JD yaml，仅用于在报告里补充中英文岗位名；读不到就返回空表。"""
    path = Path(jd_path)
    if not path.is_file():
        return {}
    try:
        import yaml  # 放在函数里，避免无 yaml 时连数据工具都用不了
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for job in data or []:
        if isinstance(job, dict) and job.get("code"):
            out[str(job["code"])] = job
    return out


def set_seed(seed: int) -> None:
    """固定 random / numpy / torch / cuda 的随机性。"""
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
    except ImportError:
        return
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    # 云端复现优先于极限吞吐；这两项会让个别 kernel 稍慢。
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def write_json(path: str | os.PathLike, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default)
    path.write_text(text + "\n", encoding="utf-8")


def _json_default(obj):
    # numpy 标量/数组落到 json 时统一转成 Python 原生类型
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    raise TypeError(f"无法序列化 {type(obj)!r}")


def time_tag() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"
