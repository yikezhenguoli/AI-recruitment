import json
import re
from urllib.parse import urlparse

import httpx
from sqlalchemy import text

from ttc.core.config import get_settings
from ttc.core.errors import TTCError
from ttc.core.security import uuid7


async def create_call(offer: bytes, instructions: str) -> tuple[bytes, str]:
    settings = get_settings()
    if not settings.realtime_api_key or not settings.realtime_model:
        raise TTCError("TTC-5004", "实时语音服务尚未配置", 503)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            result = await client.post(
                "https://api.openai.com/v1/realtime/calls",
                headers={"Authorization": f"Bearer {settings.realtime_api_key}"},
                files={
                    "sdp": ("offer.sdp", offer, "application/sdp"),
                    "session": (
                        None,
                        json.dumps({"type": "realtime", "model": settings.realtime_model,
                                    "instructions": instructions}, ensure_ascii=False),
                        "application/json",
                    ),
                },
            )
            result.raise_for_status()
            path = urlparse(result.headers.get("location", "")).path
            call_id = path.rsplit("/", 1)[-1]
            if not re.fullmatch(r"rtc_[A-Za-z0-9_-]{1,120}", call_id):
                raise ValueError("Missing provider call ID")
            return result.content, call_id
    except (httpx.HTTPError, ValueError) as exc:
        raise TTCError("TTC-5004", "实时语音连接失败", 503) from exc


async def hangup_call(call_id: str) -> None:
    if not re.fullmatch(r"rtc_[A-Za-z0-9_-]{1,120}", call_id):
        raise ValueError("Invalid provider call ID")
    settings = get_settings()
    if not settings.realtime_api_key:
        raise TTCError("TTC-5004", "实时语音服务尚未配置", 503)
    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.post(
            f"https://api.openai.com/v1/realtime/calls/{call_id}/hangup",
            headers={"Authorization": f"Bearer {settings.realtime_api_key}"})
        if response.status_code != 404:
            response.raise_for_status()


async def enqueue_hangup(session, tenant_id, session_id, call_id):
    await session.execute(text(
        "INSERT INTO task (id, tenant_id, type, resource_type, resource_id, payload) "
        "VALUES (:id, :tenant, 'realtime_hangup', 'voice_session', :session, "
        "CAST(:payload AS jsonb)) ON CONFLICT DO NOTHING"
    ), {"id": uuid7(), "tenant": tenant_id, "session": session_id,
        "payload": json.dumps({"call_id": call_id})})
