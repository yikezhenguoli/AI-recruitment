import asyncio
import base64
import binascii
import json
import logging
import math
import os
import sys
from array import array
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, WebSocket
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
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
from ttc.domains.interview import question_guard
from ttc.domains.interview.capability import normalize_capability
from ttc.domains.interview.conduct import (
    has_live_candidate_violation,
    interviewer_announces_conduct_termination,
    normalize_conduct,
)
from ttc.domains.interview.markdown_report import render_interview_markdown
from ttc.domains.interview.plan import (
    build_plan,
    merge_custom_questions,
    parse_plan,
    plan_from_db,
    plan_next_directed_turn,
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
    custom_questions: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("custom_questions")
    @classmethod
    def validate_custom_questions(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                raise ValueError("自定义问题必须是文本")
            text = " ".join(value.split())
            if not text:
                continue
            if len(text) > 200:
                raise ValueError("每个自定义问题不能超过 200 个字符")
            folded = text.casefold()
            if folded not in seen:
                cleaned.append(text)
                seen.add(folded)
        return cleaned[:5]


class TurnInput(BaseModel):
    index: int = Field(ge=0)
    role: Literal["interviewer", "candidate", "hr", "system"]
    text: str = Field(min_length=1, max_length=20000)
    question_id: str | None = Field(default=None, max_length=80)


class FinishInput(BaseModel):
    reason: Literal["completed", "timeout", "candidate_end"] = "completed"
    turns: list[TurnInput] = Field(default_factory=list, max_length=200)


class MintInput(BaseModel):
    session_id: UUID
    connection_ephemeral: bool = True


class FlowControlInput(BaseModel):
    action: Literal["pause", "resume"]


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
    plan = merge_custom_questions(
        await build_plan(session, body.candidate_id, body.job_id, body.scenario),
        body.custom_questions,
    )
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
        "s.provider, s.model, s.max_seconds, s.is_paused, s.created_at, s.started_at, s.ended_at, "
        "s.end_reason, EXISTS (SELECT 1 FROM call_report r WHERE r.session_id = s.id) "
        "AS has_report, "
        "(SELECT r.conduct_score FROM call_report r WHERE r.session_id = s.id) "
        "AS conduct_score, "
        "(SELECT r.conduct_status FROM call_report r WHERE r.session_id = s.id) "
        "AS conduct_status, "
        "COALESCE((SELECT r.conduct_veto FROM call_report r "
        "WHERE r.session_id = s.id), false) AS conduct_veto, "
        "(SELECT r.capability_score FROM call_report r WHERE r.session_id = s.id) "
        "AS capability_score, "
        "(SELECT r.capability_status FROM call_report r WHERE r.session_id = s.id) "
        "AS capability_status "
        "FROM voice_session s JOIN candidate c ON c.id = s.candidate_id "
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
                                        "started_at", "ended_at", "end_reason", "is_paused")}
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
CONDUCT_TERMINATION_GRACE_SECONDS = 8
HR_AUDIO_ACTIVITY_THRESHOLD = 0.008
HR_SPEAKER_HOLD_SECONDS = 2.5


