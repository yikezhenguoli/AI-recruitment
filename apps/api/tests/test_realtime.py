import asyncio

import httpx
import pytest

from ttc.adapters.realtime import create_call, hangup_call
from ttc.core.config import get_settings
from ttc.core.errors import TTCError


def test_realtime_connect_and_hangup(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "realtime_api_key", "synthetic-test-key")
    monkeypatch.setattr(settings, "realtime_model", "synthetic-model")
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path == "/v1/realtime/calls":
            assert request.method == "POST"
            assert b"v=0" in request.content
            assert b"synthetic-model" in request.content
            return httpx.Response(201, content=b"v=0\r\nanswer", headers={
                "Location": "/v1/realtime/calls/rtc_synthetic"})
        assert request.url.path == "/v1/realtime/calls/rtc_synthetic/hangup"
        return httpx.Response(404)

    transport = httpx.MockTransport(handle)
    original_client = httpx.AsyncClient

    def mocked_client(*args, **kwargs):
        return original_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr("ttc.adapters.realtime.httpx.AsyncClient", mocked_client)

    async def verify():
        answer, call_id = await create_call(b"v=0\r\noffer", "合成测试问题")
        assert answer == b"v=0\r\nanswer"
        assert call_id == "rtc_synthetic"
        await hangup_call(call_id)

    asyncio.run(verify())
    assert len(requests) == 2


def test_realtime_rejects_missing_call_id(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "realtime_api_key", "synthetic-test-key")
    monkeypatch.setattr(settings, "realtime_model", "synthetic-model")
    transport = httpx.MockTransport(lambda request: httpx.Response(201, content=b"v=0"))
    original_client = httpx.AsyncClient
    monkeypatch.setattr("ttc.adapters.realtime.httpx.AsyncClient", lambda **kwargs: original_client(
        transport=transport, **kwargs))

    with pytest.raises(TTCError):
        asyncio.run(create_call(b"v=0\r\noffer", "合成测试问题"))
