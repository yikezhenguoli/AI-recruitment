"""Markdown 报告渲染工具。所有报告只输出 ID、计数与枚举分布，不输出简历正文。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..utils import core


def md_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    hs = [str(h) for h in headers]
    out = ["| " + " | ".join(hs) + " |", "|" + "|".join(["---"] * len(hs)) + "|"]
    for row in rows:
        cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in row]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def bullet_list(items: Iterable[Any], limit: int | None = None) -> str:
    seq = list(items)
    if limit is not None:
        seq = seq[:limit]
    return "\n".join(f"- {x}" for x in seq) if seq else "- （无）"


def kv_table(mapping: dict[str, Any]) -> str:
    return md_table(["指标", "值"], [[k, v] for k, v in mapping.items()])


def write_report(path: str | Path, title: str, sections: list[tuple[str, str]],
                 meta: dict[str, Any] | None = None) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]
    if meta:
        lines += [f"> 生成时间：{core.now_iso()}", ">"]
        for k, v in meta.items():
            lines.append(f"> {k}：{v}")
        lines.append("")
    for heading, body in sections:
        lines += [f"## {heading}", "", body.strip(), ""]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
