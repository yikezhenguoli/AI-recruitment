import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, WebSocket
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.adapters import qwen_realtime as qwen
from ttc.adapters.llm import LLMAdapter
from ttc.adapters.realtime import create_call, enqueue_hangup
from ttc.api.deps import Principal, current_user, require_roles
from ttc.api.v1.candidates import require_candidate
from ttc.api.v1.consents import require_consent
from ttc.api.v1.jobs import require_job
from ttc.api.v1.progress import authenticate
from ttc.core.config import get_settings
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7
from ttc.domains.interview.plan import (
    build_plan,
    parse_plan,
    plan_from_db,
    session_instructions,
)

router = APIRouter(tags=["voice"])
hr = require_roles("hr", "admin")

logger = logging.getLogger(__name__)

# 排查「AI 说着说着不说话了」：打开后把上游事件类型按顺序写进日志，
# 音频分片只记长度不记内容。默认关闭，避免正常通话刷屏。
RELAY_TRACE = os.environ.get("TTC_RELAY_TRACE", "").lower() in ("1", "true", "yes")
TRACE_SKIP = ("response.audio.delta", "response.output_audio.delta")

if RELAY_TRACE:
    # 项目本身没配置 root logger，不挂 handler 的话 info 级会被静默丢弃。
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s relay %(message)s", "%H:%M:%S"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class SessionInput(BaseModel):
    candidate_id: UUID
    job_id: UUID
    scenario: Literal["screen", "verify", "skill", "mock"] = "screen"
    provider: Literal["openai_realtime", "qwen_realtime"] = "openai_realtime"
    max_seconds: int = Field(default=1200, ge=60, le=7200)


class TurnInput(BaseModel):
    index: int = Field(ge=0)
    role: Literal["interviewer", "candidate", "system"]
    text: str = Field(min_length=1, max_length=20000)
    question_id: str | None = Field(default=None, max_length=80)


class FinishInput(BaseModel):
    reason: Literal["completed", "timeout", "candidate_end"] = "completed"
    turns: list[TurnInput] = Field(default_factory=list, max_length=200)


class MintInput(BaseModel):
    session_id: UUID
    connection_ephemeral: bool = True


async def require_session(session: AsyncSession, user: Principal, session_id: UUID):
    row = (await session.execute(text(
        "SELECT v.*, j.title AS job_title FROM voice_session v "
        "JOIN candidate c ON c.id = v.candidate_id "
        "LEFT JOIN job j ON j.id = v.job_id "
        "WHERE v.id = :id AND c.tenant_id = :tenant"
    ), {"id": session_id, "tenant": user.tenant_id})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "语音会话不存在", 404)
    if user.role == "candidate":
        await require_candidate(session, user, row["candidate_id"])
    elif user.role not in ("hr", "admin"):
        raise TTCError("TTC-1002", "无权访问语音会话", 403)
    return dict(row)


@router.post("/voice-sessions", status_code=201)
async def create_session(body: SessionInput, user: Principal = Depends(hr),
                         session: AsyncSession = Depends(get_session)):
    candidate = await require_candidate(session, user, body.candidate_id)
    job = await require_job(session, user, body.job_id)
    if job["status"] == "archived" or (candidate["job_id"] and
                                      candidate["job_id"] != body.job_id):
        raise TTCError("TTC-2002", "岗位已归档或与候选人不匹配", 409)
    consent_id = await require_consent(session, body.candidate_id, "voice_interview")
    parsed = (await session.execute(text(
        "SELECT 1 FROM resume_version v JOIN resume r ON r.id = v.resume_id "
        "WHERE r.candidate_id = :candidate AND v.status = 'done' LIMIT 1"
    ), {"candidate": body.candidate_id})).scalar_one_or_none()
    if parsed is None:
        raise TTCError("TTC-2002", "简历未解析完成", 409)
    # 按简历与岗位生成问题；生成失败会回退固定清单，不影响建会话。
    plan = await build_plan(session, body.candidate_id, body.job_id, body.scenario)
    session_id = uuid7()
    await session.execute(text(
        "INSERT INTO voice_session (id, candidate_id, job_id, consent_id, scenario, "
        "status, provider, model, plan_json, max_seconds) VALUES "
        "(:id, :candidate, :job, :consent, CAST(:scenario AS voice_scenario), "
        "'created', :provider, 'unconfigured', CAST(:plan AS jsonb), :max_seconds)"
    ), {"id": session_id, "candidate": body.candidate_id, "job": body.job_id,
        "consent": consent_id, "scenario": body.scenario, "provider": body.provider,
        "plan": json.dumps(plan, ensure_ascii=False), "max_seconds": body.max_seconds})
    await session.commit()
    return {"id": session_id, "status": "created", "consent_checked": True, "plan": plan}


