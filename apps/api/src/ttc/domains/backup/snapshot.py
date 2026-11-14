"""租户级逻辑快照：导出、校验与 UPSERT 恢复。

没有依赖 `pg_dump`（本机没有该客户端），所以用应用层逻辑快照：
每个租户一张 JSON 文档，按外键顺序列出核心表。恢复只做 UPSERT，不删数据，
并且必须先通过 `dry_run` 校验——列集合、主键与行数都要对得上。

已知边界：不备份对象存储里的原件（简历文件、音频），只备份数据库行。
"""

import base64
import gzip
import hashlib
import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import MetaData, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ttc.core.errors import TTCError

SNAPSHOT_VERSION = 1

logger = logging.getLogger(__name__)

_TABLES: tuple[tuple[str, str], ...] = (
    ("tenant", "id = :tenant"),
    ("app_user", "tenant_id = :tenant"),
    ("job", "tenant_id = :tenant"),
    ("job_version", "job_id IN (SELECT id FROM job WHERE tenant_id = :tenant)"),
    ("weight_plan", "tenant_id = :tenant"),
    ("interview_plan", "tenant_id = :tenant"),
    ("candidate", "tenant_id = :tenant"),
    ("resume", "candidate_id IN (SELECT id FROM candidate WHERE tenant_id = :tenant)"),
    ("resume_version",
     "resume_id IN (SELECT r.id FROM resume r JOIN candidate c ON c.id = r.candidate_id "
     "WHERE c.tenant_id = :tenant)"),
    ("resume_claim",
     "resume_version_id IN (SELECT rv.id FROM resume_version rv "
     "JOIN resume r ON r.id = rv.resume_id JOIN candidate c ON c.id = r.candidate_id "
     "WHERE c.tenant_id = :tenant)"),
    ("application", "tenant_id = :tenant"),
    ("assessment", "candidate_id IN (SELECT id FROM candidate WHERE tenant_id = :tenant)"),
    ("dimension_score",
     "assessment_id IN (SELECT a.id FROM assessment a JOIN candidate c "
     "ON c.id = a.candidate_id WHERE c.tenant_id = :tenant)"),
    ("assessment_revision",
     "assessment_id IN (SELECT a.id FROM assessment a JOIN candidate c "
     "ON c.id = a.candidate_id WHERE c.tenant_id = :tenant)"),
    ("evidence", "tenant_id = :tenant"),
    ("consent", "candidate_id IN (SELECT id FROM candidate WHERE tenant_id = :tenant)"),
    ("privacy_request", "candidate_id IN (SELECT id FROM candidate WHERE tenant_id = :tenant)"),
    ("audit_log", "tenant_id = :tenant"),
    ("voice_session",
     "candidate_id IN (SELECT id FROM candidate WHERE tenant_id = :tenant)"),
    ("voice_turn",
     "session_id IN (SELECT v.id FROM voice_session v JOIN candidate c "
     "ON c.id = v.candidate_id WHERE c.tenant_id = :tenant)"),
    ("call_report",
     "session_id IN (SELECT v.id FROM voice_session v JOIN candidate c "
     "ON c.id = v.candidate_id WHERE c.tenant_id = :tenant)"),
    ("offer", "tenant_id = :tenant"),
    ("offer_event",
     "offer_id IN (SELECT id FROM offer WHERE tenant_id = :tenant)"),
    ("interview_slot", "tenant_id = :tenant"),
    ("notification", "tenant_id = :tenant"),
    ("talent_index", "tenant_id = :tenant"),
)

TABLE_NAMES = tuple(name for name, _ in _TABLES)


