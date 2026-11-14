"""RISM-002 公共工具层：配置、路径、IO、审核状态、脱敏。

纯标准库实现；所有路径基于 __file__ 与配置解析，不依赖当前工作目录。
本模块不 import torch / numpy / sentence_transformers，也不读写模型权重。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

# rism002/utils/core.py -> parents[2] == RISMv2 项目根
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "rism002.json"

_CACHE: dict[str, Any] = {}


def load_config(path: str | os.PathLike | None = None) -> dict[str, Any]:
    """加载主配置。project_root='auto' 时以本文件定位项目根。"""
    p = Path(path) if path else DEFAULT_CONFIG
    key = str(p)
    if key in _CACHE:
        return _CACHE[key]
    with open(p, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    root = cfg.get("project_root", "auto")
    cfg["_root"] = str(PROJECT_ROOT if root == "auto" else Path(root).resolve())
    cfg["_config_path"] = key
    _CACHE[key] = cfg
    return cfg


def root(cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    return Path(cfg["_root"])


def resolve(rel: str, cfg: dict[str, Any] | None = None) -> Path:
    """把配置中的相对路径解析为绝对路径；绝对路径原样返回。"""
    p = Path(rel)
    return p if p.is_absolute() else root(cfg) / p


def source_path(name: str, cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    return resolve(cfg["source"][name], cfg)


def out_path(name: str, cfg: dict[str, Any] | None = None) -> Path:
    cfg = cfg or load_config()
    return resolve(cfg["paths"][name], cfg)


def load_taxonomy(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    key = "taxonomy"
    if key not in _CACHE:
        with open(resolve(cfg["paths"]["taxonomy"], cfg), "r", encoding="utf-8") as fh:
            _CACHE[key] = json.load(fh)
    return _CACHE[key]


def enum_values(name: str, cfg: dict[str, Any] | None = None) -> list[str]:
    return list(load_taxonomy(cfg)["enums"][name])


def primary_dimension_ids(cfg: dict[str, Any] | None = None) -> list[str]:
    return [d["id"] for d in load_taxonomy(cfg)["primary_dimensions"]]


# ---------------------------------------------------------------- IO

def iter_jsonl(path: str | os.PathLike, *, strict: bool = True) -> Iterator[tuple[int, dict[str, Any] | None, str | None]]:
    """逐行读取 JSONL，返回 (行号, 对象或 None, 错误或 None)。

    strict=True 时遇到解析错误抛 ValueError；False 时把错误随行返回、继续读。
    """
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                msg = f"{Path(path).name}:{lineno} JSON 解析失败: {exc.msg} (col {exc.colno})"
                if strict:
                    raise ValueError(msg) from exc
                yield lineno, None, msg
                continue
            if not isinstance(obj, dict):
                msg = f"{Path(path).name}:{lineno} 顶层不是 object，实际为 {type(obj).__name__}"
                if strict:
                    raise ValueError(msg)
                yield lineno, None, msg
                continue
            yield lineno, obj, None


def read_jsonl(path: str | os.PathLike, *, strict: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for _, obj, err in iter_jsonl(path, strict=strict):
        if err:
            errors.append(err)
        elif obj is not None:
            rows.append(obj)
    return rows, errors


def read_json(path: str | os.PathLike) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str | os.PathLike, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, p)


def write_jsonl(path: str | os.PathLike, rows: Iterable[dict[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    n = 0
    with open(tmp, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    os.replace(tmp, p)
    return n


def sha256_file(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- 审核状态

def review_block(*, source: str = "rule_based", status: str = "pending",
                 annotator_id: str | None = None, reviewed_at: str | None = None,
                 review_reason: str = "", ontology_version: str | None = None,
                 cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """生成审核状态块。annotation_status 与 label_status 互不推导。"""
    cfg = cfg or load_config()
    return {
        "annotation_source": source,
        "annotation_status": status,
        "annotator_id": annotator_id,
        "reviewed_at": reviewed_at,
        "review_reason": review_reason,
        "ontology_version": ontology_version or cfg["ontology_version"],
        "reviewed": bool(status == "approved" and source in cfg["review"]["approved_requires_sources"]),
    }


def is_approved(record: dict[str, Any], cfg: dict[str, Any] | None = None) -> bool:
    """硬性门槛：只有人工来源 + approved + reviewed=True 才算可进入正式数据集。"""
    cfg = cfg or load_config()
    rv = record.get("review", record)
    review = cfg["review"]
    if rv.get("annotation_status") != "approved":
        return False
    if rv.get("annotation_source") not in review["approved_requires_sources"]:
        return False
    if review["negative_requires_reviewed"] and not rv.get("reviewed", False):
        return False
    return True


def direction_label_default(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """未审核/未出现的方向一律 Unknown，绝不自动转 Negative。"""
    cfg = cfg or load_config()
    return {
        "label_status": cfg["review"]["default_label_status"],
        "annotation_source": None,
        "reviewed": False,
    }


# ---------------------------------------------------------------- 脱敏

_SENSITIVE_PATTERNS = [
    (re.compile(r"1[3-9]\d{9}"), "[PHONE]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"\b\d{17}[\dXx]\b"), "[ID]"),
]


def redact(text: str) -> str:
    """对文本做敏感信息掩码。报告与日志默认不输出简历文本，此为二级防护。"""
    out = str(text)
    for pat, repl in _SENSITIVE_PATTERNS:
        out = pat.sub(repl, out)
    return out


def safe_id(value: Any) -> str:
    """报告只允许输出 ID 类字段。"""
    return str(value)


def ensure_dirs(cfg: dict[str, Any] | None = None) -> None:
    cfg = cfg or load_config()
    for key in ("intermediate_dir", "annotations_dir", "ontology_dir", "output_dir"):
        resolve(cfg["paths"][key], cfg).mkdir(parents=True, exist_ok=True)
    out_path("processed_samples", cfg).parent.mkdir(parents=True, exist_ok=True)