@router.get("/voice-sessions")
async def list_voice_sessions(candidate_id: UUID | None = None,
                              status: str | None = None,
                              limit: int = Query(20, ge=1, le=100),
                              user: Principal = Depends(hr),
                              session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(text(
        "SELECT s.id, s.candidate_id, c.display_name AS candidate_name, s.job_id, "
        "j.title AS job_title, s.scenario::text AS scenario, s.status::text AS status, "
        "s.provider, s.model, s.max_seconds, s.created_at, s.started_at, s.ended_at, "
        "s.end_reason, EXISTS (SELECT 1 FROM call_report r WHERE r.session_id = s.id) "
        "AS has_report FROM voice_session s JOIN candidate c ON c.id = s.candidate_id "
        "LEFT JOIN job j ON j.id = s.job_id "
        "WHERE c.tenant_id = :tenant "
        "AND (CAST(:candidate AS uuid) IS NULL OR s.candidate_id = CAST(:candidate AS uuid)) "
        "AND (CAST(:status AS text) IS NULL OR s.status::text = CAST(:status AS text)) "
        "ORDER BY s.created_at DESC, s.id DESC LIMIT :limit"
    ), {"tenant": user.tenant_id, "candidate": candidate_id, "status": status,
        "limit": limit})).mappings().all()
    return {"items": [dict(row) for row in rows], "next_cursor": None}


@router.get("/voice-sessions/{session_id}")
async def get_voice_session(session_id: UUID, user: Principal = Depends(current_user),
                            session: AsyncSession = Depends(get_session)):
    row = await require_session(session, user, session_id)
    detail = {key: row[key] for key in ("id", "candidate_id", "job_id", "scenario", "status",
                                        "provider", "max_seconds", "plan_json", "created_at",
                                        "started_at", "ended_at", "end_reason")}
    # jsonb 经 asyncpg 读出来是字符串，不解析前端拿到的 plan_json 就是一串文本。
    detail["plan_json"] = parse_plan(row["plan_json"])
    return detail


@router.post("/realtime/mint")
async def mint(body: MintInput, user: Principal = Depends(require_roles("candidate")),
               session: AsyncSession = Depends(get_session)):
    row = await require_session(session, user, body.session_id)
    await require_consent(session, row["candidate_id"], "voice_interview")
    if row["status"] != "created":
        raise TTCError("TTC-2002", "会话不可建立实时连接", 409)
    settings = get_settings()
    if not settings.realtime_api_key or not settings.realtime_model:
        raise TTCError("TTC-5004", "未配置可用的实时语音凭证服务", 503)
    raise TTCError("TTC-2002", "直连凭证无法在撤回授权后切断通话，请使用会话 connect 接口", 410)


