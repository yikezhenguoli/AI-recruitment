"""只读解析器：JSONL、npy header、npz 成员、源数据索引。

不包含任何写操作，不 import numpy（.npy 只读 header 解析用 struct）。
"""
from __future__ import annotations

import ast
import json
import struct
import zipfile
from pathlib import Path
from typing import Any

from ..utils import core


def describe_jsonl(path: str | Path, *, strict: bool = False) -> dict[str, Any]:
    rows, errors = core.read_jsonl(path, strict=strict)
    fields: dict[str, int] = {}
    for row in rows:
        for key in row:
            fields[key] = fields.get(key, 0) + 1
    return {
        "path": str(path),
        "line_count": len(rows),
        "field_presence": dict(sorted(fields.items(), key=lambda kv: (-kv[1], kv[0]))),
        "parse_errors": errors[:20],
        "parse_error_count": len(errors),
        "size_bytes": Path(path).stat().st_size,
    }


def npy_header(path: str | Path) -> dict[str, Any]:
    """只读 .npy 文件头，返回 shape / dtype / fortran_order，不加载数据。"""
    with open(path, "rb") as fh:
        magic = fh.read(6)
        if magic != b"\x93NUMPY":
            return {"valid": False, "reason": "非法 npy 魔数"}
        major, minor = fh.read(2)
        if major == 1:
            hlen = struct.unpack("<H", fh.read(2))[0]
        else:
            hlen = struct.unpack("<I", fh.read(4))[0]
        header = ast.literal_eval(fh.read(hlen).decode("latin1").strip())
    return {
        "valid": True,
        "npy_version": f"{major}.{minor}",
        "descr": header.get("descr"),
        "fortran_order": header.get("fortran_order"),
        "shape": list(header.get("shape", [])),
        "size_bytes": Path(path).stat().st_size,
    }


def npz_members(path: str | Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return sorted(zf.namelist())


def load_source_index(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """构建只读源数据索引，供审计、分析、构建共同使用。"""
    cfg = cfg or load_config_safe()
    resumes, e1 = core.read_jsonl(core.source_path("resumes", cfg))
    experiences, e2 = core.read_jsonl(core.source_path("experiences", cfg))
    questions, e3 = core.read_jsonl(core.source_path("questions", cfg))
    chains, e4 = core.read_jsonl(core.source_path("chains", cfg))
    return {
        "resumes": resumes,
        "experiences": experiences,
        "questions": questions,
        "chains": chains,
        "errors": e1 + e2 + e3 + e4,
        "by_resume": {r["resume_id"]: r for r in resumes if "resume_id" in r},
        "by_experience": {e["experience_id"]: e for e in experiences if "experience_id" in e},
        "by_question": {q["question_id"]: q for q in questions if "question_id" in q},
        "by_chain": {c["chain_id"]: c for c in chains if "chain_id" in c},
    }


def load_config_safe() -> dict[str, Any]:
    return core.load_config()


def read_json_object(path: str | Path) -> Any:
    return core.read_json(path)