def _pcm16_level(audio: str) -> float:
    """Return a lightweight RMS level for a base64 PCM16 audio chunk."""
    if not isinstance(audio, str) or not audio:
        return 0.0
    try:
        raw = base64.b64decode(audio, validate=True)
    except (ValueError, binascii.Error):
        return 0.0
    width = 2
    usable = len(raw) - (len(raw) % width)
    if usable <= 0:
        return 0.0
    samples = array("h")
    samples.frombytes(raw[:usable])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return 0.0
    stride = max(1, len(samples) // 2048)
    total = 0.0
    count = 0
    for value in samples[::stride]:
        normalized = value / 32768.0
        total += normalized * normalized
        count += 1
    return math.sqrt(total / max(1, count))


def response_text(payload: dict) -> str:
    """Extract assistant text across Realtime API event-version variants."""
    for key in ("transcript", "text", "delta"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    response = payload.get("response")
    if not isinstance(response, dict):
        return ""
    for item in response.get("output", []) if isinstance(response.get("output"), list) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if not isinstance(content, dict):
                continue
            for key in ("transcript", "text"):
                value = content.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


class LiveInterviewRoom:
    """Single-process audio room shared by the candidate and an HR observer."""

    def __init__(self, session_id: UUID):
        self.session_id = session_id
        self.candidate: WebSocket | None = None
        self.hr: WebSocket | None = None
        self.upstream = None
        self.model = "unconfigured"
        self.voice = ""
        self.instructions = ""
        self.plan: dict = {}
        self.max_seconds = 1200
        self.hr_control = False
        self.hr_mic_open = False
        self.interview_paused = False
        self.question_ledger = question_guard.QuestionLedger()
        self.awaiting_candidate_answer = False
        self.response_purpose = "idle"
        self.final_after_response = False
        self.opening_attempts = 0
        self.last_candidate_text = ""
        self.pending_question = ""
        self.pending_initial_id: str | None = None
        self.pending_question_kind: str | None = None
        self.next_turn_task: asyncio.Task | None = None
        self.last_voice_source = "candidate"
        self.last_voice_at = 0.0
        self.candidate_send_lock = asyncio.Lock()
        self.hr_send_lock = asyncio.Lock()
        self.upstream_send_lock = asyncio.Lock()

    def note_voice(self, source: str, audio: str) -> float:
        level = _pcm16_level(audio)
        if level < HR_AUDIO_ACTIVITY_THRESHOLD:
            return level
        self.last_voice_source = source
        self.last_voice_at = asyncio.get_running_loop().time()
        return level

    def current_speaker(self) -> str:
        if asyncio.get_running_loop().time() - self.last_voice_at <= HR_SPEAKER_HOLD_SECONDS:
            return self.last_voice_source
        return "candidate"

    async def send_candidate(self, payload: str | dict) -> bool:
        socket = self.candidate
        if socket is None:
            return False
        async with self.candidate_send_lock:
            try:
                if isinstance(payload, str):
                    await socket.send_text(payload)
                else:
                    await socket.send_json(payload)
                return True
            except Exception:
                return False

    async def send_hr(self, payload: str | dict) -> bool:
        socket = self.hr
        if socket is None:
            return False
        async with self.hr_send_lock:
            try:
                if isinstance(payload, str):
                    await socket.send_text(payload)
                else:
                    await socket.send_json(payload)
                return True
            except Exception:
                return False

    async def broadcast(self, payload: str | dict, *, include_candidate=True) -> None:
        if include_candidate:
            await self.send_candidate(payload)
        await self.send_hr(payload)

    async def send_upstream(self, payload: str | dict) -> None:
        if self.upstream is None:
            return
        raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        async with self.upstream_send_lock:
            await self.upstream.send(raw)

    def response_instructions(self, extra: str = "") -> str:
        return question_guard.response_instructions(
            self.instructions,
            self.question_ledger,
            extra,
        )

    def configure_plan(self, plan: dict) -> None:
        self.plan = plan if isinstance(plan, dict) else {}
        self.question_ledger.configure_initial_questions(
            self.plan.get("questions", [])
        )

    async def refresh_question_guard(self) -> None:
        """Apply the updated ledger to VAD-created as well as explicit responses."""
        await self.send_upstream({
            "type": "session.update",
            "session": {"instructions": self.response_instructions()},
        })

    async def send_question_response(
        self,
        instruction: str,
        *,
        purpose: str = "question",
        final: bool = False,
    ) -> None:
        self.response_purpose = purpose
        self.final_after_response = final
        await self.send_upstream({
            "type": "response.create",
            "response": {
                "instructions": self.response_instructions(instruction),
            },
        })

    def prepare_directed_question(
        self,
        question: str,
        *,
        initial_id: str | None,
        kind: str,
    ) -> None:
        self.pending_question = question.strip()[:240]
        self.pending_initial_id = initial_id
        self.pending_question_kind = kind

    async def start_interview(self) -> None:
        self.opening_attempts += 1
        first = self.question_ledger.next_initial_question()
        if first is None:
            await self.send_final_summary()
            return
        self.prepare_directed_question(
            first["text"],
            initial_id=first["id"],
            kind="initial",
        )
        await self.send_question_response(
            "请用一句话开场说明这是初步沟通，不做录用决定。"
            "随后只原样询问下面这一道初始问题，不要改写、不要补充、不要提出其他问题："
            f"{first['text']}"
        )

    async def continue_interview(self) -> None:
        if self.hr_control or self.interview_paused or self.upstream is None:
            return
        move = await plan_next_directed_turn(
            self.plan,
            self.question_ledger,
            self.last_candidate_text,
        )
        if move["action"] == "finish":
            await self.send_final_summary(summary=move.get("summary"))
            return
        question = str(move.get("question") or "").strip()
        if not question:
            await self.send_final_summary()
            return
        self.prepare_directed_question(
            question,
            initial_id=move.get("initial_question_id"),
            kind=move["action"],
        )
        await self.send_question_response(
            "只原样朗读下面这一道已经通过服务端校验的问题。"
            "不要改写、不要补充、不要总结、不要提出任何其他问题："
            f"{question}"
        )

    async def send_final_summary(self, summary: str | None = None) -> None:
        if self.upstream is None:
            return
        final_summary = (
            summary.strip()[:1200]
            if isinstance(summary, str) and summary.strip()
            else "感谢你的时间。本轮沟通到此结束，后续由 HR 结合本次回答和岗位要求进行人工复核。"
        )
        await self.send_question_response(
            "只原样朗读下面这段最终总结，不要提出任何问题，不要邀请候选人继续回答，"
            f"读完后结束通话：{final_summary}",
            purpose="final",
            final=True,
        )

    def repeat_last_question(self) -> str | None:
        if not self.question_ledger.questions:
            return None
        self.response_purpose = "repeat"
        self.final_after_response = False
        return self.question_ledger.questions[-1]

    def schedule_continuation(self) -> None:
        if self.next_turn_task is not None and not self.next_turn_task.done():
            self.next_turn_task.cancel()

        async def run() -> None:
            await asyncio.sleep(0.9)
            await self.continue_interview()

        self.next_turn_task = asyncio.create_task(run())

    async def resolve_completed_response(self, transcript: str) -> str | None:
        """Validate one completed AI response and decide whether the call ends."""
        purpose = self.response_purpose
        if purpose not in ("question", "repeat", "final"):
            self.response_purpose = "idle"
            if not self.interview_paused and not self.hr_control:
                self.schedule_continuation()
            return None
        if purpose == "repeat":
            self.awaiting_candidate_answer = True
            self.response_purpose = "idle"
            return None
        if self.final_after_response:
            self.response_purpose = "idle"
            self.final_after_response = False
            return "ai_completed"
        if self.pending_question:
            self.question_ledger.commit_response(self.pending_question)
        else:
            logger.warning(
                "Directed question response completed without pending question: %s",
                self.session_id,
            )
        self.awaiting_candidate_answer = True
        self.response_purpose = "idle"
        return None

    async def control_state(self) -> None:
        await self.broadcast({
            "type": "control.state",
            "ai_active": not self.hr_control and not self.interview_paused,
            "hr_control": self.hr_control,
            "hr_mic_open": self.hr_mic_open,
            "interview_paused": self.interview_paused,
        })

    async def take_control(self) -> None:
        if self.hr_control:
            await self.control_state()
            return
        self.hr_control = True
        self.response_purpose = "control"
        await self.send_upstream({"type": "response.cancel"})
        turn_detection = dict(qwen.TURN_DETECTION)
        turn_detection["create_response"] = False
        await self.send_upstream({
            "type": "session.update",
            "session": {"turn_detection": turn_detection},
        })
        await self.control_state()

    async def release_control(self) -> None:
        if not self.hr_control:
            await self.control_state()
            return
        self.hr_mic_open = False
        self.hr_control = False
        turn_detection = dict(qwen.TURN_DETECTION)
        turn_detection["create_response"] = False
        await self.send_upstream({
            "type": "session.update",
            "session": {"turn_detection": turn_detection},
        })
        await self.control_state()
        asyncio.create_task(self._resume_ai_after_transcript())

    async def _resume_ai_after_transcript(self) -> None:
        # Give the upstream ASR a short window to finish the final HR turn before
        # asking the model to continue from the full conversation context.
        await asyncio.sleep(0.8)
        if self.hr_control or self.interview_paused or self.upstream is None:
            return
        try:
            await self.continue_interview()
        except Exception:
            pass

    async def pause_interview(self) -> None:
        if self.interview_paused:
            await self.control_state()
            return
        self.interview_paused = True
        self.response_purpose = "control"
        await self.send_upstream({"type": "response.cancel"})
        turn_detection = dict(qwen.TURN_DETECTION)
        turn_detection["create_response"] = False
        await self.send_upstream({
            "type": "session.update",
            "session": {"turn_detection": turn_detection},
        })
        await self.control_state()
        await self.send_question_response(
            "请原样朗读下面这句话，不要提问，不要补充，不要继续面试："
            "面试流程被HR暂停，请等待面试流程恢复进行。",
            purpose="control",
        )

    async def resume_interview(self) -> None:
        if not self.interview_paused:
            await self.control_state()
            return
        self.interview_paused = False
        self.response_purpose = "control"
        turn_detection = dict(qwen.TURN_DETECTION)
        turn_detection["create_response"] = False
        await self.send_upstream({
            "type": "session.update",
            "session": {"turn_detection": turn_detection},
        })
        await self.control_state()
        await self.send_question_response(
            "请只原样朗读：面试流程已恢复，可以继续进行交流。"
            "本轮不要提问，也不要总结，读出后停止。",
            purpose="control",
        )


ROOMS: dict[UUID, LiveInterviewRoom] = {}


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
            "ended_at = now(), end_reason = :reason, error = COALESCE(:error, error), "
            "is_paused = false "
            "WHERE id = :id AND status IN ('created', 'live')"
        ), {"id": session_id, "status": status, "reason": reason, "error": error})
        await session.commit()