@router.post("/voice-sessions/{session_id}/connect")
async def connect_call(session_id: UUID, request: Request,
                       user: Principal = Depends(require_roles("candidate")),
                       session: AsyncSession = Depends(get_session)):
    row = await require_session(session, user, session_id)
    await require_consent(session, row["candidate_id"], "voice_interview")
    if row["status"] != "created":
        raise TTCError("TTC-2002", "会话不可再次建立连接", 409)
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/sdp":
        raise TTCError("TTC-4000", "需要 application/sdp", 415)
    offer = bytearray()
    async for chunk in request.stream():
        if len(offer) + len(chunk) > 65536:
            raise TTCError("TTC-4000", "SDP 内容超过 64 KB", 413)
        offer.extend(chunk)
    if len(offer) < 30 or not offer.startswith(b"v=0"):
        raise TTCError("TTC-4000", "SDP 内容无效", 422)
    answer, call_id = await create_call(
        bytes(offer), session_instructions(plan_from_db(row["plan_json"]), row["job_title"]))
    result = await session.execute(text(
        "UPDATE voice_session SET status = 'live', started_at = now(), "
        "provider_call_id = :call, model = :model WHERE id = :id "
        "AND status = 'created' AND EXISTS (SELECT 1 FROM consent "
        "WHERE id = consent_id AND status = 'granted' AND revoked_at IS NULL "
        "AND (expires_at IS NULL OR expires_at > now())) RETURNING id"
    ), {"id": session_id, "call": call_id, "model": get_settings().realtime_model})
    if result.scalar_one_or_none() is None:
        await session.rollback()
        from ttc.adapters.realtime import hangup_call
        try:
            await hangup_call(call_id)
        except Exception:
            await enqueue_hangup(session, user.tenant_id, session_id, call_id)
            await session.commit()
        raise TTCError("TTC-4001", "授权已撤回或会话已连接", 403)
    await session.commit()
    return Response(answer, media_type="application/sdp")


CONSENT_ALIVE = (
    "EXISTS (SELECT 1 FROM consent WHERE candidate_id = s.candidate_id "
    "AND purpose = 'voice_interview' AND status = 'granted' AND revoked_at IS NULL "
    "AND (expires_at IS NULL OR expires_at > now()))"
)

# 中转层只允许浏览器发这些事件；其余（例如改模型/改音色）一律拒绝。
CLIENT_EVENTS = frozenset({
    "input_audio_buffer.append", "input_audio_buffer.clear", "input_audio_buffer.commit",
    "conversation.item.create", "response.create", "response.cancel",
    "session.update", "conversation.item.truncate",
})
MAX_CLIENT_FRAME = 1024 * 1024


async def _close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except Exception:
        pass


async def _send(websocket: WebSocket, payload: dict) -> bool:
    try:
        await websocket.send_json(payload)
        return True
    except Exception:
        return False


async def _send_text(websocket: WebSocket, payload: str) -> bool:
    try:
        await websocket.send_text(payload)
        return True
    except Exception:
        return False


async def _finalize(session_id: UUID, status: str, reason: str, error: str | None = None):
    """落库收尾：只在会话仍处于 created/live 时生效，重复调用是幂等的。"""
    async for session in get_session():
        await session.execute(text(
            "UPDATE voice_session SET status = CAST(:status AS session_status), "
            "ended_at = now(), end_reason = :reason, error = COALESCE(:error, error) "
            "WHERE id = :id AND status IN ('created', 'live')"
        ), {"id": session_id, "status": status, "reason": reason, "error": error})
        await session.commit()


