import asyncio
import json

import httpx

from ttc.adapters.llm import LLMAdapter
from ttc.core.config import get_settings
from ttc.core.errors import TTCError
from ttc.domains.interview import plan as plan_module
from ttc.domains.interview.plan import (
    FALLBACK_PLAN,
    build_plan,
    normalize_plan,
    plan_from_db,
    session_instructions,
)


def test_normalize_plan_keeps_valid_questions():
    plan = normalize_plan(
        {
            "profile": "三年后端，主要做订单系统，用 Go 与 MySQL。",
            "questions": [
                {
                    "section": "experience",
                    "text": "你在订单系统里具体负责哪一部分？",
                    "focus": "个人贡献",
                    "job_relevance": "后端架构",
                    "resume_anchor": "订单系统",
                },
                {"section": "nonsense", "text": "为什么选择我们团队？", "focus": "动机"},
                {"section": "skill", "text": "你如何设计缓存一致性？", "focus": "技术深度"},
            ],
        }
    )
    assert plan is not None
    assert [item["text"] for item in plan["questions"]] == [
        "你在订单系统里具体负责哪一部分？",
        "为什么选择我们团队？",
        "你如何设计缓存一致性？",
    ]
    assert plan["questions"][0]["id"] == "q1"
    assert plan["questions"][1]["section"] == "experience"  # 非法 section 归一
    assert plan["questions"][0]["job_relevance"] == "后端架构"
    assert plan["profile"].startswith("三年后端")
    assert plan["sections_order"] == ["intro", "experience", "skill", "wrap"]
    assert plan["strategy"] == plan_module.STRATEGY


def test_normalize_plan_rejects_empty_questions():
    assert normalize_plan({}) is None
    assert normalize_plan({"questions": [{"text": "   "}]}) is None
    assert normalize_plan({"questions": "not-a-list"}) is None
    assert (
        normalize_plan({"questions": [{"text": "第一道问题足够长"}, {"text": "第二道问题足够长"}]})
        is None
    )


def test_session_instructions_carry_profile_and_focus():
    text = session_instructions(
        {
            "profile": "两年数据开发，做过实时数仓。",
            "questions": [
                {
                    "id": "q1",
                    "section": "experience",
                    "text": "实时数仓那条链路你做了哪一段？",
                    "focus": "职责边界",
                }
            ],
        }
    )
    assert "两年数据开发" in text
    assert "实时数仓那条链路你做了哪一段？" in text
    assert "关注：职责边界" in text
    assert "初始问题只用于确定对话主题" in text
    assert "动态推进规则" in text
    assert "敏感信息" in text


def test_session_instructions_include_job_context_and_followup_budget():
    text = session_instructions(
        {
            "profile": "三年后端，做过订单系统。",
            "questions": [
                {
                    "id": "q1",
                    "section": "experience",
                    "text": "订单服务中你负责哪一部分？",
                    "focus": "职责边界",
                    "job_relevance": "高并发后端服务",
                    "resume_anchor": "订单服务",
                }
            ],
            "job_context": {
                "title": "高级后端工程师",
                "jd_text": "负责高并发订单服务与稳定性建设。",
                "required_skills": ["Go", "PostgreSQL"],
                "preferred_skills": ["Kubernetes"],
                "responsibilities": ["服务架构设计", "稳定性建设"],
            },
        },
        job_title="高级后端工程师",
    )
    assert "岗位必备技能：Go、PostgreSQL" in text
    assert "岗位核心职责：服务架构设计；稳定性建设" in text
    assert "岗位原文快照" in text
    assert "岗位关联：高并发后端服务" in text
    assert f"最多追问 {plan_module.MAX_FOLLOWUPS_PER_TOPIC} 层" in text
    assert f"合计不超过 {plan_module.MAX_TOTAL_QUESTIONS} 个" in text


def test_session_instructions_rejects_bad_plan_input():
    text = session_instructions("not-a-dict")  # type: ignore[arg-type]
    assert FALLBACK_PLAN["questions"][0]["text"] in text