async def persist_conduct_termination(session_id: UUID, live_turns: list[dict]) -> None:
    """Persist server-observed turns before closing a policy-terminated call."""
    turns = [
        TurnInput(index=index, role=turn["role"], text=turn["text"])
        for index, turn in enumerate(live_turns[:200])
        if turn.get("role") in ("interviewer", "candidate", "hr")
        and isinstance(turn.get("text"), str)
        and turn["text"].strip()
    ]
    async for session in get_session():
        if turns:
            await save_turns(session, session_id, turns)
        await session.execute(text(
            "UPDATE voice_session SET status = 'ended', ended_at = now(), "
            "end_reason = 'conduct_violation', is_paused = false "
            "WHERE id = :id AND status IN ('created', 'live')"
        ), {"id": session_id})
        await session.execute(text(
            "INSERT INTO task (id, tenant_id, type, resource_type, resource_id) "
            "SELECT :task, c.tenant_id, 'voice_report', 'voice_session', s.id "
            "FROM voice_session s JOIN candidate c ON c.id = s.candidate_id "
            "WHERE s.id = :id AND NOT EXISTS ("
            "  SELECT 1 FROM task WHERE type = 'voice_report' "
            "  AND resource_id = :id AND status IN ('queued', 'running')"
            ")"
        ), {"task": uuid7(), "id": session_id})
        await session.commit()


def live_turn_inputs(live_turns: list[dict]) -> list[TurnInput]:
    """Convert server-observed live turns into stable persisted turn indexes."""
    return [
        TurnInput(index=index, role=turn["role"], text=turn["text"])
        for index, turn in enumerate(live_turns[:200])
        if turn.get("role") in ("interviewer", "candidate", "hr")
        and isinstance(turn.get("text"), str)
        and turn["text"].strip()
    ]


async def persist_live_transcript(session_id: UUID, live_turns: list[dict]) -> None:
    """Persist every completed live turn before a normal call is finalized."""
    turns = live_turn_inputs(live_turns)
    if not turns:
        return
    async for session in get_session():
        await save_turns(session, session_id, turns)
        await session.commit()


