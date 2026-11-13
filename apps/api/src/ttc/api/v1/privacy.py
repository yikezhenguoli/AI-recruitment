import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.adapters.realtime import enqueue_hangup
from ttc.adapters.storage import Storage
from ttc.api.deps import Principal, current_user, require_roles
from ttc.api.v1.candidates import require_candidate
from ttc.core.audit import record_audit
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7

router = APIRouter(tags=["privacy"])


class PrivacyInput(BaseModel):
    candidate_id: UUID
    request_type: Literal["access", "correct", "revoke", "delete"]
    reason: str | None = Field(default=None, max_length=1000)


@router.post("/privacy/requests", status_code=202)
async def request_privacy(body: PrivacyInput,
                          user: Principal = Depends(require_roles("candidate")),
                          session: AsyncSession = Depends(get_session)):
    await require_candidate(session, user, body.candidate_id)
    request_id = uuid7()
    await session.execute(text(
        "INSERT INTO privacy_request (id, tenant_id, candidate_id, requester_id, "
        "request_type, payload) VALUES (:id, :tenant, :candidate, :user, "
        "CAST(:type AS privacy_type), CAST(:payload AS jsonb))"
    ), {"id": request_id, "tenant": user.tenant_id, "candidate": body.candidate_id,
        "user": user.id, "type": body.request_type,
        "payload": json.dumps({"reason": body.reason}, ensure_ascii=False)})
    await record_audit(session, user, "privacy.request", "privacy_request", request_id)
    await session.commit()
    return {"id": request_id, "status": "submitted", "sla_hours": 24}


