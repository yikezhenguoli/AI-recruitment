import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.adapters.realtime import enqueue_hangup
from ttc.api.deps import Principal, require_roles
from ttc.api.v1.candidates import require_candidate
from ttc.core.audit import record_audit
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7

router = APIRouter(tags=["consents"])
candidate_role = require_roles("candidate")


class ConsentInput(BaseModel):
    candidate_id: UUID
    purpose: Literal["resume_process", "voice_interview", "recording", "model_training"]
    scope: dict = Field(default_factory=dict)
    text_version: str = Field(min_length=1)
    acknowledged: bool


@router.post("/consents", status_code=201)
async def create_consent(body: ConsentInput, user: Principal = Depends(candidate_role),
                         session: AsyncSession = Depends(get_session)):
    await require_candidate(session, user, body.candidate_id)
    if not body.acknowledged:
        raise TTCError("TTC-4001", "必须明确确认告知内容", 403)
    consent_id = uuid7()
    row = (await session.execute(
        text("INSERT INTO consent (id, candidate_id, purpose, status, scope, "
             "text_version, accepted_at) VALUES (:id, :candidate, "
             "CAST(:purpose AS consent_purpose), 'granted', CAST(:scope AS jsonb), "
             ":text_version, now()) RETURNING id, candidate_id, purpose, status, "
             "scope, text_version, accepted_at"),
        {"id": consent_id, "candidate": body.candidate_id, "purpose": body.purpose,
         "scope": json.dumps(body.scope, ensure_ascii=False), "text_version": body.text_version},
    )).mappings().one()
    await record_audit(session, user, "consent.grant", "consent", consent_id)
    await session.commit()
    return dict(row)


@router.post("/consents/{consent_id}/revoke")
async def revoke_consent(consent_id: UUID, user: Principal = Depends(candidate_role),
                         session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        text("SELECT c.candidate_id, c.purpose, c.status FROM consent c "
             "JOIN candidate p ON p.id = c.candidate_id WHERE c.id = :id "
             "AND p.tenant_id = :tenant AND p.user_id = :user FOR UPDATE OF c"),
        {"id": consent_id, "tenant": user.tenant_id, "user": user.id},
    )).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "授权记录不存在", 404)
    if row["status"] != "granted":
        raise TTCError("TTC-2002", "授权已失效", 409)
    await session.execute(
        text("UPDATE consent SET status = 'revoked', revoked_at = now() WHERE id = :id"),
        {"id": consent_id},
    )
    if row["purpose"] == "voice_interview":
        active_calls = (await session.execute(text(
            "SELECT id, provider_call_id FROM voice_session WHERE candidate_id = :candidate "
            "AND provider_call_id IS NOT NULL AND status NOT IN ('ended', 'failed', 'revoked')"
        ), {"candidate": row["candidate_id"]})).mappings().all()
        for call in active_calls:
            await enqueue_hangup(session, user.tenant_id, call["id"],
                                 call["provider_call_id"])
        await session.execute(
            text("UPDATE voice_session SET status = 'revoked', ended_at = now(), "
                 "end_reason = 'revoked' WHERE candidate_id = :candidate "
                 "AND status NOT IN ('ended', 'failed', 'revoked')"),
            {"candidate": row["candidate_id"]},
        )
    await record_audit(session, user, "consent.revoke", "consent", consent_id)
    await session.commit()
    return {"id": consent_id, "status": "revoked"}


async def require_consent(session: AsyncSession, candidate_id: UUID, purpose: str):
    row = (await session.execute(
        text("SELECT id FROM consent WHERE candidate_id = :candidate "
             "AND purpose = CAST(:purpose AS consent_purpose) "
             "AND status = 'granted' AND revoked_at IS NULL "
             "AND (expires_at IS NULL OR expires_at > now()) "
             "ORDER BY accepted_at DESC, created_at DESC LIMIT 1"),
        {"candidate": candidate_id, "purpose": purpose},
    )).scalar_one_or_none()
    if row is None:
        raise TTCError("TTC-4001", "候选人尚未授予对应授权", 403)
    return row
