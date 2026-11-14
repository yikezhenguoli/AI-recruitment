import asyncio
import json

import httpx
import pytest

from ttc.adapters.llm import LLMAdapter
from ttc.core.config import get_settings
from ttc.core.errors import TTCError
from ttc.domains.interview import plan as plan_module
from ttc.domains.interview.plan import (FALLBACK_PLAN, build_plan, normalize_plan,
                                        plan_from_db, session_instructions)


def test_normalize_plan_keeps_valid_questions():
    plan = normalize_plan({
        "profile": "三年后端，主要做订单系统，用 Go 与 MySQL。",
        "questions": [
            {"section": "experience", "text": "你在订单系统里具体负责哪一部分？", "focus": "个人贡献"},
            {"section": "nonsense", "text": "为什么选择我们团队？"},
            {"section": "skill", "text": ""},
        ],
    })
    assert plan is not None
    assert [item["text"] for item in plan["questions"]] == [
        "你在订单系统里具体负责哪一部分？", "为什么选择我们团队？"]
    assert plan["questions"][0]["id"] == "q1"
    assert plan["questions"][1]["section"] == "experience"  # 非法 section 归一
    assert plan["profile"].startswith("三年后端")
    assert plan["sections_order"] == ["intro", "experience", "wrap"]


def test_normalize_plan_rejects_empty_questions():
    assert normalize_plan({}) is None
    assert normalize_plan({"questions": [{"text": "   "}]}) is None
    assert normalize_plan({"questions": "not-a-list"}) is None


def test_session_instructions_carry_profile_and_focus():
    text = session_instructions({
        "profile": "两年数据开发，做过实时数仓。",
        "questions": [{"id": "q1", "section": "experience",
                       "text": "实时数仓那条链路你做了哪一段？", "focus": "职责边界"}],
    })
    assert "两年数据开发" in text
    assert "实时数仓那条链路你做了哪一段？" in text
    assert "关注：职责边界" in text
    assert "敏感信息" in text


def test_session_instructions_rejects_bad_plan_input():
    text = session_instructions("not-a-dict")  # type: ignore[arg-type]
    assert FALLBACK_PLAN["questions"][0]["text"] in text


def test_build_interview_plan_calls_model(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_key", "synthetic-test-key")
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "synthetic-model")
    seen = {}

    def handle(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "profile": "合成画像",
            "questions": [{"section": "skill", "text": "你的 Redis 缓存怎么做的？"}],
        }, ensure_ascii=False)}}]})

    transport = httpx.MockTransport(handle)
    original_client = httpx.AsyncClient
    monkeypatch.setattr("ttc.adapters.llm.httpx.AsyncClient",
                        lambda **kwargs: original_client(transport=transport, **kwargs))

    data = asyncio.run(LLMAdapter().build_interview_plan("简历正文", "岗位描述", "screen"))
    assert data["questions"][0]["text"] == "你的 Redis 缓存怎么做的？"
    payload = seen["body"]["messages"][1]["content"]
    assert "简历正文" in payload and "岗位描述" in payload


def test_build_plan_falls_back_when_model_fails(monkeypatch):
    async def fake_resume(session, candidate_id):
        return "合成简历正文"

    async def fake_jd(session, job_id):
        return "合成岗位描述"

    async def boom(self, resume_text, jd_text, scenario="screen"):
        raise TTCError("TTC-5004", "面试问题生成模型不可用", 503)

    monkeypatch.setattr(plan_module, "latest_resume_text", fake_resume)
    monkeypatch.setattr(plan_module, "current_jd", fake_jd)
    monkeypatch.setattr(LLMAdapter, "build_interview_plan", boom)

    plan = asyncio.run(build_plan(None, None, None))  # type: ignore[arg-type]
    assert plan["source"] == "fallback"
    assert [item["text"] for item in plan["questions"]] == [
        item["text"] for item in FALLBACK_PLAN["questions"]]


def test_build_plan_without_resume_text_skips_model(monkeypatch):
    async def empty_resume(session, candidate_id):
        return ""

    called = {"value": False}

    async def should_not_run(self, *args, **kwargs):
        called["value"] = True
        raise AssertionError("没有简历文本时不应该调用模型")

    monkeypatch.setattr(plan_module, "latest_resume_text", empty_resume)
    monkeypatch.setattr(LLMAdapter, "build_interview_plan", should_not_run)

    plan = asyncio.run(build_plan(None, None, None))  # type: ignore[arg-type]
    assert plan["source"] == "fallback"
    assert called["value"] is False


def test_normalize_plan_caps_question_count():
    plan = normalize_plan({"questions": [{"text": f"第{i}个问题足够长"} for i in range(12)]})
    assert plan is not None
    assert len(plan["questions"]) == plan_module.MAX_QUESTIONS


def test_plan_from_db_parses_jsonb_string():
    """asyncpg 把 jsonb 读成字符串；不解析会让实时层静默退回固定清单。"""
    stored = json.dumps({"questions": [{"id": "q1", "section": "skill",
                                        "text": "你在订单系统里负责哪一块？", "focus": "职责"}]},
                        ensure_ascii=False)
    plan = plan_from_db(stored)
    assert plan["questions"][0]["text"] == "你在订单系统里负责哪一块？"
    assert "你在订单系统里负责哪一块？" in session_instructions(plan)


def test_plan_from_db_falls_back_on_garbage():
    assert plan_from_db("{not json") is FALLBACK_PLAN
    assert plan_from_db(None) is FALLBACK_PLAN
    assert plan_from_db({"questions": []}) is FALLBACK_PLAN
