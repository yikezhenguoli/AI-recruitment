#!/usr/bin/env python
"""DeepSeek connectivity and AI pipeline smoke test.

Usage (from apps/api):
    ..\\..\\.venv\\Scripts\\python.exe scripts\\test_deepseek.py
    ..\\..\\.venv\\Scripts\\python.exe scripts\\test_deepseek.py --full

Exit codes:
    0  success
    1  test failure
    2  DEEPSEEK_API_KEY is not configured

This script never prints or writes the API key. The --full mode uses a clearly
labelled synthetic JD/resume sample only to exercise the real LLM calls; it does
not write results into the application session store.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from langchain_core.messages import HumanMessage, SystemMessage

from agents.jd_agent import parse_job_description
from agents.llm_client import _build_llm, build_chain, invoke_with_retry
from core.config import get_settings
from models.schemas import DimensionEvaluation

SAMPLE_JD = """
Synthetic smoke-test job description (not a real vacancy).

Role: AI Backend Engineer
Location: Beijing
Seniority: Mid-level

Responsibilities:
- Build FastAPI services for AI-powered recruitment workflows.
- Integrate LLM providers through OpenAI-compatible APIs.
- Design structured JSON extraction and evaluation pipelines.

Required skills:
- Python
- FastAPI
- LangChain
- REST APIs
- JSON schema design

Preferred skills:
- LangGraph
- PostgreSQL
- Docker

Education:
- Bachelor's degree in Computer Science or a related field.
""".strip()

SAMPLE_RESUME = {
    "personal_info": {
        "first_name": "Smoke",
        "last_name": "Test",
        "email": None,
        "phone": None,
        "location": "Beijing",
    },
    "skills": ["Python", "FastAPI", "LangChain", "REST APIs", "JSON"],
    "education": [
        {
            "institution": "Synthetic Test University",
            "degree": "Bachelor of Science",
            "field": "Computer Science",
            "score_gpa": None,
            "start_date": "2018-09",
            "end_date": "2022-06",
        }
    ],
    "work_experience": [
        {
            "organization": "Synthetic Test Company",
            "role": "Backend Engineer",
            "start_date": "2022-07",
            "end_date": "Present",
            "responsibilities": [
                "Built FastAPI services and LLM integration pipelines."
            ],
        }
    ],
    "projects": [
        {
            "name": "Synthetic recruitment API",
            "description": "A test project used only for this smoke test.",
            "technologies": ["Python", "FastAPI", "LangChain"],
        }
    ],
    "publications": [],
    "certifications": [],
    "additional_info": {
        "note": "Synthetic smoke-test sample; not a real candidate."
    },
}


def _redact(text: str, secret: str) -> str:
    if secret and secret in text:
        return text.replace(secret, "***")
    return text


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


async def check_connectivity() -> dict[str, Any]:
    """Call the same ChatOpenAI client used by the application."""
    llm = _build_llm()
    messages = [
        SystemMessage(
            content=(
                "You are a connectivity test. Return ONLY a valid JSON object. "
                "Do not use markdown or prose."
            )
        ),
        HumanMessage(
            content='Return exactly this JSON: {"status": "ok", "provider": "deepseek"}'
        ),
    ]
    response = await llm.ainvoke(messages)
    content = _content_to_text(response.content).strip()
    if not content:
        raise RuntimeError("DeepSeek returned an empty response")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"DeepSeek returned non-JSON content: {content[:300]!r}"
        ) from exc

    print(f"[OK] JSON output: {json.dumps(data, ensure_ascii=False)}")
    return data


async def check_pipeline() -> None:
    """Exercise real JD parsing, schema generation and evaluation model calls."""
    # A unique suffix avoids the JD/schema disk cache, so --full always makes
    # fresh model calls instead of replaying a previous smoke-test result.
    unique_jd = f"{SAMPLE_JD}\n\nSmoke test run: {datetime.now(timezone.utc).isoformat()}"
    jd_id, structured, schema = await parse_job_description(unique_jd)
    total_points = sum(dim.max_points for dim in schema.dimensions)
    print(
        "[OK] JD parsed: "
        f"role_title={structured.role_title!r}, jd_id={jd_id[:12]}..."
    )
    print(
        f"[OK] Scoring schema: {len(schema.dimensions)} dimensions, "
        f"total max_points={total_points}"
    )

    eval_chain = build_chain("evaluation", DimensionEvaluation)
    raw = await invoke_with_retry(
        eval_chain,
        {
            "jd_json": json.dumps(structured.model_dump(), ensure_ascii=False),
            "resume_json": json.dumps(SAMPLE_RESUME, ensure_ascii=False),
            "scoring_schema_json": json.dumps(schema.model_dump(), ensure_ascii=False),
        },
    )
    evaluation = DimensionEvaluation(**raw)
    print(f"[OK] Evaluation returned {len(evaluation.scores)} dimension scores")
    for score in evaluation.scores:
        print(f"     - {score.name}: {score.score} ({score.reason[:80]})")


async def main_async(full: bool) -> int:
    settings = get_settings()
    print(
        "[INFO] provider=deepseek "
        f"base_url={settings.DEEPSEEK_BASE_URL} "
        f"model={settings.DEEPSEEK_MODEL} "
        f"timeout={settings.LLM_TIMEOUT_SECONDS}s"
    )

    if not settings.deepseek_configured:
        print(
            "[FAIL] DEEPSEEK_API_KEY is not configured. "
            "Set it in apps/api/.env and retry."
        )
        return 2

    try:
        await check_connectivity()
        if full:
            await check_pipeline()
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        message = _redact(str(exc), settings.DEEPSEEK_API_KEY)
        print(f"[FAIL] {type(exc).__name__}: {message}")
        return 1

    print("[PASS] DeepSeek smoke test completed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test DeepSeek connectivity and the AI AFS LLM pipeline."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also test JD parsing, scoring schema generation and evaluation.",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args.full))


if __name__ == "__main__":
    raise SystemExit(main())