def _encode(value):
    if isinstance(value, UUID):
        return {"$t": "uuid", "$v": str(value)}
    if isinstance(value, datetime):
        return {"$t": "datetime", "$v": value.isoformat()}
    if isinstance(value, date):
        return {"$t": "date", "$v": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$t": "decimal", "$v": str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"$t": "bytes", "$v": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def _decode(value):
    if isinstance(value, dict) and set(value) == {"$t", "$v"}:
        kind, raw = value["$t"], value["$v"]
        if kind == "uuid":
            return UUID(raw)
        if kind == "datetime":
            return datetime.fromisoformat(raw)
        if kind == "date":
            return date.fromisoformat(raw)
        if kind == "decimal":
            return Decimal(raw)
        if kind == "bytes":
            return base64.b64decode(raw)
        return raw
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        return {key: _decode(item) for key, item in value.items()}
    return value


async def export_tenant(session, tenant_id: UUID) -> tuple[bytes, dict[str, int]]:
    tables: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for name, predicate in _TABLES:
        rows = (await session.execute(
            text(f"SELECT * FROM {name} WHERE {predicate}"), {"tenant": tenant_id}
        )).mappings().all()
        tables[name] = [_encode(dict(row)) for row in rows]
        counts[name] = len(rows)
    document = {"snapshot_version": SNAPSHOT_VERSION, "tenant_id": str(tenant_id),
                "created_at": datetime.now(UTC).isoformat(), "tables": tables}
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode()
    return gzip.compress(raw), counts


def checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse(payload: bytes) -> dict:
    try:
        document = json.loads(gzip.decompress(payload))
    except (OSError, ValueError) as exc:
        raise TTCError("TTC-3003", "快照文件损坏或不是 gzip JSON", 422) from exc
    if document.get("snapshot_version") != SNAPSHOT_VERSION:
        raise TTCError("TTC-2002", "快照版本不兼容", 409)
    if not isinstance(document.get("tables"), dict):
        raise TTCError("TTC-2002", "快照结构不完整", 409)
    return document


async def _reflect(session, names: tuple[str, ...], predicate_names: tuple[str, ...]):
    metadata = MetaData()

    def load(connection):
        metadata.reflect(connection, only=list(names))

    try:
        # AsyncSession.run_sync 回调收到的是 Session 本身（不是 Connection），
        # 必须走 AsyncConnection.run_sync 才能拿到可反射的同步 Connection。
        connection = await session.connection()
        await connection.run_sync(load)
    except Exception as exc:
        logger.exception("反射表结构失败")
        raise TTCError("TTC-5004", "无法读取数据库表结构", 503) from exc
    missing = [name for name in predicate_names if name not in metadata.tables]
    if missing:
        raise TTCError("TTC-5004", f"数据库缺少表：{', '.join(missing)}", 503)
    return metadata


async def verify(session, tenant_id: UUID, document: dict) -> dict:
    if str(tenant_id) != document.get("tenant_id"):
        raise TTCError("TTC-1002", "快照不属于当前租户，不能恢复", 403)
    metadata = await _reflect(session, TABLE_NAMES, TABLE_NAMES)
    report: dict[str, dict] = {}
    problems: list[str] = []
    for name, _ in _TABLES:
        snapshotted = document["tables"].get(name, [])
        columns = {column.name for column in metadata.tables[name].columns}
        snapshot_columns = set().union(*(row.keys() for row in snapshotted)) \
            if snapshotted else set()
        missing = sorted(snapshot_columns - columns)
        empty = sorted(columns - snapshot_columns) if snapshotted else []
        if missing:
            problems.append(f"{name}: 快照含当前表不存在的列 {missing}")
        report[name] = {"rows": len(snapshotted), "columns_missing_in_db": missing,
                        "columns_absent_from_snapshot": empty}
    return {"tenant_id": str(tenant_id), "tables": report,
            "problems": problems, "ok": not problems}


async def restore(session, tenant_id: UUID, document: dict, *, dry_run: bool) -> dict:
    report = await verify(session, tenant_id, document)
    if not report["ok"]:
        raise TTCError("TTC-2002", "快照与当前表结构不一致，已拒绝恢复", 409,
                       {"problems": report["problems"]})
    if dry_run:
        return {**report, "applied": False}
    metadata = await _reflect(session, TABLE_NAMES, TABLE_NAMES)
    written: dict[str, int] = {}
    for name, _ in _TABLES:
        rows = document["tables"].get(name, [])
        if not rows:
            written[name] = 0
            continue
        table = metadata.tables[name]
        values = [{key: _decode(value) for key, value in row.items()} for row in rows]
        statement = pg_insert(table).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.id],
            set_={column.name: statement.excluded[column.name]
                  for column in table.columns if column.name != "id"},
        )
        await session.execute(statement)
        written[name] = len(values)
    return {**report, "applied": True, "written": written}
