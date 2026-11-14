import asyncio
import json

import httpx

from ttc.adapters.llm import LLMAdapter
from ttc.core.config import get_settings
from ttc.domains.interview.conduct import (
    has_live_candidate_violation,
    interviewer_announces_conduct_termination,
    normalize_conduct,
)


def turns():
    return [
        {"id": "i1", "role": "interviewer", "text": "请介绍你的项目。"},
        {"id": "c1", "role": "candidate", "text": "我负责订单服务的库存扣减链路。"},
        {"id": "c2", "role": "candidate", "text": "异常时我们会回滚并记录审计日志。"},
    ]


def test_conduct_score_is_weighted_from_dimensions():
    result = normalize_conduct(
        {
            "summary": "整体表达克制，配合流程。",
            "dimensions": [
                {
                    "key": "respect",
                    "score": 90,
                    "reason": "全程保持尊重。",
                    "evidence_turn_ids": ["c1"],
                },
                {"key": "order", "score": 80, "reason": "按问题作答。"},
                {"key": "integrity", "score": 100, "reason": "回答具体。"},
                {"key": "professionalism", "score": 70, "reason": "表达可理解。"},
            ],
            "incidents": [],
            "veto": False,
        },
        turns(),
    )

    assert result["status"] == "assessed"
    assert result["score"] == 86.5
    assert result["veto"] is False
    assert result["dimensions"][0]["evidence_turn_ids"] == ["c1"]


def test_severe_incident_requires_candidate_evidence_and_forces_veto():
    result = normalize_conduct(
        {
            "summary": "候选人辱骂面试官。",
            "dimensions": [
                {"key": "respect", "score": 90, "reason": "不应被采纳。"},
            ],
            "incidents": [
                {
                    "category": "hostility",
                    "severity": "severe",
                    "description": "候选人辱骂面试官。",
                    "evidence_turn_ids": ["c2"],
                }
            ],
            "veto": False,
        },
        turns(),
    )

    assert result["status"] == "vetoed"
    assert result["score"] == 0
    assert result["veto"] is True
    assert result["review_required"] is True
    assert result["incidents"][0]["quotes"] == [
        {"turn_id": "c2", "text": "异常时我们会回滚并记录审计日志。"}
    ]
    assert "候选人辱骂面试官。" in result["veto_reasons"][0]


def test_unlocatable_or_interviewer_evidence_cannot_trigger_veto():
    result = normalize_conduct(
        {
            "summary": "模型声称有严重问题。",
            "incidents": [
                {
                    "category": "hostility",
                    "severity": "severe",
                    "description": "无依据的严重指控。",
                    "evidence_turn_ids": ["i1"],
                }
            ],
            "veto": True,
        },
        turns(),
    )

    assert result["status"] == "unassessed"
    assert result["veto"] is False
    assert result["incidents"] == []
    assert any("没有提供可定位" in item for item in result["limitations"])


def test_moderate_incident_caps_score_and_requires_review():
    result = normalize_conduct(
        {
            "dimensions": [
                {"key": "respect", "score": 100, "reason": "偶有不当。"},
                {"key": "order", "score": 100, "reason": "基本配合。"},
                {"key": "integrity", "score": 100, "reason": "作答完整。"},
                {"key": "professionalism", "score": 100, "reason": "表达清楚。"},
            ],
            "incidents": [
                {
                    "category": "disruption",
                    "severity": "moderate",
                    "description": "打断面试官。",
                    "evidence_turn_ids": ["c1"],
                }
            ],
            "veto": False,
        },
        turns(),
    )

    assert result["status"] == "assessed"
    assert result["score"] == 59.0
    assert result["review_required"] is True
    assert result["veto"] is False


def test_unambiguous_abuse_is_vetoed_even_when_model_is_unavailable():
    abusive_turns = [
        {"id": "c1", "role": "candidate", "text": "你算什么东西，滚出去，傻逼。"},
    ]
    result = normalize_conduct({}, abusive_turns, "模型超时")

    assert result["status"] == "vetoed"
    assert result["score"] == 0
    assert result["incidents"][0]["source"] == "rule"
    assert result["incidents"][0]["quotes"][0]["turn_id"] == "c1"
    assert result["incidents"][0]["quotes"][0]["text"] == abusive_turns[0]["text"]


def test_short_or_unknown_answers_are_not_rule_flagged():
    short_turns = [
        {"id": "c1", "role": "candidate", "text": "不知道。"},
        {"id": "c2", "role": "candidate", "text": "这里我没听清，可以重复吗？"},
    ]
    result = normalize_conduct({}, short_turns, "模型不可用")

    assert result["status"] == "unassessed"
    assert result["score"] is None
    assert result["veto"] is False
    assert result["incidents"] == []


def test_live_termination_signal_requires_explicit_abuse_or_warning():
    assert has_live_candidate_violation("我操你妈。") is True
    assert has_live_candidate_violation("我不知道，可以再说一次吗？") is False
    assert interviewer_announces_conduct_termination(
        "你刚才的言语非常不当，我会如实记录。这次沟通到此结束。"
    ) is True
    assert interviewer_announces_conduct_termination(
        "好的，那我们回到刚才的问题。"
    ) is False
    assert interviewer_announces_conduct_termination("这次沟通到此结束。") is False


def test_no_candidate_turns_is_unassessed():
    result = normalize_conduct({}, turns()[:1])

    assert result["status"] == "unassessed"
    assert result["review_required"] is True
    assert result["score"] is None
    assert result["veto"] is False


def test_conduct_model_prompt_requires_exact_turn_evidence(monkeypatch):
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
                                    "summary": "已审核。",
                                    "dimensions": [],
                                    "incidents": [],
                                    "veto": False,
                                    "veto_reasons": [],
                                    "review_required": False,
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

    asyncio.run(LLMAdapter().assess_interview_conduct(turns()))
    system_prompt = seen["body"]["messages"][0]["content"]
    payload = seen["body"]["messages"][1]["content"]
    assert "故意扰乱面试秩序" in system_prompt
    assert "evidence_turn_ids" in system_prompt
    assert "不得编造引语" in system_prompt
    assert "[turn:c1] 候选人" in payload
