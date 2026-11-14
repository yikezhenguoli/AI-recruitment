import asyncio
import base64
import io
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.websockets import WebSocketDisconnect

from ttc.core.config import get_settings
from ttc.core.security import hash_password, uuid7
from ttc.domains.interview.capability import normalize_capability
from ttc.domains.interview.conduct import normalize_conduct
from ttc.main import app
from ttc.tasks.runner import run_once


class FakeLLM:
    async def extract_claims(self, resume_text):
        return [{"type": "education", "raw_text": "清华", "normalized": {"org": "清华大学"},
                 "confidence": .9},
                {"type": "skill", "raw_text": "Python", "normalized": {"name": "Python"},
                 "confidence": .95},
                {"type": "work", "raw_text": "后端开发", "normalized": {"role": "后端开发"},
                 "confidence": .8},
                {"type": "work", "raw_text": "从未出现的经历",
                 "normalized": {"org": "不存在"}, "confidence": .8}]


def test_synthetic_resume_assessment_and_tenant_access(monkeypatch):
    settings = get_settings()
    if not settings.database_url or not settings.demo_mode:
        pytest.skip("Requires migrated development PostgreSQL and DEMO_MODE")
    slug = f"test-{uuid4().hex}"
    password = "synthetic-test-password-123"

    async def seed():
        engine = create_async_engine(settings.database_url)
        try:
            async with engine.begin() as connection:
                tenant_id, second_id, admin_id, candidate_user = (
                    uuid7(), uuid7(), uuid7(), uuid7())
                for tenant, tenant_slug in ((tenant_id, slug), (second_id, slug + "-other")):
                    await connection.execute(text(
                        "INSERT INTO tenant (id, slug, name, is_demo) "
                        "VALUES (:id, :slug, :name, true)"
                    ), {"id": tenant, "slug": tenant_slug, "name": "合成测试租户"})
                for user, tenant in ((admin_id, tenant_id), (uuid7(), second_id)):
                    await connection.execute(text(
                        "INSERT INTO app_user (id, tenant_id, email, display_name, "
                        "password_hash, role) VALUES (:id, :tenant, 'test@example.invalid', "
                        "'合成管理员', :hash, 'admin')"
                    ), {"id": user, "tenant": tenant, "hash": hash_password(password)})
                await connection.execute(text(
                    "INSERT INTO app_user (id, tenant_id, email, display_name, "
                    "password_hash, role) VALUES (:id, :tenant, 'candidate@example.invalid', "
                    "'合成候选人', :hash, 'candidate')"
                ), {"id": candidate_user, "tenant": tenant_id,
                    "hash": hash_password(password)})
            return tenant_id, second_id, candidate_user
        finally:
            await engine.dispose()

    tenant_id, second_id, candidate_user = asyncio.run(seed())
    resume_id = None
    try:
        with TestClient(app) as client:
            def login(tenant_slug):
                response = client.post("/api/v1/auth/login", json={
                    "tenant_slug": tenant_slug, "email": "test@example.invalid",
                    "password": password})
                assert response.status_code == 200, response.text
                return {"Authorization": "Bearer " + response.json()["access_token"]}

            headers, other = login(slug), login(slug + "-other")
            job = client.post("/api/v1/jobs", headers=headers, json={
                "title": "后端工程师",
                "jd_text": "负责后端服务开发，熟悉 Python 与 PostgreSQL，重视安全和工程质量。"})
            assert job.status_code == 201, job.text
            assert client.get("/api/v1/jobs", headers=headers).status_code == 200
            candidate = client.post("/api/v1/candidates", headers=headers,
                                    json={"display_name": "合成候选人"})
            assert candidate.status_code == 201, candidate.text
            assert client.get("/api/v1/candidates", headers=headers).status_code == 200
            candidate_id = candidate.json()["id"]
            async def link():
                engine = create_async_engine(settings.database_url)
                try:
                    async with engine.begin() as connection:
                        await connection.execute(text(
                            "UPDATE candidate SET user_id = :user WHERE id = :candidate"
                        ), {"user": candidate_user, "candidate": candidate_id})
                finally:
                    await engine.dispose()
            asyncio.run(link())
            assert client.get(f"/api/v1/candidates/{candidate_id}",
                              headers=other).status_code == 404
            response = client.post("/api/v1/resumes", headers=headers, data={
                "candidate_id": candidate_id, "job_id": job.json()["id"]},
                files={"file": ("synthetic.txt", io.BytesIO("清华 Python 后端开发".encode()),
                                "text/plain")})
            assert response.status_code == 202, response.text
            resume_id = response.json()["resume_id"]
            assert client.get(f"/api/v1/resumes/{resume_id}", headers=other).status_code == 404
            listed = client.get(f"/api/v1/candidates/{candidate_id}/resumes",
                                headers=headers)
            assert listed.status_code == 200, listed.text
            assert listed.json()["items"][0]["id"] == resume_id
            assert client.get(f"/api/v1/candidates/{candidate_id}/resumes",
                              headers=other).status_code == 404
            with client.websocket_connect(
                f"/api/v1/ws/progress/{response.json()['task_id']}"
            ) as socket:
                socket.send_json({"token": headers["Authorization"].split()[1]})
                assert socket.receive_json()["stage"] == "queued"
        from ttc.core.db import dispose_engine
        async def process():
            try:
                assert await run_once(llm=FakeLLM()) is True
            finally:
                await dispose_engine()
        asyncio.run(process())
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer " + client.post(
                "/api/v1/auth/login", json={"tenant_slug": slug,
                                             "email": "test@example.invalid",
                                             "password": password}
            ).json()["access_token"]}
            parsed = client.get(f"/api/v1/resumes/{resume_id}/claims", headers=headers)
            assert parsed.status_code == 200, parsed.text
            assert len(parsed.json()["claims"]) == 3
            assert parsed.json()["claims"][0]["raw_text"] == "清华"
            assert parsed.json()["claims"][0]["normalized"].get("org") is None
            assert parsed.json()["claims"][0]["needs_review"] is True
            report = client.post(f"/api/v1/candidates/{candidate_id}/assessments",
                                 headers=headers, json={"job_id": job.json()["id"]})
            assert report.status_code == 201, report.text
            assert "match_ledger" in report.json()["report"]
            candidate_headers = {"Authorization": "Bearer " + client.post(
                "/api/v1/auth/login", json={"tenant_slug": slug,
                                             "email": "candidate@example.invalid",
                                             "password": password}
            ).json()["access_token"]}

            async def quick_capability(turns, _plan, _job_title):
                return normalize_capability(
                    {}, [dict(turn) for turn in turns]
                ), "synthetic-capability"

            monkeypatch.setattr("ttc.api.v1.voice.assess_capability", quick_capability)
            assert client.post("/api/v1/voice-sessions", headers=headers, json={
                "candidate_id": candidate_id, "job_id": job.json()["id"]}).status_code == 403
            consent = client.post("/api/v1/consents", headers=candidate_headers, json={
                "candidate_id": candidate_id, "purpose": "voice_interview",
                "text_version": "synthetic-v1", "acknowledged": True})
            assert consent.status_code == 201, consent.text
            too_many_questions = client.post("/api/v1/voice-sessions", headers=headers, json={
                "candidate_id": candidate_id, "job_id": job.json()["id"],
                "custom_questions": [f"问题{i}" for i in range(6)]})
            assert too_many_questions.status_code == 422, too_many_questions.text
            voice = client.post("/api/v1/voice-sessions", headers=headers, json={
                "candidate_id": candidate_id, "job_id": job.json()["id"],
                "custom_questions": ["请说明你如何定位线上性能问题？"]})
            assert voice.status_code == 201, voice.text
            assert voice.json()["plan"]["questions"][0]["source"] == "hr"
            assert voice.json()["plan"]["questions"][0]["text"] == (
                "请说明你如何定位线上性能问题？"
            )
            voice_id = voice.json()["id"]
            assert client.post("/api/v1/realtime/mint", headers=candidate_headers,
                               json={"session_id": voice_id}).status_code == 503
            finished = client.post(f"/api/v1/voice-sessions/{voice_id}/finish",
                                   headers=candidate_headers, json={"turns": [
                                       {"index": 0, "role": "candidate", "text": "合成回答"}]})
            assert finished.status_code == 202, finished.text
            assert client.get(f"/api/v1/voice-sessions/{voice_id}/report",
                              headers=candidate_headers).status_code == 403
            call_report = client.get(f"/api/v1/voice-sessions/{voice_id}/report",
                                     headers=headers).json()
            assert call_report["quotes"][0]["text"] == "合成回答"
            assert call_report["conduct"]["status"] in ("assessed", "unassessed", "vetoed")
            assert (
                call_report["conduct_score"] is None
                or 0 <= call_report["conduct_score"] <= 100
            )
            assert call_report["conduct_veto"] is False
            assert call_report["capability"]["status"] in ("assessed", "unassessed")
            assert (
                call_report["capability_score"] is None
                or 0 <= call_report["capability_score"] <= 100
            )
            call_index = 0

            async def synthetic_call(offer, instructions):
                nonlocal call_index
                call_index += 1
                assert offer.startswith(b"v=0")
                assert "招聘" in instructions
                assert "应聘岗位：后端工程师" in instructions
                return b"v=0\r\nsynthetic-answer", f"rtc_synthetic_test_{call_index}"

            monkeypatch.setattr("ttc.api.v1.voice.create_call", synthetic_call)
            monkeypatch.setattr(settings, "realtime_model", "synthetic-model")
            live_voice = client.post("/api/v1/voice-sessions", headers=headers, json={
                "candidate_id": candidate_id, "job_id": job.json()["id"]})
            assert live_voice.status_code == 201, live_voice.text
            live_id = live_voice.json()["id"]
            invalid = client.post(f"/api/v1/voice-sessions/{live_id}/connect",
                                  headers={**candidate_headers,
                                           "Content-Type": "application/sdp"},
                                  content=b"invalid")
            assert invalid.status_code == 422, invalid.text
            oversized = client.post(f"/api/v1/voice-sessions/{live_id}/connect",
                                    headers={**candidate_headers,
                                             "Content-Type": "application/sdp"},
                                    content=b"v=0" + b"a" * 65536)
            assert oversized.status_code == 413, oversized.text
            connected = client.post(f"/api/v1/voice-sessions/{live_id}/connect",
                                    headers={**candidate_headers,
                                             "Content-Type": "application/sdp"},
                                    content=b"v=0\r\nsynthetic-offer-for-test-only")
            assert connected.status_code == 200, connected.text
            assert connected.content == b"v=0\r\nsynthetic-answer"
            assert client.post(f"/api/v1/voice-sessions/{live_id}/connect",
                               headers={**candidate_headers,
                                        "Content-Type": "application/sdp"},
                               content=b"v=0\r\nsynthetic-offer-for-test-only").status_code == 409
            revoked = client.post(f"/api/v1/consents/{consent.json()['id']}/revoke",
                                  headers=candidate_headers)
            assert revoked.status_code == 200, revoked.text
            state = client.get(f"/api/v1/voice-sessions/{live_id}", headers=headers)
            assert state.json()["status"] == "revoked"
            assert client.post(f"/api/v1/voice-sessions/{live_id}/turns",
                               headers=candidate_headers, json=[]).status_code == 403
            renewed = client.post("/api/v1/consents", headers=candidate_headers, json={
                "candidate_id": candidate_id, "purpose": "voice_interview",
                "text_version": "synthetic-v2", "acknowledged": True})
            assert renewed.status_code == 201, renewed.text
            next_voice = client.post("/api/v1/voice-sessions", headers=headers, json={
                "candidate_id": candidate_id, "job_id": job.json()["id"]})
            assert next_voice.status_code == 201, next_voice.text
            live_id = next_voice.json()["id"]
            connected = client.post(f"/api/v1/voice-sessions/{live_id}/connect",
                                    headers={**candidate_headers,
                                             "Content-Type": "application/sdp"},
                                    content=b"v=0\r\nsynthetic-offer-for-test-only")
            assert connected.status_code == 200, connected.text

            policy_voice = client.post("/api/v1/voice-sessions", headers=headers, json={
                "candidate_id": candidate_id, "job_id": job.json()["id"]})
            assert policy_voice.status_code == 201, policy_voice.text
            policy_id = policy_voice.json()["id"]

            class FakeQwen:
                def __init__(self):
                    self.events = [
                        json.dumps({
                            "type": "conversation.item.input_audio_transcription.completed",
                            "item_id": "candidate-1",
                            "transcript": "我操你妈。",
                        }, ensure_ascii=False),
                        json.dumps({
                            "type": "response.audio_transcript.delta",
                            "response_id": "warning-1",
                            "delta": "你刚才的言语非常不当，我会如实记录。"
                                     "这次沟通到此结束。",
                        }, ensure_ascii=False),
                        json.dumps({
                            "type": "response.done",
                            "response_id": "warning-1",
                        }),
                    ]

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    if not self.events:
                        await asyncio.sleep(1)
                        raise StopAsyncIteration
                    return self.events.pop(0)

                async def send(self, _message):
                    return None

                async def close(self):
                    return None

            async def fake_qwen_session(_instructions, _voice=None):
                return (
                    FakeQwen(),
                    "synthetic-qwen",
                    "Tina",
                    [json.dumps({"type": "session.created"})],
                )

            async def quick_summary(_session, _session_id, turns):
                return (
                    {"status": "assessed", "turn_count": len(turns),
                     "overview": "合成言行终止测试", "qa": [], "limitations": []},
                    [],
                    "synthetic-summary",
                )

            async def quick_conduct(turns):
                return normalize_conduct({}, [dict(turn) for turn in turns]), "synthetic-conduct"

            monkeypatch.setattr("ttc.api.v1.voice.qwen.open_session", fake_qwen_session)
            monkeypatch.setattr("ttc.api.v1.voice.summarize_turns", quick_summary)
            monkeypatch.setattr("ttc.api.v1.voice.assess_turns", quick_conduct)
            with client.websocket_connect(
                f"/api/v1/voice-sessions/{policy_id}/realtime"
            ) as socket:
                socket.send_json({"token": candidate_headers["Authorization"].split()[1]})
                message_types = []
                for _ in range(10):
                    payload = socket.receive_json()
                    message_types.append(payload["type"])
                    if payload["type"] == "session.terminated":
                        assert payload["reason"] == "conduct_violation"
                        break
                assert "session.terminated" in message_types

            policy_state = client.get(f"/api/v1/voice-sessions/{policy_id}",
                                      headers=headers).json()
            assert policy_state["status"] == "ended"
            assert policy_state["end_reason"] == "conduct_violation"
            policy_turns = client.get(f"/api/v1/voice-sessions/{policy_id}/turns",
                                      headers=headers).json()["items"]
            assert any(turn["role"] == "candidate" and "操你妈" in turn["text"]
                       for turn in policy_turns)

            async def verify_policy_report_task():
                engine = create_async_engine(settings.database_url)
                try:
                    async with engine.connect() as connection:
                        return await connection.scalar(text(
                            "SELECT count(*) FROM task WHERE type = 'voice_report' "
                            "AND resource_type = 'voice_session' AND resource_id = :id"
                        ), {"id": policy_id})
                finally:
                    await engine.dispose()

            assert asyncio.run(verify_policy_report_task()) == 1

            observer_voice = client.post("/api/v1/voice-sessions", headers=headers, json={
                "candidate_id": candidate_id, "job_id": job.json()["id"]})
            assert observer_voice.status_code == 201, observer_voice.text
            observer_id = observer_voice.json()["id"]

            class ObserverUpstream:
                def __init__(self):
                    self.sent = []
                    self.events = []

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    while not self.events:
                        await asyncio.sleep(0.02)
                    return self.events.pop(0)

                async def send(self, message):
                    self.sent.append(message)

                async def close(self):
                    return None

            observer_holder = {}

            async def fake_observer_session(_instructions, _voice=None):
                upstream = ObserverUpstream()
                observer_holder["upstream"] = upstream
                return (
                    upstream,
                    "synthetic-observer",
                    "Tina",
                    [json.dumps({"type": "session.created"})],
                )

            monkeypatch.setattr("ttc.api.v1.voice.qwen.open_session", fake_observer_session)
            token = candidate_headers["Authorization"].split()[1]
            audio = base64.b64encode(b"\x10\x40" * 320).decode()
            with client.websocket_connect(
                f"/api/v1/voice-sessions/{observer_id}/realtime"
            ) as candidate_socket:
                candidate_socket.send_json({"token": token})
                assert candidate_socket.receive_json()["type"] == "session.created"
                assert candidate_socket.receive_json()["type"] == "relay.ready"
                with pytest.raises(WebSocketDisconnect) as denied:
                    with client.websocket_connect(
                        f"/api/v1/voice-sessions/{observer_id}/realtime"
                    ) as hr_realtime:
                        hr_realtime.send_json(
                            {"token": headers["Authorization"].split()[1]}
                        )
                        hr_realtime.receive_json()
                assert denied.value.code == 4403
                with client.websocket_connect(
                    f"/api/v1/voice-sessions/{observer_id}/observe"
                ) as hr_socket:
                    hr_socket.send_json(
                        {"token": headers["Authorization"].split()[1]}
                    )
                    initial_types = {
                        hr_socket.receive_json()["type"],
                        hr_socket.receive_json()["type"],
                    }
                    assert "relay.ready" in initial_types
                    assert "control.state" in initial_types

                    paused = client.post(
                        f"/api/v1/voice-sessions/{observer_id}/flow-control",
                        headers=headers,
                        json={"action": "pause"},
                    )
                    assert paused.status_code == 200, paused.text
                    assert paused.json()["interview_paused"] is True
                    assert any(
                        "面试流程被HR暂停" in json.dumps(message, ensure_ascii=False)
                        for message in observer_holder["upstream"].sent
                    )

                    resumed = client.post(
                        f"/api/v1/voice-sessions/{observer_id}/flow-control",
                        headers=headers,
                        json={"action": "resume"},
                    )
                    assert resumed.status_code == 200, resumed.text
                    assert resumed.json()["interview_paused"] is False
                    assert any(
                        "面试流程已恢复" in json.dumps(message, ensure_ascii=False)
                        for message in observer_holder["upstream"].sent
                    )

                    candidate_socket.send_json({
                        "type": "input_audio_buffer.append",
                        "audio": audio,
                    })
                    candidate_event = hr_socket.receive_json()
                    while candidate_event["type"] != "participant.audio":
                        candidate_event = hr_socket.receive_json()
                    assert candidate_event["role"] == "candidate"
                    assert candidate_event["sample_rate"] == 16000

                    hr_socket.send_json({"type": "control.take"})
                    control_event = hr_socket.receive_json()
                    while control_event["type"] != "control.state":
                        control_event = hr_socket.receive_json()
                    assert control_event["hr_control"] is True

                    hr_socket.send_json({
                        "type": "hr_audio.append",
                        "audio": audio,
                    })
                    candidate_event = candidate_socket.receive_json()
                    while candidate_event["type"] != "participant.audio":
                        candidate_event = candidate_socket.receive_json()
                    assert candidate_event["role"] == "hr"
                    assert candidate_event["sample_rate"] == 16000

                    observer_holder["upstream"].events.append(json.dumps({
                        "type": "conversation.item.input_audio_transcription.completed",
                        "item_id": "hr-turn-1",
                        "transcript": "请具体说明你处理线上故障的步骤。",
                    }, ensure_ascii=False))
                    transcript_event = hr_socket.receive_json()
                    while transcript_event["type"] != (
                        "conversation.item.input_audio_transcription.completed"
                    ):
                        transcript_event = hr_socket.receive_json()
                    assert transcript_event["speaker"] == "hr"

                    hr_socket.send_json({"type": "control.release"})

            assert client.delete(f"/api/v1/resumes/{resume_id}", headers=headers).status_code == 200
            request = client.post("/api/v1/privacy/requests", headers=candidate_headers,
                                  json={"candidate_id": candidate_id,
                                        "request_type": "delete", "reason": "合成测试"})
            assert request.status_code == 202, request.text
            request_id = request.json()["id"]
            processed = client.post(f"/api/v1/admin/privacy/requests/{request_id}/process",
                                    headers=headers)
            assert processed.status_code == 200, processed.text
            async def verify_hangup_task():
                engine = create_async_engine(settings.database_url)
                try:
                    async with engine.connect() as connection:
                        return await connection.scalar(text(
                            "SELECT count(*) FROM task WHERE type = 'realtime_hangup' "
                            "AND resource_id = :id AND payload->>'call_id' = :call"
                        ), {"id": live_id, "call": "rtc_synthetic_test_2"})
                finally:
                    await engine.dispose()
            assert asyncio.run(verify_hangup_task()) == 1
            assert client.get(f"/api/v1/privacy/requests/{request_id}",
                              headers=candidate_headers).status_code == 401
            assert client.get(f"/api/v1/privacy/requests/{request_id}",
                              headers=headers).json()["status"] == "completed"
    finally:
        async def cleanup():
            engine = create_async_engine(settings.database_url)
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(
                        "DELETE FROM task WHERE tenant_id IN (:a, :b)"
                    ), {"a": tenant_id, "b": second_id})
                    await connection.execute(text(
                        "DELETE FROM privacy_request WHERE tenant_id IN (:a, :b)"
                    ), {"a": tenant_id, "b": second_id})
                    await connection.execute(text(
                        "DELETE FROM job WHERE tenant_id IN (:a, :b)"
                    ), {"a": tenant_id, "b": second_id})
                    await connection.execute(text("DELETE FROM tenant WHERE id IN (:a, :b)"),
                                             {"a": tenant_id, "b": second_id})
            finally:
                await engine.dispose()
        asyncio.run(cleanup())
