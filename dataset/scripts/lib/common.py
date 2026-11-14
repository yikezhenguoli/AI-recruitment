"""公共 I/O、日志、知识库加载与文本工具（纯标准库）。"""
from __future__ import annotations

import datetime as _dt
import json
import os
import random
import re
from typing import Any, Iterable

from . import config

ROOT = config.ROOT
_LOG_PATH = config.abspath(config.get_config("generation_config")["checkpoint"]["log_file"])


# ---------------------------------------------------------------- I/O
def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str, obj: Any, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=indent)


def read_jsonl(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{n} JSON 解析失败: {exc}") from exc
    return out


def write_jsonl(path: str, rows: Iterable[dict[str, Any]], mode: str = "w") -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = 0
    with open(path, mode, encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    return n


def log(msg: str) -> None:
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    with open(_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line)


# ---------------------------------------------------------------- 知识库
_KB: dict[str, dict[str, Any]] = {}
_BANKS: dict[str, Any] = {}


def load_banks() -> dict[str, Any]:
    global _BANKS
    if not _BANKS:
        _BANKS = read_json(os.path.join(ROOT, "knowledge_base", "common", "common_banks.json"))
    return _BANKS


def load_position_kb(position_id: str) -> dict[str, Any]:
    if position_id not in _KB:
        p = os.path.join(ROOT, "knowledge_base", "positions", position_id + ".json")
        _KB[position_id] = read_json(p)
    return _KB[position_id]


def all_position_kbs() -> dict[str, dict[str, Any]]:
    order = config.get_config("position_categories")["position_order"]
    return {pid: load_position_kb(pid) for pid in order}


# ---------------------------------------------------------------- 状态
def load_state() -> dict[str, Any]:
    p = config.abspath(config.get_config("generation_config")["checkpoint"]["state_file"])
    if os.path.exists(p):
        return read_json(p)
    return {
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "stage": "init",
        "completed_resume_ids": [],
        "completed_batches": [],
        "failed_resume_ids": [],
        "batches": {},
    }


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    write_json(config.abspath(config.get_config("generation_config")["checkpoint"]["state_file"]), state)


# ---------------------------------------------------------------- 文本
_NUM_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")


def jitter_numbers(text: str, rng: random.Random) -> str:
    """对指标中的数值做轻微扰动以制造差异，保持数值方向与语义结构。"""
    def repl(m: re.Match[str]) -> str:
        raw = m.group(0)
        if rng.random() > 0.65:
            return raw
        val = float(raw)
        if val <= 0:
            return raw
        factor = rng.uniform(0.80, 1.25)
        new = val * factor
        if "." in raw:
            return f"{new:.1f}"
        new_i = max(1, int(round(new)))
        if "%" in text[m.end():m.end() + 1]:
            new_i = min(new_i, 96)
        return str(new_i)
    return _NUM_RE.sub(repl, text)


def ym_add(year: int, month: int, delta_months: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta_months
    return total // 12, total % 12 + 1


def ym_str(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def ym_tuple(s: str) -> tuple[int, int]:
    y, m = s.split("-")
    return int(y), int(m)


def months_between(a: str, b: str) -> int:
    ya, ma = ym_tuple(a)
    yb, mb = ym_tuple(b)
    return (yb - ya) * 12 + (mb - ma)


def strip_tail_punct(s: str) -> str:
    return s.rstrip("。；，、：;,")


def pick(rng: random.Random, seq: list[Any], default: Any = "") -> Any:
    return rng.choice(seq) if seq else default


def sample(rng: random.Random, seq: list[Any], n: int) -> list[Any]:
    return rng.sample(seq, min(n, len(seq)))
