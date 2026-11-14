"""通义千问实时语音（DashScope Realtime）适配层。

事件形状与 OpenAI Realtime 一致，但传输是 WebSocket 而不是 WebRTC：
浏览器不能直连（会把密钥暴露在页面里，也无法在撤回授权后切断），
所以由后端做 WebSocket 中转。

模型解析
--------
DashScope 的实时语音模型按快照退役：旧的别名（例如
``qwen3-omni-flash-realtime``）仍能完成 WebSocket 握手并回
``session.created``，但之后任何一帧都会返回 ``InvalidParameter:
Model not exist.`` 并断开 1007。因此不能只看握手成功，必须在建立连接后
下发一次 ``session.update`` 并等到 ``session.updated`` 才算可用；失败就
切换到下一个候选模型。解析结果缓存在进程内，避免每次通话都探测。

音色也随模型变化，例如 ``Cherry`` 只对 qwen3-omni 系列有效，
``qwen3.8-omni-flash-realtime`` / ``qwen3.5-omni-*`` 的可用音色是 ``Tina``。
配置里的音色只在与配置模型同名时使用。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets

from ttc.core.config import get_settings

INPUT_FORMAT = "pcm16"
OUTPUT_FORMAT = "pcm24"

# 显式声明的 VAD 参数（上游默认 threshold 0.5 / silence 800ms）。
# 默认阈值对笔记本外放的回声与键盘声偏敏感：AI 播报时麦克风收到自己的声音，
# 会被判成「候选人插话」并取消当前回复，听起来就是「说着说着就不说话了」。
# threshold 提到 0.65 让误触发明显变少；silence 缩到 600ms 让正常轮次更跟手。
# create_response=False：由服务端在候选人回答完成后统一创建下一轮，
# 保证创建前已写入最新问题账本和追问预算，避免 VAD 绕过服务端约束。
TURN_DETECTION: dict[str, Any] = {
    "type": "server_vad",
    "threshold": 0.65,
    "prefix_padding_ms": 300,
    "silence_duration_ms": 600,
    "create_response": False,
    "interrupt_response": True,
}


# 模型 -> (默认音色)。仅包含本账号实测可用的实时模型。
MODEL_PROFILES: dict[str, str] = {
    "qwen3-omni-flash-realtime": "Cherry",
    "qwen3-omni-flash-realtime-2025-09-15": "Cherry",
    "qwen-omni-turbo-realtime": "Chelsie",
    "qwen3.8-omni-flash-realtime": "Tina",
    "qwen3.5-omni-flash-realtime": "Tina",
    "qwen3.5-omni-plus-realtime": "Tina",
    "qwen-audio-3.1-realtime-flash": "longanqian_v3.1",
    "qwen-audio-3.0-realtime-flash": "longanqian",
}

# 配置模型不可用时的回退顺序（实测均能返回 session.updated）。
FALLBACK_MODELS = (
    "qwen3.8-omni-flash-realtime",
    "qwen3.5-omni-flash-realtime",
    "qwen3-omni-flash-realtime-2025-09-15",
)

_resolved_model: str | None = None
_resolve_lock: asyncio.Lock | None = None


def upstream_url(model: str) -> str:
    base = get_settings().dashscope_realtime_url.rstrip("/")
    return f"{base}?model={model}"


def session_update(instructions: str, voice: str) -> dict[str, Any]:
    """开场下发面试计划与音色；其余参数沿用服务端默认值。

    不覆盖 ``input_audio_transcription``：服务端按模型给出默认转写模型
    （qwen3.8 系默认 ``qwen3-asr-flash-realtime``），比写死 gummy 更稳。
    """
    return {
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "voice": voice,
            "instructions": instructions,
            "input_audio_format": INPUT_FORMAT,
            "output_audio_format": OUTPUT_FORMAT,
            "turn_detection": TURN_DETECTION,
        },
    }


def candidate_models() -> list[str]:
    ordered: list[str] = []
    for model in (get_settings().dashscope_realtime_model, *_resolved_order(), *FALLBACK_MODELS):
        if model and model not in ordered:
            ordered.append(model)
    return ordered


def _resolved_order() -> tuple[str, ...]:
    return (_resolved_model,) if _resolved_model else ()


def voice_for(model: str, configured_voice: str | None = None) -> str:
    if configured_voice and model == get_settings().dashscope_realtime_model:
        return configured_voice
    return MODEL_PROFILES.get(model, configured_voice or "Tina")


async def connect(model: str):
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY")
    return await websockets.connect(
        upstream_url(model),
        additional_headers={
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "OpenAI-Beta": "realtime=v1",
        },
        open_timeout=15,
        close_timeout=3,
        ping_interval=20,
        max_size=16 * 1024 * 1024,
    )


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _is_error(payload: dict[str, Any]) -> str | None:
    if payload.get("type") == "error":
        error = payload.get("error") or {}
        return str(error.get("message") or payload.get("message") or "上游返回错误")
    if payload.get("code") and not payload.get("type"):
        return str(payload.get("message") or payload.get("code"))
    return None


async def _close_quietly(ws) -> None:
    try:
        await ws.close()
    except Exception:
        pass


async def open_session(instructions: str, configured_voice: str | None = None):
    """建立上游会话并完成一次可验证的 handshake。

    返回 ``(ws, model, voice, initial_events)``；``initial_events`` 是握手期间
    被本函数消费掉的原始帧（``session.created`` / ``session.updated``），
    调用方应原样转发给浏览器，否则前端看不到会话已建立。
    """
    global _resolved_model, _resolve_lock
    if _resolve_lock is None:
        _resolve_lock = asyncio.Lock()
    errors: list[str] = []
    async with _resolve_lock:
        for model in candidate_models():
            voice = voice_for(model, configured_voice)
            try:
                ws = await connect(model)
            except Exception as exc:  # 网络/鉴权类错误，换下一个候选
                errors.append(f"{model}: {type(exc).__name__} {exc}")
                continue
            initial: list[str] = []
            try:
                created = await asyncio.wait_for(ws.recv(), timeout=12)
                initial.append(created)
                await ws.send(dumps(session_update(instructions, voice)))
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=12)
                    initial.append(raw)
                    payload = json.loads(raw)
                    error = _is_error(payload)
                    if error:
                        raise RuntimeError(error)
                    if payload.get("type") == "session.updated":
                        _resolved_model = model
                        return ws, model, voice, initial
            except Exception as exc:
                errors.append(f"{model}: {type(exc).__name__} {exc}")
                await _close_quietly(ws)
                continue
    raise RuntimeError("实时语音模型不可用：" + "；".join(errors))