def test_session_instructions_carry_job_title():
    """语音系统指令必须显式带上应聘岗位名，且放在长文本之前。"""
    text = session_instructions(
        {
            "profile": "两年 Java 后端，做过订单服务。",
            "questions": [
                {
                    "id": "q1",
                    "section": "experience",
                    "text": "你做的订单服务用了哪些技术？",
                    "focus": "技术栈",
                }
            ],
        },
        job_title="Java 后端工程师",
    )
    assert "应聘岗位：Java 后端工程师" in text
    assert text.index("应聘岗位：") < text.index("候选人简历要点")


def test_session_instructions_omit_blank_job_title():
    """岗位名缺失（job 删除/标题为空）时整行不注入，也不报错。"""
    for missing in (None, "", "   "):
        text = session_instructions(
            {
                "questions": [
                    {
                        "id": "q1",
                        "section": "experience",
                        "text": "请介绍一段项目经历。",
                        "focus": "经历",
                    }
                ],
            },
            job_title=missing,
        )
        assert "应聘岗位：" not in text


def test_session_instructions_fallback_keeps_job_title():
    """回退固定清单时岗位名不能丢。"""
    text = session_instructions({"questions": []}, job_title="测试开发工程师")
    assert FALLBACK_PLAN["questions"][0]["text"] in text
    assert "应聘岗位：测试开发工程师" in text


def test_build_interview_plan_calls_model(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_key", "synthetic-test-key")
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "synthetic-model")
    seen = {}

    def handle(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "profile": "合成画像",
                                    "questions": [
                                        {"section": "skill", "text": "你的 Redis 缓存怎么做的？"}
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handle)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "ttc.adapters.llm.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    data = asyncio.run(
        LLMAdapter().build_interview_plan(
            "简历正文",
            "岗位描述",
            "screen",
            job_context={"required_skills": ["Python"]},
        )
    )
    assert data["questions"][0]["text"] == "你的 Redis 缓存怎么做的？"
    payload = seen["body"]["messages"][1]["content"]
    assert "简历正文" in payload and "岗位描述" in payload
    assert '"required_skills": ["Python"]' in payload
    system_prompt = seen["body"]["messages"][0]["content"]
    assert "3～5 道初始问题" in system_prompt
    assert "不需要预生成追问" in system_prompt


def test_build_plan_falls_back_when_model_fails(monkeypatch):
    async def fake_resume(session, candidate_id):
        return "合成简历正文"

    async def fake_context(session, job_id):
        return {"title": "后端工程师", "jd_text": "合成岗位描述"}

    async def boom(self, resume_text, jd_text, scenario="screen", job_context=None):
        raise TTCError("TTC-5004", "面试问题生成模型不可用", 503)

    monkeypatch.setattr(plan_module, "latest_resume_text", fake_resume)
    monkeypatch.setattr(plan_module, "current_job_context", fake_context)
    monkeypatch.setattr(LLMAdapter, "build_interview_plan", boom)

    plan = asyncio.run(build_plan(None, None, None))  # type: ignore[arg-type]
    assert plan["source"] == "fallback"
    assert plan["job_context"]["title"] == "后端工程师"
    assert [item["text"] for item in plan["questions"]] == [
        item["text"] for item in FALLBACK_PLAN["questions"]
    ]


def test_build_plan_without_resume_text_skips_model(monkeypatch):
    async def empty_resume(session, candidate_id):
        return ""

    async def fake_context(session, job_id):
        return {"title": "数据工程师", "jd_text": "合成岗位描述"}

    called = {"value": False}

    async def should_not_run(self, *args, **kwargs):
        called["value"] = True
        raise AssertionError("没有简历文本时不应该调用模型")

    monkeypatch.setattr(plan_module, "latest_resume_text", empty_resume)
    monkeypatch.setattr(plan_module, "current_job_context", fake_context)
    monkeypatch.setattr(LLMAdapter, "build_interview_plan", should_not_run)

    plan = asyncio.run(build_plan(None, None, None))  # type: ignore[arg-type]
    assert plan["source"] == "fallback"
    assert plan["job_context"]["title"] == "数据工程师"
    assert called["value"] is False