@router.websocket("/voice-sessions/{session_id}/realtime")
async def realtime_relay(websocket: WebSocket, session_id: UUID):
    """通义千问实时语音中转。

    浏览器拿不到 DashScope 密钥，也不能自行切断上游；中转层负责
    逐条转发事件，并每 5 秒复查授权与最长时长，撤回授权即断开。

    这是候选人专用音频通道。企业 HR 只能通过 ``/observe`` 旁听和接管，
    不能从企业端建立一条让 AI 面试 HR 的候选人连接。
    """
    user = await authenticate(websocket)
    if user is None:
        return
    if user["role"] != "candidate":
        await _close(websocket, 4403)
        return
    settings = get_settings()
    plan = None
    job_title = None
    max_seconds = 1200
    initially_paused = False
    async for session in get_session():
        row = (await session.execute(text(
            "SELECT s.plan_json, s.candidate_id, s.max_seconds, s.is_paused, c.user_id, "
            "j.title AS job_title FROM voice_session s "
            "JOIN candidate c ON c.id = s.candidate_id "
            "LEFT JOIN job j ON j.id = s.job_id "
            "WHERE s.id = :id AND c.tenant_id = :tenant"
        ), {"id": session_id, "tenant": user["tenant_id"]})).mappings().one_or_none()
        if row is None:
            await _close(websocket, 4404)
            return
        if row["user_id"] != user["id"]:
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
        initially_paused = bool(row["is_paused"])

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

    room = ROOMS.setdefault(session_id, LiveInterviewRoom(session_id))
    if room.candidate is not None:
        await _close(websocket, 4409)
        try:
            await upstream.close()
        except Exception:
            pass
        return
    room.candidate = websocket
    room.upstream = upstream
    room.model = model
    room.voice = voice
    room.instructions = instructions
    room.configure_plan(plan_from_db(plan))
    room.max_seconds = max_seconds
    room.interview_paused = initially_paused

    reason = "candidate_end"
    status = "ended"
    error_note: str | None = None
    tasks: list[asyncio.Task] = []
    live_turns: list[dict] = []
    live_turn_index: dict[str, int] = {}
    interviewer_stream_modes: dict[str, str] = {}
    last_candidate_text = ""
    conduct_signal = asyncio.Event()

    def upsert_live_turn(key: str, role: str, text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        existing = live_turn_index.get(key)
        if existing is None:
            live_turn_index[key] = len(live_turns)
            live_turns.append({"role": role, "text": cleaned})
        else:
            live_turns[existing] = {"role": role, "text": cleaned}

    def append_live_turn(key: str, role: str, delta: str) -> str:
        existing = live_turn_index.get(key)
        text = (live_turns[existing]["text"] if existing is not None else "") + delta
        upsert_live_turn(key, role, text)
        return text

    try:
        for raw in initial:
            await room.send_candidate(raw)
        await room.send_candidate({
            "type": "relay.ready",
            "model": model,
            "voice": voice,
            "max_seconds": max_seconds,
        })
        if room.hr is not None:
            await room.send_hr({
                "type": "relay.ready",
                "model": model,
                "voice": voice,
                "max_seconds": max_seconds,
                "observer": True,
            })
        await room.control_state()

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
                if payload.get("type") == "input_audio_buffer.append":
                    audio = payload.get("audio")
                    if isinstance(audio, str):
                        level = room.note_voice("candidate", audio)
                        await room.send_hr({
                            "type": "participant.audio",
                            "role": "candidate",
                            "audio": audio,
                            "sample_rate": 16000,
                        })
                        if room.hr_control and level < HR_AUDIO_ACTIVITY_THRESHOLD:
                            continue
                if payload.get("type") == "response.create":
                    if room.hr_control:
                        continue
                    if not room.question_ledger.questions and room.response_purpose == "idle":
                        await room.start_interview()
                    # 后续轮次只能由服务端在候选人回答完成后创建。浏览器的
                    # 空闲兜底 response.create 不允许绕过问题账本和追问预算。
                    continue
                await room.send_upstream(raw)

        async def upstream_to_client():
            nonlocal last_candidate_text
            end_after_response = False
            async for message in upstream:
                try:
                    payload = json.loads(message)
                except (TypeError, ValueError):
                    payload = {}
                outbound = message
                event_type = payload.get("type", "")
                if event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = str(payload.get("transcript") or "").strip()
                    if transcript:
                        speaker = room.current_speaker()
                        payload["speaker"] = speaker
                        outbound = json.dumps(payload, ensure_ascii=False)
                        role = "hr" if speaker == "hr" else "candidate"
                        if role == "candidate":
                            last_candidate_text = transcript
                            room.last_candidate_text = transcript
                            if question_guard.asks_to_repeat(transcript):
                                previous = room.repeat_last_question()
                                if previous:
                                    await room.send_question_response(
                                        "候选人明确请求重复上一题。请只原样重复下面问题一次，"
                                        "不要改写、不要追问、不要补充其他问题："
                                        f"{previous}",
                                        purpose="repeat",
                                    )
                            elif room.awaiting_candidate_answer:
                                room.awaiting_candidate_answer = False
                                room.schedule_continuation()
                        item_id = payload.get("item_id") or len(live_turns)
                        upsert_live_turn(f"{role}:{item_id}", role, transcript)
                        if role == "candidate" and has_live_candidate_violation(transcript):
                            conduct_signal.set()
                elif event_type == "conversation.item.input_audio_transcription.delta":
                    payload["speaker"] = room.current_speaker()
                    outbound = json.dumps(payload, ensure_ascii=False)
                elif event_type in (
                    "response.audio_transcript.delta",
                    "response.text.delta",
                    "response.output_audio_transcript.delta",
                    "response.output_text.delta",
                ):
                    response_key = str(
                        payload.get("response_id")
                        or payload.get("item_id")
                        or "current"
                    )
                    stream_mode = (
                        "audio"
                        if event_type.endswith("audio_transcript.delta")
                        else "text"
                    )
                    existing_mode = interviewer_stream_modes.get(response_key)
                    if existing_mode is None:
                        interviewer_stream_modes[response_key] = stream_mode
                    elif existing_mode != stream_mode:
                        # Some models emit the same content through both streams.
                        # Keep one canonical transcript to avoid duplicate turns.
                        payload = {}
                        event_type = "duplicate_stream"
                    if event_type != "duplicate_stream":
                        transcript = append_live_turn(
                            f"interviewer:{response_key}",
                            "interviewer",
                            str(payload.get("delta") or ""),
                        )
                        if (
                            last_candidate_text
                            and interviewer_announces_conduct_termination(transcript)
                        ):
                            conduct_signal.set()
                elif event_type in (
                    "response.audio_transcript.done",
                    "response.text.done",
                    "response.output_audio_transcript.done",
                    "response.output_text.done",
                ):
                    response_key = str(
                        payload.get("response_id")
                        or payload.get("item_id")
                        or "current"
                    )
                    transcript = response_text(payload)
                    if transcript:
                        upsert_live_turn(
                            f"interviewer:{response_key}", "interviewer", transcript
                        )
                        if (
                            last_candidate_text
                            and interviewer_announces_conduct_termination(transcript)
                        ):
                            conduct_signal.set()
                elif event_type == "response.done":
                    response_key = str(
                        payload.get("response_id")
                        or payload.get("item_id")
                        or "current"
                    )
                    index = live_turn_index.get(f"interviewer:{response_key}")
                    transcript = (
                        live_turns[index]["text"]
                        if index is not None
                        else response_text(payload)
                    )
                    resolved = await room.resolve_completed_response(transcript)
                    if resolved == "ai_completed":
                        end_after_response = True
                if RELAY_TRACE:
                    if any(f'"type":"{skip}"' in message for skip in TRACE_SKIP):
                        logger.info("relay %s upstream audio chunk %d bytes",
                                    session_id, len(message))
                    else:
                        logger.info("relay %s upstream event %s", session_id, message[:600])
                if not await room.send_candidate(outbound):
                    return "client_gone"
                await room.send_hr(outbound)
                if event_type == "response.done" and conduct_signal.is_set():
                    return "conduct_violation"
                if end_after_response:
                    return "ai_completed"
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

        async def conduct_watch():
            await conduct_signal.wait()
            await asyncio.sleep(CONDUCT_TERMINATION_GRACE_SECONDS)
            return "conduct_violation"

        client_task = asyncio.create_task(client_to_upstream())
        upstream_task = asyncio.create_task(upstream_to_client())
        state_task = asyncio.create_task(watch())
        conduct_task = asyncio.create_task(conduct_watch())
        tasks = [client_task, upstream_task, state_task, conduct_task]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        prioritized_done = [
            task
            for task in (upstream_task, conduct_task, state_task, client_task)
            if task in done
        ]
        for task in prioritized_done:
            if task.cancelled():
                continue
            exc = task.exception()
            if task is state_task:
                if exc is None:
                    reason = task.result()
                else:
                    reason = "closed"
            elif task is upstream_task:
                # 上游先断开：正常关闭记为 end，异常记 failed
                if exc is not None:
                    status, reason = "failed", "error"
                    error_note = f"上游连接中断: {type(exc).__name__}: {exc}"[:500]
                else:
                    result = task.result()
                    if result == "conduct_violation":
                        reason = "conduct_violation"
                    elif result == "ai_completed":
                        reason = "completed"
                    elif result == "client_gone":
                        reason = "candidate_end"
                    else:
                        reason = "upstream_closed"
            elif task is conduct_task:
                reason = "conduct_violation"
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
        if room.next_turn_task is not None and not room.next_turn_task.done():
            room.next_turn_task.cancel()
            await asyncio.gather(room.next_turn_task, return_exceptions=True)
        try:
            await upstream.close()
        except Exception:
            pass
        if reason == "conduct_violation":
            try:
                await persist_conduct_termination(session_id, live_turns)
            except Exception:
                logger.exception("Failed to persist conduct termination for %s", session_id)
            await room.broadcast({
                "type": "session.terminated",
                "reason": "conduct_violation",
                "message": "检测到严重不当言行，通话已由系统终止并记录。",
            })
        else:
            if reason != "revoked":
                try:
                    await persist_live_transcript(session_id, live_turns)
                except Exception:
                    logger.exception(
                        "Failed to persist live transcript for %s",
                        session_id,
                    )
            await room.broadcast({
                "type": "session.terminated",
                "reason": reason,
                "message": "本次语音沟通已结束。",
            })
        await _close(websocket, 1000)
        room.candidate = None
        if room.hr is not None:
            try:
                await room.hr.close(code=1000)
            except Exception:
                pass
            room.hr = None
        ROOMS.pop(session_id, None)
        # 会话已被 HR / 授权流程置为终态时 reason == "closed"，不覆盖
        if reason not in ("closed", "conduct_violation"):
            final_status = "revoked" if reason == "revoked" else status
            try:
                await _finalize(session_id, final_status, reason, error_note)
            except Exception:
                pass


@router.post("/voice-sessions/{session_id}/flow-control")
async def control_interview_flow(
    session_id: UUID,
    body: FlowControlInput,
    user: Principal = Depends(hr),
    session: AsyncSession = Depends(get_session),
):
    """HR 一键暂停或恢复全场面试流程。"""
    row = await require_session(session, user, session_id)
    if row["status"] != "live":
        raise TTCError("TTC-2002", "仅进行中的面试可以暂停或恢复", 409)
    room = ROOMS.get(session_id)
    if room is None or room.candidate is None or room.upstream is None:
        raise TTCError("TTC-2002", "候选人实时连接尚未就绪", 409)
    paused = body.action == "pause"
    await session.execute(text(
        "UPDATE voice_session SET is_paused = :paused WHERE id = :id"
    ), {"paused": paused, "id": session_id})
    await session.commit()
    if paused:
        await room.pause_interview()
    else:
        await room.resume_interview()
    return {
        "session_id": session_id,
        "status": row["status"],
        "interview_paused": paused,
        "ai_active": not paused and not room.hr_control,
    }


@router.websocket("/voice-sessions/{session_id}/observe")
async def observe_realtime_interview(websocket: WebSocket, session_id: UUID):
    """HR 实时旁听、暂停 AI、打开麦克风并与候选人直接沟通。"""
    user = await authenticate(websocket)
    if user is None:
        return
    if user["role"] not in ("hr", "admin"):
        await _close(websocket, 4403)
        return
    async for session in get_session():
        row = (await session.execute(text(
            "SELECT s.status::text AS status, s.model, s.max_seconds "
            "FROM voice_session s JOIN candidate c ON c.id = s.candidate_id "
            "WHERE s.id = :id AND c.tenant_id = :tenant "
            f"AND {CONSENT_ALIVE}"
        ), {"id": session_id, "tenant": user["tenant_id"]})).mappings().one_or_none()
        if row is None:
            await _close(websocket, 4404)
            return
        if row["status"] != "live":
            await _close(websocket, 4409)
            return

    room = ROOMS.get(session_id)
    if room is None or room.candidate is None or room.upstream is None:
        await _close(websocket, 4409)
        return
    if room.hr is not None:
        await _close(websocket, 4409)
        return
    room.hr = websocket
    try:
        await room.send_hr({
            "type": "relay.ready",
            "model": room.model,
            "voice": room.voice,
            "max_seconds": room.max_seconds,
            "observer": True,
        })
        await room.control_state()
        while True:
            raw = await websocket.receive_text()
            if len(raw) > MAX_CLIENT_FRAME:
                await room.send_hr({"type": "error", "message": "HR 音频帧超过 1 MB"})
                continue
            try:
                payload = json.loads(raw)
            except ValueError:
                await room.send_hr({"type": "error", "message": "非 JSON 控制事件"})
                continue
            event_type = payload.get("type")
            if event_type == "control.take":
                await room.take_control()
            elif event_type == "control.release":
                if room.hr_mic_open:
                    room.hr_mic_open = False
                    await room.send_upstream({"type": "input_audio_buffer.commit"})
                await room.release_control()
            elif event_type == "hr_audio.start":
                await room.take_control()
                room.hr_mic_open = True
                await room.control_state()
            elif event_type == "hr_audio.append":
                audio = payload.get("audio")
                if not isinstance(audio, str) or not audio:
                    continue
                if not room.hr_control:
                    await room.take_control()
                room.hr_mic_open = True
                level = room.note_voice("hr", audio)
                await room.send_candidate({
                    "type": "participant.audio",
                    "role": "hr",
                    "audio": audio,
                    "sample_rate": 16000,
                })
                if level >= HR_AUDIO_ACTIVITY_THRESHOLD:
                    await room.send_upstream({
                        "type": "input_audio_buffer.append",
                        "audio": audio,
                    })
            elif event_type == "hr_audio.commit":
                room.hr_mic_open = False
                await room.send_upstream({"type": "input_audio_buffer.commit"})
                await room.control_state()
            else:
                await room.send_hr({
                    "type": "error",
                    "message": f"不支持的控制事件 {event_type}",
                })
    except Exception:
        pass
    finally:
        if room.hr is websocket:
            room.hr = None
            room.hr_mic_open = False
            if room.hr_control:
                try:
                    await room.release_control()
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


async def assess_turns(turns: list) -> tuple[dict, str]:
    """审核言行；模型不可用时仍保留规则命中的明确严重事件。"""
    turn_data = [dict(turn) for turn in turns]
    if not turn_data:
        return normalize_conduct({}, []), "rule-conduct-v1"
    try:
        result = await LLMAdapter().assess_interview_conduct(turn_data)
    except TTCError as exc:
        return normalize_conduct({}, turn_data, exc.message), "rule-conduct-v1"
    except Exception as exc:
        return normalize_conduct(
            {}, turn_data, f"{type(exc).__name__}: 未预期的模型调用异常"
        ), "rule-conduct-v1"
    return normalize_conduct(result, turn_data), "llm-conduct-v1"


async def load_capability_context(
    session: AsyncSession,
    session_id: UUID,
) -> tuple[dict, str | None]:
    row = (await session.execute(text(
        "SELECT v.plan_json, j.title AS job_title FROM voice_session v "
        "LEFT JOIN job j ON j.id = v.job_id WHERE v.id = :id"
    ), {"id": session_id})).mappings().one_or_none()
    return (
        plan_from_db(row["plan_json"] if row else None),
        row["job_title"] if row else None,
    )


async def assess_capability(
    turns: list,
    plan: dict,
    job_title: str | None,
) -> tuple[dict, str]:
    """评价面试回答展示的岗位相关能力证据，失败时不伪造分数。"""
    turn_data = [dict(turn) for turn in turns]
    if not turn_data:
        return normalize_capability({}, []), "rule-capability-v1"
    try:
        result = await LLMAdapter().assess_interview_capability(
            plan, turn_data, job_title
        )
    except TTCError as exc:
        return normalize_capability({}, turn_data, exc.message), "transcript-capability-v1"
    except Exception as exc:
        return normalize_capability(
            {}, turn_data, f"{type(exc).__name__}: 未预期的模型调用异常"
        ), "transcript-capability-v1"
    return normalize_capability(result, turn_data), "llm-capability-v1"


def legacy_conduct() -> dict:
    """给迁移前生成、尚无可信言行结果的旧报告一个明确占位。"""
    result = normalize_conduct({}, [])
    result["summary"] = "该历史报告尚未进行言行审核，请重新整理后再复核。"
    result["limitations"] = [
        "历史报告没有言行审核结果。",
        *result["limitations"],
    ]
    return result


def legacy_capability() -> dict:
    """给迁移前生成的历史报告一个明确的能力评分占位。"""
    result = normalize_capability({}, [])
    result["summary"] = "该历史报告尚未生成面试能力评分，请重新整理后再复核。"
    result["limitations"] = [
        "历史报告没有面试能力评分结果。",
        *result["limitations"],
    ]
    return result


async def generate_interview_markdown(
    session: AsyncSession,
    session_id: UUID,
    *,
    force: bool = False,
) -> dict:
    """Render and persist the portable Markdown report for one interview."""
    row = (await session.execute(text(
        "SELECT r.id AS report_id, r.status AS report_status, r.summary, "
        "r.dimensions, r.quotes, r.crosscheck, r.followups, r.model_version, "
        "r.conduct_status, r.conduct_score, r.conduct_veto, r.conduct_json, "
        "r.conduct_model_version, r.capability_status, r.capability_score, "
        "r.capability_json, r.capability_model_version, r.markdown_content, "
        "r.markdown_hash, r.markdown_generated_at, "
        "s.id AS session_id, s.status AS session_status, s.scenario, s.provider, "
        "s.model, s.created_at, s.started_at, s.ended_at, s.end_reason, "
        "s.max_seconds, s.plan_json, "
        "c.id AS candidate_id, c.display_name AS candidate_name, "
        "j.id AS job_id, j.title AS job_title "
        "FROM call_report r "
        "JOIN voice_session s ON s.id = r.session_id "
        "JOIN candidate c ON c.id = s.candidate_id "
        "LEFT JOIN job j ON j.id = s.job_id "
        "WHERE r.session_id = :id AND c.tenant_id IS NOT NULL"
    ), {"id": session_id})).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "报告尚未生成", 404)
    if row["markdown_content"] and not force:
        return {
            "markdown_ready": True,
            "markdown_generated_at": row["markdown_generated_at"],
            "markdown_sha256": row["markdown_hash"],
        }
    turns = (await session.execute(text(
        "SELECT id, turn_index, role::text AS role, text, question_id, started_at "
        "FROM voice_turn WHERE session_id = :id ORDER BY turn_index"
    ), {"id": session_id})).mappings().all()
    report = {
        "id": row["report_id"],
        "status": row["report_status"],
        "summary": row["summary"] or {},
        "dimensions": row["dimensions"] or [],
        "quotes": row["quotes"] or [],
        "crosscheck": row["crosscheck"] or {},
        "followups": row["followups"] or [],
        "model_version": row["model_version"],
        "conduct_status": row["conduct_status"],
        "conduct_score": row["conduct_score"],
        "conduct_veto": row["conduct_veto"],
        "conduct": row["conduct_json"] or legacy_conduct(),
        "conduct_model_version": row["conduct_model_version"],
        "capability_status": row["capability_status"],
        "capability_score": row["capability_score"],
        "capability": row["capability_json"] or legacy_capability(),
        "capability_model_version": row["capability_model_version"],
    }
    generated_at = datetime.now(UTC)
    markdown, digest = render_interview_markdown(
        session={
            "id": row["session_id"],
            "status": row["session_status"],
            "scenario": row["scenario"],
            "provider": row["provider"],
            "model": row["model"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "end_reason": row["end_reason"],
            "max_seconds": row["max_seconds"],
        },
        candidate={"id": row["candidate_id"], "display_name": row["candidate_name"]},
        job={"id": row["job_id"], "title": row["job_title"]},
        plan=plan_from_db(row["plan_json"]),
        report=report,
        turns=[dict(turn) for turn in turns],
        generated_at=generated_at,
    )
    await session.execute(text(
        "UPDATE call_report SET markdown_content = :content, markdown_hash = :hash, "
        "markdown_generated_at = :generated, updated_at = now() WHERE session_id = :id"
    ), {"content": markdown, "hash": digest, "generated": generated_at, "id": session_id})
    return {
        "markdown_ready": True,
        "markdown_generated_at": generated_at,
        "markdown_sha256": digest,
    }


async def create_transcript_report(session: AsyncSession, session_id: UUID) -> UUID:
    existing = (await session.execute(text(
        "SELECT id, markdown_content FROM call_report WHERE session_id = :id"
    ), {"id": session_id})).mappings().one_or_none()
    if existing is not None:
        await generate_interview_markdown(session, session_id)
        return existing["id"]
    turns = (await session.execute(text(
        "SELECT id, turn_index, role, text, question_id FROM voice_turn "
        "WHERE session_id = :id ORDER BY turn_index"
    ), {"id": session_id})).mappings().all()
    quote_rows = [{"turn_id": str(turn["id"]), "question_id": turn["question_id"],
                   "text": turn["text"][:1000]} for turn in turns if turn["role"] == "candidate"]
    plan, job_title = await load_capability_context(session, session_id)
    (
        (summary, followups, model_version),
        (conduct, conduct_model_version),
        (capability, capability_model_version),
    ) = await asyncio.gather(
        summarize_turns(session, session_id, list(turns)),
        assess_turns(list(turns)),
        assess_capability(list(turns), plan, job_title),
    )
    report_id = uuid7()
    inserted = await session.execute(text(
        "INSERT INTO call_report (id, session_id, status, summary, dimensions, quotes, "
        "crosscheck, followups, model_version, conduct_status, conduct_score, "
        "conduct_veto, conduct_json, conduct_model_version, capability_status, "
        "capability_score, capability_json, capability_model_version) VALUES "
        "(:id, :session, 'ready', CAST(:summary AS jsonb), '[]'::jsonb, "
        "CAST(:quotes AS jsonb), CAST(:crosscheck AS jsonb), CAST(:followups AS jsonb), "
        ":model_version, :conduct_status, :conduct_score, :conduct_veto, "
        "CAST(:conduct AS jsonb), :conduct_model_version, :capability_status, "
        ":capability_score, CAST(:capability AS jsonb), :capability_model_version) "
        "ON CONFLICT (session_id) DO NOTHING RETURNING id"
    ), {"id": report_id, "session": session_id,
        "summary": json.dumps(summary, ensure_ascii=False),
        "quotes": json.dumps(quote_rows, ensure_ascii=False),
        "followups": json.dumps(followups, ensure_ascii=False),
        "model_version": model_version,
        "conduct_status": conduct["status"],
        "conduct_score": conduct["score"],
        "conduct_veto": conduct["veto"],
        "conduct": json.dumps(conduct, ensure_ascii=False),
        "conduct_model_version": conduct_model_version,
        "capability_status": capability["status"],
        "capability_score": capability["score"],
        "capability": json.dumps(capability, ensure_ascii=False),
        "capability_model_version": capability_model_version,
        "crosscheck": json.dumps({"consistent": [], "supplemented": [],
                                  "inconsistent": [], "unverified": []})})
    report_id = inserted.scalar_one_or_none() or (await session.execute(text(
        "SELECT id FROM call_report WHERE session_id = :id"
    ), {"id": session_id})).scalar_one()
    await generate_interview_markdown(session, session_id)
    return report_id


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
            "end_reason = :reason, is_paused = false WHERE id = :id"
        ), {"id": session_id, "reason": body.reason})
        if row["provider_call_id"]:
            await enqueue_hangup(session, user.tenant_id, session_id, row["provider_call_id"])
    report_id = await create_transcript_report(session, session_id)
    await session.commit()
    return {
        "report_id": report_id,
        "status": "ready",
        "markdown_ready": True,
        "completed_at": datetime.now(UTC),
    }


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
        "SELECT status, summary, dimensions, quotes, crosscheck, followups, model_version, "
        "conduct_status, conduct_score, conduct_veto, conduct_json, conduct_model_version, "
        "capability_status, capability_score, capability_json, capability_model_version, "
        "markdown_generated_at, markdown_hash "
        "FROM call_report WHERE session_id = :id"
    ), {"id": session_id})).mappings().one_or_none()
    if result is None:
        raise TTCError("TTC-2001", "报告尚未生成", 404)
    payload = dict(result)
    payload["conduct"] = payload.pop("conduct_json") or legacy_conduct()
    payload["capability"] = payload.pop("capability_json") or legacy_capability()
    payload["markdown_ready"] = bool(payload.get("markdown_generated_at"))
    return {"session": {"id": session_id, "scenario": row["scenario"],
                        "status": row["status"], "provider": row["provider"]},
            **payload}


