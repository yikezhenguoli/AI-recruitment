"""租户备份：生成逻辑快照、校验、UPSERT 恢复。

恢复接口默认 `dry_run=true`；真正写入必须把 `confirm` 设为快照 id，且只做
UPSERT，不会删除桶外数据。对象存储里的简历原件与音频不在快照内。
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.adapters.storage import Storage
from ttc.api.deps import Principal, require_permission
from ttc.core.audit import record_audit
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7
from ttc.domains.backup.snapshot import checksum, export_tenant, parse, restore, verify

router = APIRouter(tags=["backup"])
backup_admin = require_permission("backup:manage")


class RestoreInput(BaseModel):
    dry_run: bool = True
    confirm: str | None = None


async def require_snapshot(session: AsyncSession, snapshot_id: UUID, tenant_id: UUID) -> dict:
    row = (await session.execute(text(
        "SELECT id, uri, table_counts, checksum, size_bytes, created_by, created_at "
        "FROM backup_snapshot WHERE id = :id AND tenant_id = :tenant"
    ), {"id": snapshot_id, "tenant": tenant_id})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "快照不存在", 404)
    return dict(row)


@router.post("/admin/backups", status_code=201)
async def create_backup(user: Principal = Depends(backup_admin),
                        session: AsyncSession = Depends(get_session)):
    payload, counts = await export_tenant(session, user.tenant_id)
    digest = checksum(payload)
    snapshot_id = uuid7()
    uri = await Storage().put(
        f"backups/{user.tenant_id}/{snapshot_id}.json.gz", payload, "application/gzip")
    row = (await session.execute(text(
        "INSERT INTO backup_snapshot (id, tenant_id, uri, table_counts, checksum, "
        "size_bytes, created_by) VALUES (:id, :tenant, :uri, CAST(:counts AS jsonb), "
        ":checksum, :size, :user) RETURNING id, created_at"
    ), {"id": snapshot_id, "tenant": user.tenant_id, "uri": uri,
        "counts": json.dumps(counts, ensure_ascii=False),
        "checksum": digest, "size": len(payload), "user": user.id})).mappings().one()
    await record_audit(session, user, "backup.create", "backup_snapshot", snapshot_id)
    await session.commit()
    return {**dict(row), "uri": uri, "table_counts": counts, "checksum": digest,
            "size_bytes": len(payload),
            "note": "仅数据库行；简历原件、音频等对象存储内容不在此快照内"}


@router.get("/admin/backups")
async def list_backups(limit: int = 50, user: Principal = Depends(backup_admin),
                       session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(text(
        "SELECT id, uri, table_counts, checksum, size_bytes, created_at "
        "FROM backup_snapshot WHERE tenant_id = :tenant ORDER BY created_at DESC LIMIT :limit"
    ), {"tenant": user.tenant_id, "limit": max(1, min(limit, 200))})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/admin/backups/{snapshot_id}/verify")
async def verify_backup(snapshot_id: UUID, user: Principal = Depends(backup_admin),
                        session: AsyncSession = Depends(get_session)):
    snapshot = await require_snapshot(session, snapshot_id, user.tenant_id)
    payload = await Storage().get(snapshot["uri"])
    digest = checksum(payload)
    if digest != snapshot["checksum"]:
        raise TTCError("TTC-3004", "快照校验和不匹配，文件可能已损坏", 422)
    report = await verify(session, user.tenant_id, parse(payload))
    return {**report, "snapshot_id": str(snapshot_id), "checksum_ok": True}


@router.post("/admin/backups/{snapshot_id}/restore")
async def restore_backup(snapshot_id: UUID, body: RestoreInput,
                         user: Principal = Depends(backup_admin),
                         session: AsyncSession = Depends(get_session)):
    if not body.dry_run and body.confirm != str(snapshot_id):
        raise TTCError("TTC-2002", "执行恢复必须把 confirm 设为该快照 id", 409)
    snapshot = await require_snapshot(session, snapshot_id, user.tenant_id)
    payload = await Storage().get(snapshot["uri"])
    if checksum(payload) != snapshot["checksum"]:
        raise TTCError("TTC-3004", "快照校验和不匹配，文件可能已损坏", 422)
    report = await restore(session, user.tenant_id, parse(payload), dry_run=body.dry_run)
    if body.dry_run:
        await session.rollback()
        return report
    await session.execute(text(
        "SELECT setval(pg_get_serial_sequence('audit_log', 'id'), "
        "GREATEST((SELECT COALESCE(max(id), 1) FROM audit_log), 1))"
    ))
    await record_audit(session, user, "backup.restore", "backup_snapshot", snapshot_id)
    await session.commit()
    return report
