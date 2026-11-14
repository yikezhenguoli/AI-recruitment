"""轻量 JSON Schema 校验器（draft-07 常用子集，纯标准库）。

支持关键字：type, required, properties, items, enum, const, minItems, maxItems,
minLength, maxLength, pattern, additionalProperties(false)。
不依赖 jsonschema 第三方库。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..utils import core

_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}
SCHEMA_DIR = Path(__file__).resolve().parent / "definitions.json"

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def load_definitions() -> dict[str, Any]:
    if "defs" not in _SCHEMA_CACHE:
        _SCHEMA_CACHE["defs"] = core.read_json(SCHEMA_DIR)
    return _SCHEMA_CACHE["defs"]


def schema_for(entity: str) -> dict[str, Any]:
    defs = load_definitions()
    if entity not in defs["schemas"]:
        raise KeyError(f"未知 Schema 实体: {entity}")
    return defs["schemas"][entity]


def _resolve_ref(schema: dict[str, Any]) -> dict[str, Any]:
    """解析本地 JSON Pointer（#/$defs/x 或 #/schemas/x）。"""
    ref = schema.get("$ref")
    if not ref or not ref.startswith("#/"):
        return schema
    node: Any = load_definitions()
    for part in ref[2:].split("/"):
        node = node[part]
    merged = dict(node)
    merged.update({k: v for k, v in schema.items() if k != "$ref"})
    return merged


def validate(obj: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """返回错误列表；空列表表示通过。"""
    errors: list[str] = []
    schema = _resolve_ref(schema)

    expected = schema.get("type")
    if expected:
        kinds = expected if isinstance(expected, list) else [expected]
        ok = False
        for kind in kinds:
            py = _TYPES.get(kind)
            if py is None:
                continue
            if kind == "integer":
                ok = ok or (isinstance(obj, int) and not isinstance(obj, bool))
            elif kind == "number":
                ok = ok or (isinstance(obj, (int, float)) and not isinstance(obj, bool))
            elif kind == "boolean":
                ok = ok or isinstance(obj, bool)
            else:
                ok = ok or isinstance(obj, py)
        if not ok:
            errors.append(f"{path}: 类型应为 {'|'.join(kinds)}，实际为 {type(obj).__name__}")
            return errors

    if "enum" in schema and obj not in schema["enum"]:
        errors.append(f"{path}: 取值 {obj!r} 不在枚举 {schema['enum']} 中")
    if "const" in schema and obj != schema["const"]:
        errors.append(f"{path}: 取值应为常量 {schema['const']!r}")

    if isinstance(obj, dict):
        for key in schema.get("required", []):
            if key not in obj:
                errors.append(f"{path}: 缺少必需字段 '{key}'")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in obj:
                errors.extend(validate(obj[key], sub, f"{path}.{key}"))
        if schema.get("additionalProperties") is False:
            extra = set(obj) - set(props)
            if extra:
                errors.append(f"{path}: 不允许的额外字段 {sorted(extra)}")

    if isinstance(obj, list):
        if "minItems" in schema and len(obj) < schema["minItems"]:
            errors.append(f"{path}: 至少需要 {schema['minItems']} 项，实际 {len(obj)}")
        if "maxItems" in schema and len(obj) > schema["maxItems"]:
            errors.append(f"{path}: 最多允许 {schema['maxItems']} 项，实际 {len(obj)}")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(obj):
                errors.extend(validate(item, item_schema, f"{path}[{i}]"))

    if isinstance(obj, str):
        if "minLength" in schema and len(obj) < schema["minLength"]:
            errors.append(f"{path}: 长度不足 {schema['minLength']}")
        if "maxLength" in schema and len(obj) > schema["maxLength"]:
            errors.append(f"{path}: 长度超过 {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], obj):
            errors.append(f"{path}: 不匹配模式 {schema['pattern']}")

    return errors


def validate_entity(obj: Any, entity: str) -> list[str]:
    return validate(obj, schema_for(entity), f"${entity}")


def self_check() -> list[str]:
    """Schema 定义自身的合法性自检（关键字段、枚举与 taxonomy 一致）。"""
    errs: list[str] = []
    defs = load_definitions()
    tax = core.load_taxonomy()
    if defs.get("version") != core.load_config()["ontology_version"]:
        errs.append("Schema 版本与配置 ontology_version 不一致")
    for entity, sch in defs["schemas"].items():
        resolved = _resolve_ref(sch)
        if resolved.get("type") != "object" or "required" not in resolved:
            errs.append(f"{entity}: 缺少 object/required 定义")
    for name, values in tax["enums"].items():
        if not values:
            errs.append(f"taxonomy 枚举 {name} 为空")
    return errs