def test_build_plan_keeps_initial_questions_and_job_snapshot(monkeypatch):
    async def fake_resume(session, candidate_id):
        return "合成简历正文"

    async def fake_context(session, job_id):
        return {
            "job_version_id": "version-1",
            "title": "Python 后端工程师",
            "jd_text": "负责订单服务开发。",
            "required_skills": ["Python", "PostgreSQL"],
            "responsibilities": ["订单服务开发"],
        }

    async def fake_model(self, resume_text, jd_text, scenario="screen", job_context=None):
        return {
            "profile": "三年 Python 后端。",
            "questions": [
                {
                    "section": "experience",
                    "text": "你在订单服务中负责什么？",
                    "focus": "个人贡献",
                    "job_relevance": "后端开发",
                    "resume_anchor": "订单服务",
                },
                {
                    "section": "skill",
                    "text": "你如何定位数据库慢查询？",
                    "focus": "问题排查",
                    "job_relevance": "PostgreSQL",
                    "resume_anchor": "数据库优化",
                },
                {"section": "motivation", "text": "你为什么考虑这个岗位？", "focus": "求职动机"},
            ],
        }

    monkeypatch.setattr(plan_module, "latest_resume_text", fake_resume)
    monkeypatch.setattr(plan_module, "current_job_context", fake_context)
    monkeypatch.setattr(LLMAdapter, "build_interview_plan", fake_model)

    plan = asyncio.run(build_plan(None, None, None))  # type: ignore[arg-type]
    assert plan["source"] == "llm"
    assert len(plan["questions"]) == 3
    assert plan["job_context"]["job_version_id"] == "version-1"
    assert plan["questions"][0]["job_relevance"] == "后端开发"


def test_normalize_plan_caps_question_count():
    plan = normalize_plan({"questions": [{"text": f"第{i}个问题足够长"} for i in range(12)]})
    assert plan is not None
    assert len(plan["questions"]) == plan_module.MAX_QUESTIONS


def test_plan_from_db_parses_jsonb_string():
    """asyncpg 把 jsonb 读成字符串；不解析会让实时层静默退回固定清单。"""
    stored = json.dumps(
        {
            "questions": [
                {
                    "id": "q1",
                    "section": "skill",
                    "text": "你在订单系统里负责哪一块？",
                    "focus": "职责",
                }
            ]
        },
        ensure_ascii=False,
    )
    plan = plan_from_db(stored)
    assert plan["questions"][0]["text"] == "你在订单系统里负责哪一块？"
    assert "你在订单系统里负责哪一块？" in session_instructions(plan)


def test_plan_from_db_falls_back_on_garbage():
    assert plan_from_db("{not json") is FALLBACK_PLAN
    assert plan_from_db(None) is FALLBACK_PLAN
    assert plan_from_db({"questions": []}) is FALLBACK_PLAN


def test_summarize_interview_includes_job_title(monkeypatch):
    """纪要模型也要看到应聘岗位名（HR 端按岗位核对）。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_key", "synthetic-test-key")
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "synthetic-model")
    seen = {}

    def handle(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "overview": "合成纪要",
                                    "qa": [],
                                    "followups": [],
                                    "limitations": [],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handle)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "ttc.adapters.llm.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    asyncio.run(LLMAdapter().summarize_interview({"questions": []}, [], "Java 后端工程师"))
    payload = seen["body"]["messages"][1]["content"]
    assert "应聘岗位：Java 后端工程师" in payload


def test_summarize_interview_omits_blank_job_title(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_key", "synthetic-test-key")
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "synthetic-model")
    seen = {}

    def handle(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "overview": "合成纪要",
                                    "qa": [],
                                    "followups": [],
                                    "limitations": [],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handle)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "ttc.adapters.llm.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    asyncio.run(LLMAdapter().summarize_interview({"questions": []}, [], "   "))
    payload = seen["body"]["messages"][1]["content"]
    assert "应聘岗位：" not in payload