@router.get("/privacy/requests/{request_id}")
async def get_request(request_id: UUID, user: Principal = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    row = (await session.execute(text(
        "SELECT id, candidate_id, requester_id, request_type, status, result, "
        "created_at, completed_at FROM privacy_request "
        "WHERE id = :id AND tenant_id = :tenant"
    ), {"id": request_id, "tenant": user.tenant_id})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "隐私申请不存在", 404)
    if user.role == "candidate" and row["requester_id"] != user.id:
        raise TTCError("TTC-1002", "无权查询他人的隐私申请", 403)
    if user.role not in ("candidate", "admin"):
        raise TTCError("TTC-1002", "无权查询隐私申请", 403)
    return dict(row)


@router.post("/admin/privacy/requests/{request_id}/process")
async def process_request(request_id: UUID,
                          user: Principal = Depends(require_roles("admin")),
                          session: AsyncSession = Depends(get_session)):
    row = (await session.execute(text(
        "SELECT candidate_id, request_type, status FROM privacy_request "
        "WHERE id = :id AND tenant_id = :tenant FOR UPDATE"
    ), {"id": request_id, "tenant": user.tenant_id})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "隐私申请不存在", 404)
    if row["status"] == "completed":
        return {"id": request_id, "status": "completed"}
    if row["request_type"] not in ("revoke", "delete"):
        raise TTCError("TTC-2002", "访问或更正申请需人工核验后处理", 409)
    candidate_id = row["candidate_id"]
    if candidate_id is None:
        raise TTCError("TTC-2001", "候选人已删除", 404)
    await session.execute(text(
        "UPDATE consent SET status = 'revoked', revoked_at = now() "
        "WHERE candidate_id = :id AND status = 'granted'"
    ), {"id": candidate_id})
    active_calls = (await session.execute(text(
        "SELECT id, provider_call_id FROM voice_session WHERE candidate_id = :id "
        "AND provider_call_id IS NOT NULL AND status NOT IN ('ended', 'failed', 'revoked')"
    ), {"id": candidate_id})).mappings().all()
    for call in active_calls:
        await enqueue_hangup(session, user.tenant_id, call["id"], call["provider_call_id"])
    await session.execute(text(
        "UPDATE voice_session SET status = 'revoked', ended_at = now(), "
        "end_reason = 'revoked' WHERE candidate_id = :id "
        "AND status NOT IN ('ended', 'failed', 'revoked')"
    ), {"id": candidate_id})
    uris = []
    if row["request_type"] == "delete":
        owner_id = (await session.execute(text(
            "SELECT user_id FROM candidate WHERE id = :id"
        ), {"id": candidate_id})).scalar_one_or_none()
        uris = (await session.execute(text(
            "SELECT file_uri FROM resume WHERE candidate_id = :id UNION ALL "
            "SELECT v.text_uri FROM resume_version v JOIN resume r ON r.id = v.resume_id "
            "WHERE r.candidate_id = :id AND v.text_uri IS NOT NULL UNION ALL "
            "SELECT t.audio_uri FROM voice_turn t JOIN voice_session s ON s.id = t.session_id "
            "WHERE s.candidate_id = :id AND t.audio_uri IS NOT NULL"
        ), {"id": candidate_id})).scalars().all()
        await session.execute(text(
            "DELETE FROM task WHERE (resource_type = 'candidate' AND resource_id = :id) "
            "OR (resource_type = 'resume' AND resource_id IN "
            "(SELECT id FROM resume WHERE candidate_id = :id))"
        ), {"id": candidate_id})
        await session.execute(text(
            "DELETE FROM assessment WHERE candidate_id = :id"
        ), {"id": candidate_id})
        await session.execute(text(
            "DELETE FROM evidence_conflict WHERE entity_id IN "
            "(SELECT entity_id FROM evidence WHERE claim_id IN "
            "(SELECT c.id FROM resume_claim c JOIN resume_version v "
            "ON v.id = c.resume_version_id JOIN resume r ON r.id = v.resume_id "
            "WHERE r.candidate_id = :id))"
        ), {"id": candidate_id})
        await session.execute(text(
            "DELETE FROM vector_ref WHERE object_type = 'evidence' AND object_id IN "
            "(SELECT e.id FROM evidence e JOIN resume_claim c ON c.id = e.claim_id "
            "JOIN resume_version v ON v.id = c.resume_version_id "
            "JOIN resume r ON r.id = v.resume_id WHERE r.candidate_id = :id)"
        ), {"id": candidate_id})
        await session.execute(text(
            "DELETE FROM evidence WHERE claim_id IN "
            "(SELECT c.id FROM resume_claim c JOIN resume_version v "
            "ON v.id = c.resume_version_id JOIN resume r ON r.id = v.resume_id "
            "WHERE r.candidate_id = :id)"
        ), {"id": candidate_id})
        await session.execute(text(
            "DELETE FROM vector_ref WHERE object_type = 'claim' AND object_id IN "
            "(SELECT c.id FROM resume_claim c JOIN resume_version v "
            "ON v.id = c.resume_version_id JOIN resume r ON r.id = v.resume_id "
            "WHERE r.candidate_id = :id)"
        ), {"id": candidate_id})
        await session.execute(text(
            "DELETE FROM candidate WHERE id = :id"
        ), {"id": candidate_id})
        if owner_id is not None:
            await session.execute(text(
                "UPDATE auth_session SET revoked_at = now() "
                "WHERE user_id = :user AND revoked_at IS NULL"
            ), {"user": owner_id})
            await session.execute(text(
                "UPDATE app_user SET email = :email, display_name = '已删除用户', "
                "password_hash = NULL, status = 'disabled' WHERE id = :user "
                "AND role = 'candidate'"
            ), {"user": owner_id, "email": f"deleted-{owner_id}@example.invalid"})
    await session.execute(text(
        "UPDATE privacy_request SET status = 'completed', payload = '{}'::jsonb, "
        "result = CAST(:result AS jsonb), handled_by = :user, completed_at = now() "
        "WHERE id = :id"
    ), {"id": request_id, "user": user.id,
        "result": json.dumps({"action": row["request_type"],
                              "storage_objects": len(uris)})})
    await record_audit(session, user, "privacy.process", "privacy_request", request_id)
    for uri in uris:
        try:
            await Storage().delete(uri)
        except Exception as exc:
            await session.rollback()
            raise TTCError("TTC-5004", "对象存储删除失败，隐私申请未完成", 503) from exc
    await session.commit()
    return {"id": request_id, "status": "completed", "storage_objects": len(uris)}
