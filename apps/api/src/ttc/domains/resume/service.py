import io
import json
import re
from collections import defaultdict

from docx import Document
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.adapters.llm import LLMAdapter
from ttc.adapters.storage import Storage
from ttc.core.config import get_settings
from ttc.core.errors import TTCError
from ttc.core.security import uuid7

CLAIM_TYPES = {"education", "work", "project", "publication", "patent", "award",
               "skill", "contact", "summary"}


def extract_text(data: bytes, mime: str) -> tuple[str, list[str]]:
    try:
        if mime == "application/pdf":
            if not data.startswith(b"%PDF-"):
                raise TTCError("TTC-3004", "文件内容与扩展名不符", 422)
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise TTCError("TTC-3003", "不支持加密 PDF", 422)
            pages = [page.extract_text() or "" for page in reader.pages]
        elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            if not data.startswith(b"PK\x03\x04"):
                raise TTCError("TTC-3004", "文件内容与扩展名不符", 422)
            document = Document(io.BytesIO(data))
            pages = ["\n".join(paragraph.text for paragraph in document.paragraphs)]
        else:
            pages = [data.decode("utf-8-sig")]
    except TTCError:
        raise
    except Exception as exc:
        raise TTCError("TTC-3003", "文件损坏或无法提取文本", 422) from exc
    value = "\n".join(pages).strip()
    if not value:
        raise TTCError("TTC-3003", "文件没有可解析的文字；扫描件需先 OCR", 422)
    return value, pages


async def parse_resume(session: AsyncSession, resume_id, *, llm=None, storage=None) -> int:
    resume = (await session.execute(
        text("SELECT r.id, r.file_uri, r.mime, r.candidate_id, c.tenant_id FROM resume r "
             "JOIN candidate c ON c.id = r.candidate_id WHERE r.id = :id"),
        {"id": resume_id},
    )).mappings().one()
    storage = storage or Storage()
    data = await storage.get(resume["file_uri"])
    resume_text, pages = extract_text(data, resume["mime"])
    model = get_settings().llm_model or "unconfigured"
    version_no = (await session.execute(
        text("SELECT COALESCE(MAX(version_no), 0) + 1 FROM resume_version "
             "WHERE resume_id = :id"), {"id": resume_id},
    )).scalar_one()
    llm = llm or LLMAdapter()
    claims = await llm.extract_claims(resume_text)
    if not isinstance(claims, list):
        raise TTCError("TTC-5002", "模型解析字段无效", 502)
    text_uri = await storage.put(
        f"text/{resume['tenant_id']}/{resume['candidate_id']}/{resume_id}/{version_no}.txt",
        resume_text.encode(), "text/plain; charset=utf-8",
    )
    version_id = uuid7()
    await session.execute(
        text("INSERT INTO resume_version (id, resume_id, version_no, extractor_model, "
             "prompt_version, text_uri, status, parsed_at) VALUES "
             "(:id, :resume, :no, :model, 'v1', :uri, 'done', now())"),
        {"id": version_id, "resume": resume_id, "no": version_no,
         "model": model, "uri": text_uri},
    )
    counts = defaultdict(int)
    page_boundaries = []
    cursor = 0
    for page in pages:
        cursor += len(page) + 1
        page_boundaries.append(cursor)
    for claim in claims[:200]:
        if not isinstance(claim, dict) or claim.get("type") not in CLAIM_TYPES:
            continue
        raw = claim.get("raw_text")
        normalized = claim.get("normalized")
        if not isinstance(raw, str) or not raw or not isinstance(normalized, dict):
            continue
        normalized = dict(normalized)
        invalid_fields = []
        for field in ("org", "school", "company", "department"):
            name = normalized.get(field)
            if isinstance(name, str) and not re.search(
                r"(?<![\u3400-\u9fffA-Za-z0-9])" + re.escape(name) +
                r"(?![\u3400-\u9fffA-Za-z0-9])", raw, re.IGNORECASE,
            ):
                normalized.pop(field)
                invalid_fields.append(field)
        if invalid_fields:
            normalized["unverified_fields"] = invalid_fields
        offset = resume_text.find(raw)
        if offset < 0:
            continue
        try:
            confidence = float(claim.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        if not 0 <= confidence <= 1:
            continue
        claim_type = claim["type"]
        counts[claim_type] += 1
        page_no = 1 + sum(boundary <= offset for boundary in page_boundaries[:-1])
        await session.execute(
            text("INSERT INTO resume_claim (id, resume_version_id, claim_type, ordinal, "
                 "raw_text, normalized, page_no, char_start, char_end, confidence, needs_review) "
                 "VALUES (:id, :version, CAST(:type AS claim_type), :ordinal, :raw, "
                 "CAST(:normalized AS jsonb), :page, :start, :end, :confidence, :review)"),
            {"id": uuid7(), "version": version_id, "type": claim_type,
             "ordinal": counts[claim_type], "raw": raw,
             "normalized": json.dumps(normalized, ensure_ascii=False),
             "page": page_no, "start": offset, "end": offset + len(raw),
             "confidence": confidence, "review": confidence < 0.8 or bool(invalid_fields)},
        )
    await session.execute(
        text("UPDATE resume SET parse_status = 'done', page_count = :pages WHERE id = :id"),
        {"pages": len(pages), "id": resume_id},
    )
    return sum(counts.values())