@router.websocket("/voice-sessions/{session_id}/realtime")
async def realtime_relay(websocket: WebSocket, session_id: UUID):
    """通义千问实时语音中转。

    浏览器拿不到 DashScope 密钥，也不能自行切断上游；中转层负责
    逐条转发事件，并每 5 秒复查授权与最长时长，撤回授权即断开。

    权限沿用 ``require_session`` 的口径：candidate 只能连自己的会话，
    hr/admin 可以连本租户的任意会话（演示用：前端目前只有招聘端）。
    """
    user = await authenticate(websocket)
    if user is None:
        return
    if user["role"] not in ("candidate", "hr", "admin"):
        await _close(websocket, 4403)
        return
    settings = get_settings()
    plan = None
    job_title = None
    max_seconds = 1200
    async for session in get_session():
        row = (await session.execute(text(
            "SELECT s.plan_json, s.candidate_id, s.max_seconds, c.user_id, "
            "j.title AS job_title FROM voice_session s "
            "JOIN candidate c ON c.id = s.candidate_id "
            "LEFT JOIN job j ON j.id = s.job_id "
            "WHERE s.id = :id AND c.tenant_id = :tenant"
        ), {"id": session_id, "tenant": user["tenant_id"]})).mappings().one_or_none()
        if row is None:
            await _close(websocket, 4404)
            return
        if user["role"] == "candidate" and row["user_id"] != user["id"]:
            await _close(websocket, 4403)
            return
        claimed = await session.execute(text(
            "UPDATE voice_session s SET status = 'live', "
            "started_at = COALESCE(started_at, now()), provider = 'qwen_realtime' "
            "WHERE s.id = :id AND s.status = 'created' "
            f"AND {CONSENT_ALIVE} RETURNING s.max_seconds"
        ), {"id": session_id})
        max_seconds = claimed.scalar_one_or_none()
        if max_seconds is None:
            await session.rollback()
            await _close(websocket, 4409)
            return
        await session.commit()
        plan = row["plan_json"]
        job_title = row["job_title"]

    instructions = session_instructions(plan_from_db(plan), job_title)

    try:
        upstream, model, voice, initial = await qwen.open_session(
            instructions, settings.dashscope_realtime_voice)
    except Exception as exc:
        await _finalize(session_id, "failed", "error", f"实时语音上游连接失败: {exc}"[:500])
        await _send(websocket, {"type": "error", "message": "实时语音服务连接失败"})
        await _close(websocket, 1011)
        return

    async for session in get_session():
        await session.execute(text(
            "UPDATE voice_session SET model = :model WHERE id = :id"
        ), {"id": session_id, "model": model})
        await session.commit()

    reason = "candidate_end"
    status = "ended"
    error_note: str | None = None
    tasks: list[asyncio.Task] = []
    try:
        for raw in initial:
            await _send_text(websocket, raw)
        await _send(websocket, {"type": "relay.ready", "model": model, "voice": voice,
                                "max_seconds": max_seconds})

        async def client_to_upstream():
            while True:
                raw = await websocket.receive_text()
                if len(raw) > MAX_CLIENT_FRAME:
                    await _send(websocket, {"type": "error",
                                            "message": "客户端事件超过 1 MB"})
                    continue
                try:
                    payload = json.loads(raw)
                except ValueError:
                    await _send(websocket, {"type": "error", "message": "非 JSON 客户端事件"})
                    continue
                if payload.get("type") not in CLIENT_EVENTS:
                    await _send(websocket, {"type": "error",
                                            "message": f"不支持的事件 {payload.get('type')}"})
                    continue
                # 上游只认 response.create 里自带的 instructions：握手时
                # session.update 的 instructions 不会让开场响应生效，缺了它
                # 直接回 "Cannot create response without input, history, or
                # instructions"。面试计划不下发浏览器，因此在这里补。
                if payload.get("type") == "response.create":
                    response = payload.get("response")
                    response = dict(response) if isinstance(response, dict) else {}
                    response.setdefault("instructions", instructions)
                    payload["response"] = response
                    raw = json.dumps(payload, ensure_ascii=False)
                await upstream.send(raw)

        async def upstream_to_client():
            async for message in upstream:
                if RELAY_TRACE:
                    if any(f'"type":"{skip}"' in message for skip in TRACE_SKIP):
                        logger.info("relay %s upstream audio chunk %d bytes",
                                    session_id, len(message))
                    else:
                        logger.info("relay %s upstream event %s", session_id, message[:600])
                if not await _send_text(websocket, message):
                    return "client_gone"
            return "upstream_gone"

        async def watch():
            loop = asyncio.get_running_loop()
            deadline = loop.time() + max_seconds
            while True:
                await asyncio.sleep(5)
                state = None
                async for session in get_session():
                    state = (await session.execute(text(
                        "SELECT s.status::text AS status, "
                        f"{CONSENT_ALIVE} AS consented FROM voice_session s WHERE s.id = :id"
                    ), {"id": session_id})).mappings().one_or_none()
                if state is None or state["status"] in ("ended", "failed", "revoked"):
                    return "closed"
                if not state["consented"]:
                    return "revoked"
                if loop.time() >= deadline:
                    return "timeout"

        tasks = [asyncio.create_task(coro) for coro in
                 (client_to_upstream(), upstream_to_client(), watch())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if task is tasks[2]:
                if exc is None:
                    reason = task.result()
                else:
                    reason = "closed"
            elif task is tasks[1]:
                # 上游先断开：正常关闭记为 end，异常记 failed
                if exc is not None:
                    status, reason = "failed", "error"
                    error_note = f"上游连接中断: {type(exc).__name__}: {exc}"[:500]
                else:
                    reason = "candidate_end" if task.result() == "client_gone" else "upstream_closed"
            else:
                # 浏览器先断开（WebSocketDisconnect）或上游拒收
                if exc is not None and not type(exc).__name__ == "WebSocketDisconnect":
                    status, reason = "failed", "error"
                    error_note = f"上游连接中断: {type(exc).__name__}: {exc}"[:500]
                else:
                    reason = "candidate_end"
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await upstream.close()
        except Exception:
            pass
        await _close(websocket, 1000)
        # 会话已被 HR / 授权流程置为终态时 reason == "closed"，不覆盖
        if reason != "closed":
            final_status = "revoked" if reason == "revoked" else status
            try:
                await _finalize(session_id, final_status, reason, error_note)
            except Exception:
                pass


async def save_turns(session: AsyncSession, session_id: UUID, turns: list[TurnInput]):
    if len({turn.index for turn in turns}) != len(turns):
        raise TTCError("TTC-4000", "轮次序号重复", 422)
    for turn in turns:
        await session.execute(text(
            "INSERT INTO voice_turn (id, session_id, turn_index, role, text, question_id, "
            "started_at) VALUES (:id, :session, :index, CAST(:role AS turn_role), "
            ":content, :question, now()) ON CONFLICT (session_id, turn_index) "
            "DO NOTHING"
        ), {"id": uuid7(), "session": session_id, "index": turn.index,
            "role": turn.role, "content": turn.text, "question": turn.question_id})


@router.post("/voice-sessions/{session_id}/turns")
async def add_turns(session_id: UUID, turns: list[TurnInput],
                    user: Principal = Depends(require_roles("candidate")),
                    session: AsyncSession = Depends(get_session)):
    row = await require_session(session, user, session_id)
    await require_consent(session, row["candidate_id"], "voice_interview")
    if row["status"] in ("ended", "failed", "revoked"):
        raise TTCError("TTC-2002", "会话已结束", 409)
    await save_turns(session, session_id, turns)
    await session.execute(text(
        "UPDATE voice_session SET status = 'live', started_at = COALESCE(started_at, now()) "
        "WHERE id = :id AND status IN ('created', 'connecting')"
    ), {"id": session_id})
    await session.commit()
    return {"session_id": session_id, "submitted": len(turns)}


FALLBACK_LIMIT = ("通话评估模型未能生成纪要；报告仅包含通话中提交的转写文字轮次，"
                  "服务端不校验转写来源")


async def summarize_turns(session: AsyncSession, session_id: UUID,
                          turns: list) -> tuple[dict, list[str], str]:
    """用大模型把转写整理成纪要；失败时退回只有元信息的占位摘要。"""
    if not turns:
        return ({"status": "unassessed", "turn_count": 0,
                 "limitations": ["本次通话没有产生转写内容"]}, [], "transcript-v1")
    row = (await session.execute(text(
        "SELECT v.plan_json, j.title AS job_title FROM voice_session v "
        "LEFT JOIN job j ON j.id = v.job_id WHERE v.id = :id"), {"id": session_id}
    )).mappings().one_or_none()
    plan = plan_from_db(row["plan_json"] if row else None)
    job_title = row["job_title"] if row else None
    try:
        result = await LLMAdapter().summarize_interview(
            plan, [dict(turn) for turn in turns], job_title)
    except TTCError as exc:
        return ({"status": "unassessed", "turn_count": len(turns),
                 "limitations": [f"纪要生成失败：{exc.message}", FALLBACK_LIMIT]},
                [], "transcript-v1")
    return ({"status": "assessed", "turn_count": len(turns),
             "overview": result["overview"], "qa": result["qa"],
             "limitations": result["limitations"]},
            result["followups"], "llm-interview-v1")


async def create_transcript_report(session: AsyncSession, session_id: UUID) -> UUID:
    existing = (await session.execute(text(
        "SELECT id FROM call_report WHERE session_id = :id"
    ), {"id": session_id})).scalar_one_or_none()
    if existing is not None:
        return existing
    turns = (await session.execute(text(
        "SELECT id, turn_index, role, text, question_id FROM voice_turn "
        "WHERE session_id = :id ORDER BY turn_index"
    ), {"id": session_id})).mappings().all()
    quote_rows = [{"turn_id": str(turn["id"]), "question_id": turn["question_id"],
                   "text": turn["text"][:1000]} for turn in turns if turn["role"] == "candidate"]
    summary, followups, model_version = await summarize_turns(session, session_id, list(turns))
    report_id = uuid7()
    inserted = await session.execute(text(
        "INSERT INTO call_report (id, session_id, status, summary, dimensions, quotes, "
        "crosscheck, followups, model_version) VALUES "
        "(:id, :session, 'ready', CAST(:summary AS jsonb), '[]'::jsonb, "
        "CAST(:quotes AS jsonb), CAST(:crosscheck AS jsonb), CAST(:followups AS jsonb), "
        ":model_version) "
        "ON CONFLICT (session_id) DO NOTHING RETURNING id"
    ), {"id": report_id, "session": session_id,
        "summary": json.dumps(summary, ensure_ascii=False),
        "quotes": json.dumps(quote_rows, ensure_ascii=False),
        "followups": json.dumps(followups, ensure_ascii=False),
        "model_version": model_version,
        "crosscheck": json.dumps({"consistent": [], "supplemented": [],
                                  "inconsistent": [], "unverified": []})})
    return inserted.scalar_one_or_none() or (await session.execute(text(
        "SELECT id FROM call_report WHERE session_id = :id"
    ), {"id": session_id})).scalar_one()


@router.post("/voice-sessions/{session_id}/finish", status_code=202)
async def finish_session(session_id: UUID, body: FinishInput,
                         user: Principal = Depends(current_user),
                         session: AsyncSession = Depends(get_session)):
    row = await require_session(session, user, session_id)
    await require_consent(session, row["candidate_id"], "voice_interview")
    if row["status"] in ("revoked", "failed"):
        raise TTCError("TTC-2002", "会话已失效", 409)
    # 实时通话结束时中转层已把状态置为 ended；此时仍要落盘轮次，
    # 否则报告里只剩空 transcript。
    await save_turns(session, session_id, body.turns)
    if row["status"] != "ended":
        await session.execute(text(
            "UPDATE voice_session SET status = 'ended', ended_at = now(), "
            "end_reason = :reason WHERE id = :id"
        ), {"id": session_id, "reason": body.reason})
        if row["provider_call_id"]:
            await enqueue_hangup(session, user.tenant_id, session_id, row["provider_call_id"])
    report_id = await create_transcript_report(session, session_id)
    await session.commit()
    return {"report_id": report_id, "status": "ready", "completed_at": datetime.now(UTC)}


@router.get("/voice-sessions/{session_id}/turns")
async def list_turns(session_id: UUID, user: Principal = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    await require_session(session, user, session_id)
    rows = (await session.execute(text(
        "SELECT id, turn_index, role::text AS role, text, question_id, started_at "
        "FROM voice_turn WHERE session_id = :id ORDER BY turn_index"
    ), {"id": session_id})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/voice-sessions/{session_id}/report")
async def report(session_id: UUID, user: Principal = Depends(hr),
                 session: AsyncSession = Depends(get_session)):
    """通话报告只对招聘方开放；候选人门户不返回纪要内容。"""
    row = await require_session(session, user, session_id)
    result = (await session.execute(text(
        "SELECT status, summary, dimensions, quotes, crosscheck, followups, model_version "
        "FROM call_report WHERE session_id = :id"
    ), {"id": session_id})).mappings().one_or_none()
    if result is None:
        raise TTCError("TTC-2001", "报告尚未生成", 404)
    return {"session": {"id": session_id, "scenario": row["scenario"],
                        "status": row["status"], "provider": row["provider"]},
            **dict(result)}


@router.get("/voice-sessions/{session_id}/summary")
async def call_summary(session_id: UUID, user: Principal = Depends(hr),
                       session: AsyncSession = Depends(get_session)):
    """HR 端沟通纪要：只返回模型整理后的字段，不含逐句转写。"""
    row = await require_session(session, user, session_id)
    result = (await session.execute(text(
        "SELECT status, summary, followups, model_version, updated_at "
        "FROM call_report WHERE session_id = :id"
    ), {"id": session_id})).mappings().one_or_none()
    if result is None:
        raise TTCError("TTC-2001", "该会话还没有生成沟通纪要", 404)
    summary = result["summary"] or {}
    return {"session_id": session_id,
            "candidate_id": row["candidate_id"],
            "scenario": row["scenario"],
            "session_status": row["status"],
            "report_status": result["status"],
            "model_version": result["model_version"],
            "generated_at": result["updated_at"],
            "turn_count": summary.get("turn_count", 0),
            "overview": summary.get("overview"),
            "qa": summary.get("qa", []),
            "followups": result["followups"] or [],
            "limitations": summary.get("limitations", [])}


@router.post("/voice-sessions/{session_id}/report/regenerate", status_code=202)
async def regenerate_report(session_id: UUID, user: Principal = Depends(hr),
                            session: AsyncSession = Depends(get_session)):
    """按现有转写重新生成纪要；供已结束但只有占位摘要的历史会话补纪要。"""
    await require_session(session, user, session_id)
    turns = (await session.execute(text(
        "SELECT id, turn_index, role, text, question_id FROM voice_turn "
        "WHERE session_id = :id ORDER BY turn_index"
    ), {"id": session_id})).mappings().all()
    if not turns:
        raise TTCError("TTC-2002", "该会话没有转写内容，无法生成纪要", 409)
    quote_rows = [{"turn_id": str(turn["id"]), "question_id": turn["question_id"],
                   "text": turn["text"][:1000]} for turn in turns if turn["role"] == "candidate"]
    summary, followups, model_version = await summarize_turns(session, session_id, list(turns))
    await session.execute(text(
        "INSERT INTO call_report (id, session_id, status, summary, dimensions, quotes, "
        "crosscheck, followups, model_version) VALUES "
        "(:id, :session, 'ready', CAST(:summary AS jsonb), '[]'::jsonb, "
        "CAST(:quotes AS jsonb), CAST(:crosscheck AS jsonb), CAST(:followups AS jsonb), "
        ":model_version) ON CONFLICT (session_id) DO UPDATE SET status = 'ready', "
        "summary = EXCLUDED.summary, quotes = EXCLUDED.quotes, "
        "followups = EXCLUDED.followups, model_version = EXCLUDED.model_version, "
        "updated_at = now()"
    ), {"id": uuid7(), "session": session_id,
        "summary": json.dumps(summary, ensure_ascii=False),
        "quotes": json.dumps(quote_rows, ensure_ascii=False),
        "followups": json.dumps(followups, ensure_ascii=False),
        "model_version": model_version,
        "crosscheck": json.dumps({"consistent": [], "supplemented": [],
                                  "inconsistent": [], "unverified": []})})
    await session.commit()
    return {"session_id": session_id, "status": "ready", "model_version": model_version}
