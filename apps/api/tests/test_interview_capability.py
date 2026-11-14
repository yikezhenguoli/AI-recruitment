import asyncio
import json

import httpx

from ttc.adapters.llm import LLMAdapter
from ttc.core.config import get_settings
from ttc.domains.interview.capability import normalize_capability


def turns():
    return [
        {"id": "i1", "role": "interviewer", "text": "请介绍订单服务项目。"},
        {
            "id": "c1",
            "role": "candidate",
            "text": "我负责库存扣减接口，用 Redis 分布式锁解决并发超卖。",
        },
        {
            "id": "c2",
            "role": "candidate",
            "text": "压测 QPS 从 800 提升到 2400，异常时回滚并记录审计日志。",
        },
    ]


def test_capability_score_is_weighted_from_evidenced_dimensions():
    result = normalize_capability(
        {
            "summary": "候选人展示了订单并发处理的项目证据。",
            "dimensions": [
                {"key": "job_knowledge", "score": 80, "reason": "理解并发扣减。",
                 "evidence_turn_ids": ["c1"]},
                {"key": "relevant_experience", "score": 90, "reason": "有具体项目。",
                 "evidence_turn_ids": ["c1", "c2"]},
                {"key": "problem_solving", "score": 85, "reason": "说明锁与超卖问题。",
                 "evidence_turn_ids": ["c1"]},
                {"key": "ownership_impact", "score": 75, "reason": "有一手结果。",
                 "evidence_turn_ids": ["c2"]},
                {"key": "learning_adaptability", "score": None, "reason": "未提问。",
                 "evidence_turn_ids": []},
            ],
            "strengths": ["并发问题描述具体"],
            "gaps": ["缺少故障复盘"],
            "verification_questions": ["锁失效时如何处理？"],
            "review_required": False,
            "limitations": [],
        },
        turns(),
    )

    assert result["status"] == "assessed"
    assert result["score"] == 82.94
    assert result["review_required"] is False
    assert result["evidence_coverage"] == {
        "cited_turns": 2,
        "candidate_turns": 2,
        "ratio": 1.0,
    }
    assert result["dimensions"][0]["evidence_turn_ids"] == ["c1"]


def test_capability_dimension_without_candidate_evidence_is_null():
    result = normalize_capability(
        {
            "dimensions": [
                {"key": "job_knowledge", "score": 95, "reason": "模型臆测。",
                 "evidence_turn_ids": ["i1"]},
                {"key": "relevant_experience", "score": 90, "reason": "模型臆测。",
                 "evidence_turn_ids": []},
            ]
        },
        turns(),
    )

    assert result["status"] == "unassessed"
    assert result["score"] is None
    assert all(item["score"] is None for item in result["dimensions"])
    assert result["review_required"] is True


def test_capability_requires_reliable_weight_and_review_coverage():
    result = normalize_capability(
        {
            "dimensions": [
                {"key": "job_knowledge", "score": 100, "reason": "单点回答。",
                 "evidence_turn_ids": ["c1"]},
            ],
            "review_required": False,
        },
        turns(),
    )

    assert result["status"] == "unassessed"
    assert result["score"] is None
    assert result["review_required"] is True


def test_capability_without_candidate_answers_is_unassessed():
    result = normalize_capability({}, turns()[:1])

    assert result["status"] == "unassessed"
    assert result["score"] is None
    assert result["review_required"] is True


def test_capability_prompt_requires_answer_evidence(monkeypatch):
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
                "choices": [{
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "已评估。",
                                "dimensions": [],
                                "strengths": [],
                                "gaps": [],
                                "verification_questions": [],
                                "review_required": True,
                                "limitations": [],
                            },
                            ensure_ascii=False,
                        )
                    }
                }]
            },
        )

    transport = httpx.MockTransport(handle)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "ttc.adapters.llm.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    asyncio.run(
        LLMAdapter().assess_interview_capability(
            {
                "questions": [{"text": "请介绍订单服务项目。"}],
                "job_context": {"required_skills": ["Redis", "Python"]},
            },
            turns(),
            "后端工程师",
        )
    )
    system_prompt = seen["body"]["messages"][0]["content"]
    payload = seen["body"]["messages"][1]["content"]
    assert "只评价回答中明确出现的内容" in system_prompt
    assert "evidence_turn_ids" in system_prompt
    assert "[turn:c1] 候选人" in payload
    assert "Redis" in payload