@router.get("/voice-sessions/{session_id}/report/markdown")
async def download_report_markdown(
    session_id: UUID,
    user: Principal = Depends(hr),
    session: AsyncSession = Depends(get_session),
):
    """Download the HR-only Markdown report for a completed interview."""
    await require_session(session, user, session_id)
    markdown = (await session.execute(text(
        "SELECT markdown_content FROM call_report WHERE session_id = :id"
    ), {"id": session_id})).scalar_one_or_none()
    if markdown is None:
        exists = (await session.execute(text(
            "SELECT 1 FROM call_report WHERE session_id = :id"
        ), {"id": session_id})).scalar_one_or_none()
        if exists is None:
            raise TTCError("TTC-2001", "报告尚未生成", 404)
        await generate_interview_markdown(session, session_id)
        await session.commit()
        markdown = (await session.execute(text(
            "SELECT markdown_content FROM call_report WHERE session_id = :id"
        ), {"id": session_id})).scalar_one_or_none()
    if not markdown:
        raise TTCError("TTC-5004", "Markdown 报告不可用", 503)
    return Response(
        content=markdown.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="interview-report-{session_id}.md"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/voice-sessions/{session_id}/summary")
async def call_summary(session_id: UUID, user: Principal = Depends(hr),
                       session: AsyncSession = Depends(get_session)):
    """HR 端沟通纪要：只返回模型整理后的字段，不含逐句转写。"""
    row = await require_session(session, user, session_id)
    result = (await session.execute(text(
        "SELECT status, summary, followups, model_version, updated_at, conduct_json, "
        "conduct_status, conduct_score, conduct_veto, conduct_model_version, "
        "capability_status, capability_score, capability_json, capability_model_version, "
        "markdown_generated_at, markdown_hash "
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
            "limitations": summary.get("limitations", []),
            "conduct": result["conduct_json"] or legacy_conduct(),
            "conduct_status": result["conduct_status"],
            "conduct_score": result["conduct_score"],
            "conduct_veto": result["conduct_veto"],
            "conduct_model_version": result["conduct_model_version"],
            "capability": result["capability_json"] or legacy_capability(),
            "capability_status": result["capability_status"],
            "capability_score": result["capability_score"],
            "capability_model_version": result["capability_model_version"],
            "markdown_ready": bool(result["markdown_generated_at"]),
            "markdown_generated_at": result["markdown_generated_at"],
            "markdown_sha256": result["markdown_hash"]}


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
    plan, job_title = await load_capability_context(session, session_id)
    (
        (summary, followups, model_version),
        (conduct, conduct_model_version),
        (capability, capability_model_version),
    ) = await asyncio.gather(
        summarize_turns(session, session_id, list(turns)),
        assess_turns(list(turns)),
        assess_capability(list(turns), plan, job_title),
    )
    await session.execute(text(
        "INSERT INTO call_report (id, session_id, status, summary, dimensions, quotes, "
        "crosscheck, followups, model_version, conduct_status, conduct_score, "
        "conduct_veto, conduct_json, conduct_model_version, capability_status, "
        "capability_score, capability_json, capability_model_version) VALUES "
        "(:id, :session, 'ready', CAST(:summary AS jsonb), '[]'::jsonb, "
        "CAST(:quotes AS jsonb), CAST(:crosscheck AS jsonb), CAST(:followups AS jsonb), "
        ":model_version, :conduct_status, :conduct_score, :conduct_veto, "
        "CAST(:conduct AS jsonb), :conduct_model_version, :capability_status, "
        ":capability_score, CAST(:capability AS jsonb), :capability_model_version) "
        "ON CONFLICT (session_id) DO UPDATE SET status = 'ready', "
        "summary = EXCLUDED.summary, quotes = EXCLUDED.quotes, "
        "followups = EXCLUDED.followups, model_version = EXCLUDED.model_version, "
        "conduct_status = EXCLUDED.conduct_status, "
        "conduct_score = EXCLUDED.conduct_score, "
        "conduct_veto = EXCLUDED.conduct_veto, "
        "conduct_json = EXCLUDED.conduct_json, "
        "conduct_model_version = EXCLUDED.conduct_model_version, "
        "capability_status = EXCLUDED.capability_status, "
        "capability_score = EXCLUDED.capability_score, "
        "capability_json = EXCLUDED.capability_json, "
        "capability_model_version = EXCLUDED.capability_model_version, "
        "updated_at = now()"
    ), {"id": uuid7(), "session": session_id,
        "summary": json.dumps(summary, ensure_ascii=False),
        "quotes": json.dumps(quote_rows, ensure_ascii=False),
        "followups": json.dumps(followups, ensure_ascii=False),
        "model_version": model_version,
        "conduct_status": conduct["status"],
        "conduct_score": conduct["score"],
        "conduct_veto": conduct["veto"],
        "conduct": json.dumps(conduct, ensure_ascii=False),
        "conduct_model_version": conduct_model_version,
        "capability_status": capability["status"],
        "capability_score": capability["score"],
        "capability": json.dumps(capability, ensure_ascii=False),
        "capability_model_version": capability_model_version,
        "crosscheck": json.dumps({"consistent": [], "supplemented": [],
                                  "inconsistent": [], "unverified": []})})
    await generate_interview_markdown(session, session_id, force=True)
    await session.commit()
    return {"session_id": session_id, "status": "ready", "model_version": model_version}
