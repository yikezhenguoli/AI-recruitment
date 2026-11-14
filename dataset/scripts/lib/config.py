"""配置加载器（纯标准库）。

优先使用 PyYAML；环境未安装时回退到内置的极简 YAML 子集解析器。
本项目所有 .yaml 配置文件只使用该子集：
  - 整行注释（# 开头）、空行
  - key: scalar / key: [a, b] / key: "带引号字符串"
  - key: 后接缩进块（嵌套映射或 - 列表）
  - 缩进一律为 2 个空格，禁止 tab、行尾注释、锚点与多行字符串
"""
from __future__ import annotations

import json
import os
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG_DIR = os.path.join(ROOT, "config")


def _scalar(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    if text[0] in "\"'" and text[-1] == text[0] and len(text) >= 2:
        body = text[1:-1]
        if text[0] == '"':
            return json.loads('"' + body.replace('"', '\\"') + '"') if "\\" in body else body
        return body
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        parts, buf, quote = [], "", None
        for ch in inner:
            if ch in "\"'":
                quote = None if quote == ch else (ch if quote is None else quote)
            if ch == "," and quote is None:
                parts.append(buf)
                buf = ""
            else:
                buf += ch
        if buf.strip():
            parts.append(buf)
        return [_scalar(p) for p in parts]
    low = text.lower()
    if low in ("null", "none", "~"):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _mini_yaml(path: str) -> Any:
    rows: list[tuple[int, str]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip(" "))
            rows.append((indent, line.strip()))

    def parse_block(i: int, indent: int) -> tuple[Any, int]:
        if i >= len(rows):
            return None, i
        if rows[i][1].startswith("- ") or rows[i][1] == "-":
            out = []
            while i < len(rows) and rows[i][0] == indent and (
                rows[i][1].startswith("- ") or rows[i][1] == "-"
            ):
                item = rows[i][1][1:].strip()
                i += 1
                # 列表项形如 "- key: value"，其后缩进行属于同一个映射
                is_map_item = (
                    bool(item)
                    and item[0] not in "\"'["
                    and (": " in item or item.endswith(":"))
                )
                if is_map_item:
                    j = i
                    while j < len(rows) and rows[j][0] > indent:
                        j += 1
                    child_indent = rows[i][0] if i < j else indent + 2
                    sub_rows = [(child_indent, item)] + rows[i:j]
                    saved = rows[:]
                    rows[:] = sub_rows
                    sub, _ = parse_block(0, child_indent)
                    rows[:] = saved
                    out.append(sub)
                    i = j
                elif item:
                    out.append(_scalar(item))
                elif i < len(rows) and rows[i][0] > indent:
                    sub, i = parse_block(i, rows[i][0])
                    out.append(sub)
                else:
                    out.append(None)
            return out, i
        out: dict[str, Any] = {}
        while i < len(rows) and rows[i][0] == indent and not rows[i][1].startswith("- "):
            key, _, rest = rows[i][1].partition(":")
            key = key.strip().strip("\"'")
            i += 1
            if rest.strip():
                out[key] = _scalar(rest)
            elif i < len(rows) and rows[i][0] > indent:
                sub, i = parse_block(i, rows[i][0])
                out[key] = sub
            else:
                out[key] = None
        return out, i

    value, _ = parse_block(0, rows[0][0] if rows else 0)
    return value


def load_yaml(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        return _mini_yaml(path)


_CACHE: dict[str, Any] = {}


def get_config(name: str, reload: bool = False) -> dict[str, Any]:
    """按文件名加载 config/ 下的配置，例如 get_config('generation_config')。"""
    if name in _CACHE and not reload:
        return _CACHE[name]
    filename = name if name.endswith(".yaml") else name + ".yaml"
    data = load_yaml(os.path.join(CONFIG_DIR, filename))
    if not isinstance(data, dict):
        raise ValueError(f"配置文件内容必须是映射: {filename}")
    _CACHE[name] = data
    return data


def abspath(rel: str) -> str:
    return rel if os.path.isabs(rel) else os.path.join(ROOT, rel)


def all_configs() -> dict[str, Any]:
    names = [
        "generation_config",
        "position_categories",
        "experience_types",
        "question_dimensions",
        "question_types",
        "quality_distribution",
        "scoring_rules",
    ]
    return {n: get_config(n) for n in names}
