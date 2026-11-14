import asyncio
import json
from uuid import uuid4

from ttc.api.v1.voice import (
    LiveInterviewRoom,
    live_turn_inputs,
    response_text,
)


class FakeUpstream:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


def run(coro):
    return asyncio.run(coro)


def test_room_starts_with_exact_initial_and_switches_after_followup_budget():
    room = LiveInterviewRoom(uuid4())
    room.configure_plan({
        "questions": [
            {"id": "q1", "text": "请介绍一个订单系统项目。"},
            {"id": "q2", "text": "你如何定位线上性能问题？"},
        ]
    })
    room.upstream = FakeUpstream()

    run(room.start_interview())
    opening = room.upstream.sent[-1]
    assert opening["type"] == "response.create"
    assert "请介绍一个订单系统项目。" in opening["response"]["instructions"]
    assert "如果没有任何有必要的下一问" in opening["response"]["instructions"]

    room.question_ledger.commit_response("请介绍一个订单系统项目。")
    room.question_ledger.commit_response("这个项目中你亲自负责哪一部分？")
    room.question_ledger.commit_response("刚才那部分最终产生了什么可验证结果？")
    run(room.continue_interview())
    next_instruction = room.upstream.sent[-1]["response"]["instructions"]
    assert "你如何定位线上性能问题？" in next_instruction


def test_room_requests_summary_when_no_question_remains():
    room = LiveInterviewRoom(uuid4())
    room.configure_plan({
        "questions": [
            {"id": "q1", "text": "请介绍一个订单系统项目。"},
        ]
    })
    room.upstream = FakeUpstream()
    room.question_ledger.commit_response("请介绍一个订单系统项目。")
    room.question_ledger.commit_response("这个项目中你亲自负责哪一部分？")
    room.question_ledger.commit_response("刚才那部分最终产生了什么可验证结果？")

    run(room.continue_interview())
    payload = room.upstream.sent[-1]
    assert room.response_purpose == "final"
    assert room.final_after_response is True
    assert "不要提出任何问题" in payload["response"]["instructions"]


def test_approved_question_is_committed_once_and_does_not_end_call():
    room = LiveInterviewRoom(uuid4())
    room.configure_plan({
        "questions": [
            {"id": "q1", "text": "请介绍一个订单系统项目。"},
        ]
    })
    room.upstream = FakeUpstream()
    room.prepare_directed_question(
        "请介绍一个订单系统项目。",
        initial_id="q1",
        kind="initial",
    )
    room.response_purpose = "question"

    result = run(room.resolve_completed_response(""))

    assert result is None
    assert room.awaiting_candidate_answer is True
    assert room.question_ledger.questions == ["请介绍一个订单系统项目。"]
    assert room.question_ledger.asked_initial_ids == {"q1"}


def test_empty_transcript_does_not_end_call():
    room = LiveInterviewRoom(uuid4())
    room.configure_plan({
        "questions": [
            {"id": "q1", "text": "请介绍一个订单系统项目。"},
        ]
    })
    room.upstream = FakeUpstream()
    run(room.start_interview())

    result = run(room.resolve_completed_response(""))

    assert result is None
    assert room.opening_attempts == 1
    assert room.question_ledger.questions == ["请介绍一个订单系统项目。"]
    assert room.awaiting_candidate_answer is True


def test_only_explicit_final_summary_completes_call():
    room = LiveInterviewRoom(uuid4())
    room.configure_plan({
        "questions": [
            {"id": "q1", "text": "请介绍一个订单系统项目。"},
        ]
    })
    room.upstream = FakeUpstream()
    room.question_ledger.commit_response("请介绍一个订单系统项目。")
    room.response_purpose = "final"
    room.final_after_response = True

    result = run(room.resolve_completed_response(""))

    assert result == "ai_completed"


def test_response_text_supports_new_and_legacy_event_shapes():
    assert response_text({"transcript": "旧版文本。"}) == "旧版文本。"
    assert response_text({"text": "新版文本。"}) == "新版文本。"
    assert response_text({
        "response": {
            "output": [{
                "content": [{
                    "type": "audio_transcript",
                    "transcript": "输出数组中的文本。",
                }]
            }]
        }
    }) == "输出数组中的文本。"


def test_live_turns_become_persisted_turn_inputs():
    turns = live_turn_inputs([
        {"role": "interviewer", "text": "请介绍一个项目。"},
        {"role": "candidate", "text": "我负责订单服务。"},
        {"role": "system", "text": "忽略系统消息"},
        {"role": "candidate", "text": "   "},
    ])

    assert [(turn.index, turn.role, turn.text) for turn in turns] == [
        (0, "interviewer", "请介绍一个项目。"),
        (1, "candidate", "我负责订单服务。"),
    ]
