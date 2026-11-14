from datetime import UTC, datetime

from ttc.domains.interview.markdown_report import render_interview_markdown


def sample_report() -> dict:
    return {
        "id": "report-1",
        "summary": {
            "turn_count": 4,
            "overview": "候选人说明了故障排查过程，但项目结果证据不足。",
            "qa": [
                {
                    "question": "如何定位线上性能问题？",
                    "answer_summary": "候选人先查看监控，再分段排查数据库与接口。",
                }
            ],
            "limitations": ["转写由浏览器上报。"],
        },
        "quotes": [
            {
                "turn_id": "turn-candidate-1",
                "text": "我先看监控，再排查慢查询。<script>alert(1)</script>",
            }
        ],
        "crosscheck": {"inconsistent": ["项目时间与简历不一致"]},
        "followups": ["请确认项目上线时间和本人负责范围。"],
        "model_version": "summary-v1",
        "conduct": {
            "status": "assessed",
            "score": 86,
            "veto": False,
            "review_required": False,
            "summary": "未发现严重言行事件。",
            "incidents": [],
            "limitations": ["仅审核转写。"],
        },
        "conduct_model_version": "conduct-v1",
        "capability": {
            "status": "assessed",
            "score": 50,
            "review_required": False,
            "summary": "具备问题分析证据，但岗位知识不足。",
            "dimensions": [
                {
                    "key": "job_knowledge",
                    "label": "岗位知识与技能",
                    "weight_pct": 20,
                    "score": 40,
                    "reason": "数据库知识回答不完整。",
                    "evidence_turn_ids": ["turn-candidate-1"],
                },
                {
                    "key": "problem_solving",
                    "label": "分析与问题解决",
                    "weight_pct": 20,
                    "score": 82,
                    "reason": "能够说明分段排查步骤。",
                    "evidence_turn_ids": ["turn-candidate-1"],
                },
            ],
            "evidence_coverage": {"cited_turns": 1, "candidate_turns": 2, "ratio": 0.5},
            "strengths": ["问题拆解步骤清楚"],
            "gaps": ["缺少结果指标"],
            "verification_questions": ["请说明故障恢复后的量化结果。"],
            "limitations": ["未进行技能测试。"],
        },
        "capability_model_version": "capability-v1",
    }


def test_markdown_report_contains_required_sections_and_evidence() -> None:
    markdown, digest = render_interview_markdown(
        session={
            "id": "session-1",
            "status": "ended",
            "end_reason": "completed",
            "started_at": datetime(2026, 11, 15, 1, 0, tzinfo=UTC),
            "ended_at": datetime(2026, 11, 15, 1, 18, tzinfo=UTC),
        },
        candidate={"id": "candidate-1", "display_name": "合成候选人"},
        job={"id": "job-1", "title": "后端工程师"},
        plan={
            "questions": [
                {
                    "text": "如何定位线上性能问题？",
                    "focus": "问题定位",
                }
            ]
        },
        report=sample_report(),
        turns=[
            {"role": "interviewer", "text": "如何定位线上性能问题？"},
            {"role": "candidate", "text": "先查监控，再排查慢查询。"},
        ],
        generated_at=datetime(2026, 11, 15, 2, 0, tzinfo=UTC),
    )

    assert len(digest) == 64
    for heading in (
        "## 1. 报告信息",
        "## 2. 执行摘要",
        "## 3. 综合表现与能力图谱",
        "## 4. 面试问答概括",
        "## 5. 亮点、重点与疑点",
        "## 6. 待确认事项",
        "## 7. HR 进一步调查与提问方向",
        "## 8. 参考结论与其他岗位建议",
        "## 9. 证据与报告边界",
        "## 10. 后续行动清单",
    ):
        assert heading in markdown
    assert "**[亮点]** 问题拆解步骤清楚" in markdown
    assert "**[疑点]** 与已有材料存在不一致：项目时间与简历不一致" in markdown
    assert "`turn-candidate-1`" in markdown
    assert "暂不建议进入当前岗位下一轮" in markdown
    assert "问题解决证据较强" in markdown
    assert "<script>" not in markdown
    assert "&lt;script&gt;" in markdown


def test_markdown_report_falls_back_to_persisted_turns() -> None:
    report = sample_report()
    report["summary"]["qa"] = []
    markdown, _ = render_interview_markdown(
        session={"id": "session-2", "status": "ended", "end_reason": "completed"},
        candidate={"id": "candidate-2", "display_name": "候选人二"},
        job={"id": "job-2", "title": "平台工程师"},
        plan={},
        report=report,
        turns=[
            {"role": "interviewer", "text": "请介绍一次故障处理。"},
            {"role": "candidate", "text": "我负责定位根因并回滚版本。"},
        ],
    )

    assert "### Q1 请介绍一次故障处理。" in markdown
    assert "我负责定位根因并回滚版本。" in markdown
