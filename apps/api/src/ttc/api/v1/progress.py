import asyncio
from uuid import UUID

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from ttc.core.db import get_session
from ttc.core.security import decode_access_token

router = APIRouter(tags=["progress"])


async def authenticate(websocket: WebSocket):
    await websocket.accept()
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        user_id = decode_access_token(auth["token"])
    except (TimeoutError, KeyError, TypeError, ValueError, jwt.PyJWTError, WebSocketDisconnect):
        await websocket.close(code=4401)
        return None
    async for session in get_session():
        user = (await session.execute(text(
            "SELECT id, tenant_id, role FROM app_user WHERE id = :id AND status = 'active'"
        ), {"id": user_id})).mappings().one_or_none()
        if user is None:
            await websocket.close(code=4401)
            return None
        return dict(user)


@router.websocket("/ws/progress/{task_id}")
async def task_progress(websocket: WebSocket, task_id: UUID):
    user = await authenticate(websocket)
    if user is None:
        return
    prior = None
    while True:
        async for session in get_session():
            row = (await session.execute(text(
                "SELECT status::text AS status, type, resource_id, resource_type, attempts, error "
                "FROM task WHERE id = :id AND tenant_id = :tenant"
            ), {"id": task_id, "tenant": user["tenant_id"]})).mappings().one_or_none()
        if row is None:
            await websocket.close(code=4404)
            return
        if user["role"] == "candidate":
            async for session in get_session():
                owned = (await session.execute(text(
                    "SELECT 1 FROM candidate c WHERE c.user_id = :user AND c.tenant_id = :tenant "
                    "AND ((:kind = 'candidate' AND c.id = :resource) OR "
                    "(:kind = 'resume' AND EXISTS (SELECT 1 FROM resume r "
                    "WHERE r.id = :resource AND r.candidate_id = c.id)))"
                ), {"user": user["id"], "tenant": user["tenant_id"],
                    "kind": row["resource_type"], "resource": row["resource_id"]}
                )).scalar_one_or_none()
            if not owned:
                await websocket.close(code=4403)
                return
        elif user["role"] not in ("hr", "admin"):
            await websocket.close(code=4403)
            return
        state = dict(row)
        if state != prior:
            status = row["status"]
            await websocket.send_json({"type": "done" if status == "succeeded" else
                                       "error" if status in ("failed", "canceled") else
                                       "progress", "task_id": str(task_id),
                                       "stage": status, "resource_id": str(row["resource_id"]),
                                       "attempts": row["attempts"], "message": row["error"]})
            prior = state
        if row["status"] in ("succeeded", "failed", "canceled"):
            await websocket.close()
            return
        await asyncio.sleep(1)


@router.websocket("/ws/voice/{session_id}")
async def voice_status(websocket: WebSocket, session_id: UUID):
    user = await authenticate(websocket)
    if user is None:
        return
    prior = None
    while True:
        async for session in get_session():
            row = (await session.execute(text(
                "SELECT s.status::text AS status, s.candidate_id, c.user_id "
                "FROM voice_session s JOIN candidate c ON c.id = s.candidate_id "
                "WHERE s.id = :id AND c.tenant_id = :tenant"
            ), {"id": session_id, "tenant": user["tenant_id"]})).mappings().one_or_none()
            allowed = row is not None and (user["role"] in ("hr", "admin") or
                                           (user["role"] == "candidate" and
                                            row["user_id"] == user["id"]))
            consent = None
            if allowed:
                consent = (await session.execute(text(
                    "SELECT 1 FROM consent WHERE candidate_id = :candidate "
                    "AND purpose = 'voice_interview' AND status = 'granted' "
                    "AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now()) "
                    "LIMIT 1"
                ), {"candidate": row["candidate_id"]})).scalar_one_or_none()
        if not allowed:
            await websocket.close(code=4403)
            return
        status = row["status"] if consent else "revoked"
        if status != prior:
            await websocket.send_json({"type": "state", "state": status})
            prior = status
        if status in ("ended", "failed", "revoked"):
            await websocket.close()
            return
        await asyncio.sleep(1)
