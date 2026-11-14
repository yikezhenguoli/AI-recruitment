import hashlib
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.adapters.storage import Storage
from ttc.api.deps import Principal, require_roles
from ttc.api.v1.candidates import require_candidate
from ttc.api.v1.consents import require_consent
from ttc.api.v1.jobs import require_job
from ttc.core.audit import record_audit
from ttc.core.db import get_session
from ttc.core.errors import TTCError
from ttc.core.security import uuid7
from ttc.domains.resume.service import validate_document
from ttc.domains.resume.timeline import build_timeline

router = APIRouter(tags=["resumes"])
hr = require_roles("hr", "admin")
MIMES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
MAX_FILE = 20 * 1024 * 1024


async def require_resume(session: AsyncSession, user: Principal, resume_id: UUID):
    row = (await session.execute(
        text("SELECT r.id, r.candidate_id, r.file_name, r.mime, r.size_bytes, "
             "r.file_uri, r.parse_status, r.page_count, r.created_at "
             "FROM resume r JOIN candidate c ON c.id = r.candidate_id "
             "WHERE r.id = :id AND c.tenant_id = :tenant"),
        {"id": resume_id, "tenant": user.tenant_id},
    )).mappings().one_or_none()
    if row is None:
        raise TTCError("TTC-2001", "简历不存在", 404)
    return dict(row)


@router.post("/resumes", status_code=202)
async def upload_resume(candidate_id: UUID = Form(), job_id: UUID | None = Form(default=None),
                        file: UploadFile = File(), user: Principal = Depends(hr),
                        session: AsyncSession = Depends(get_session)):
    candidate = await require_candidate(session, user, candidate_id)
    if not candidate["is_synthetic"]:
        await require_consent(session, candidate_id, "resume_process")
    if job_id:
        job = await require_job(session, user, job_id)
        if job["status"] == "archived":
            raise TTCError("TTC-2002", "岗位已归档", 409)
    name = Path(file.filename or "").name
    mime = MIMES.get(Path(name).suffix.lower())
    if not mime:
        raise TTCError("TTC-3001", "仅支持 PDF、DOCX、TXT 与 PNG/JPEG/WebP 图片", 415)
    if file.content_type != mime:
        raise TTCError("TTC-3004", "声明的 MIME 与扩展名不一致", 422)
    data = await file.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise TTCError("TTC-3002", "简历超过 20 MB", 413)
    validate_document(data, mime)
    digest = hashlib.sha256(data).digest()
    existing = (await session.execute(
        text("SELECT id, parse_status FROM resume WHERE candidate_id = :candidate "
             "AND file_hash = :hash"),
        {"candidate": candidate_id, "hash": digest},
    )).mappings().one_or_none()
    if existing:
        return {"resume_id": existing["id"], "parse_status": existing["parse_status"],
                "duplicate": True}
    storage = Storage()
    resume_id, task_id = uuid7(), uuid7()
    uri = await storage.put(f"{user.tenant_id}/{candidate_id}/{resume_id}/{name}", data, mime)
    try:
        await session.execute(
            text("INSERT INTO resume (id, candidate_id, file_name, mime, size_bytes, "
                 "file_hash, file_uri) VALUES (:id, :candidate, :name, :mime, :size, :hash, :uri)"),
            {"id": resume_id, "candidate": candidate_id, "name": name, "mime": mime,
             "size": len(data), "hash": digest, "uri": uri},
        )
        await session.execute(
            text("INSERT INTO task (id, tenant_id, type, resource_type, resource_id) "
                 "VALUES (:id, :tenant, 'resume_parse', 'resume', :resume)"),
            {"id": task_id, "tenant": user.tenant_id, "resume": resume_id},
        )
        await record_audit(session, user, "resume.upload", "resume", resume_id)
        await session.commit()
    except Exception:
        await session.rollback()
        await storage.delete(uri)
        raise
    return {"resume_id": resume_id, "task_id": task_id, "parse_status": "queued",
            "checks": {"mime_ok": True, "size_ok": True,
                       "hash": f"sha256:{digest.hex()}"}}


@router.get("/resumes/{resume_id}")
async def get_resume(resume_id: UUID, user: Principal = Depends(hr),
                     session: AsyncSession = Depends(get_session)):
    row = await require_resume(session, user, resume_id)
    row.pop("file_uri")
    return row


@router.get("/resumes/{resume_id}/claims")
async def claims(resume_id: UUID, user: Principal = Depends(hr),
                 session: AsyncSession = Depends(get_session)):
    await require_resume(session, user, resume_id)
    version = (await session.execute(
        text("SELECT id, version_no, status, error FROM resume_version "
             "WHERE resume_id = :id ORDER BY version_no DESC LIMIT 1"),
        {"id": resume_id},
    )).mappings().one_or_none()
    if version is None:
        return {"resume_id": resume_id, "version": None, "claims": []}
    rows = (await session.execute(
        text("SELECT id, claim_type AS type, ordinal, raw_text, normalized, page_no, "
             "char_start, char_end, confidence, needs_review FROM resume_claim "
             "WHERE resume_version_id = :version ORDER BY claim_type, ordinal"),
        {"version": version["id"]},
    )).mappings().all()
    return {"resume_id": resume_id, "version": version["version_no"],
            "status": version["status"], "claims": [dict(row) for row in rows]}


@router.get("/resumes/{resume_id}/text")
async def resume_text(resume_id: UUID, user: Principal = Depends(hr),
                      session: AsyncSession = Depends(get_session)):
    """返回最近一版的纯文本（扫描件即 OCR 转写结果），供 HR 对照原件核对。"""
    await require_resume(session, user, resume_id)
    version = (await session.execute(
        text("SELECT version_no, extractor_model, text_uri FROM resume_version "
             "WHERE resume_id = :id ORDER BY version_no DESC LIMIT 1"),
        {"id": resume_id},
    )).mappings().one_or_none()
    if version is None or not version["text_uri"]:
        raise TTCError("TTC-2001", "还没有可查看的转写文本", 404)
    data = await Storage().get(version["text_uri"])
    return {"version": version["version_no"],
            "extractor_model": version["extractor_model"],
            "text": data.decode("utf-8", errors="replace")}


@router.get("/resumes/{resume_id}/timeline")
async def timeline(resume_id: UUID, user: Principal = Depends(hr),
                   session: AsyncSession = Depends(get_session)):
    result = await claims(resume_id, user, session)
    return build_timeline(result["claims"])


@router.post("/resumes/{resume_id}/reparse", status_code=202)
async def reparse(resume_id: UUID, user: Principal = Depends(hr),
                  session: AsyncSession = Depends(get_session)):
    await require_resume(session, user, resume_id)
    active = (await session.execute(
        text("SELECT id FROM task WHERE type = 'resume_parse' AND resource_id = :id "
             "AND status IN ('queued', 'running')"), {"id": resume_id},
    )).scalar_one_or_none()
    if active:
        return {"task_id": active, "parse_status": "queued"}
    task_id = uuid7()
    await session.execute(
        text("INSERT INTO task (id, tenant_id, type, resource_type, resource_id) "
             "VALUES (:id, :tenant, 'resume_parse', 'resume', :resume)"),
        {"id": task_id, "tenant": user.tenant_id, "resume": resume_id},
    )
    await session.execute(
        text("UPDATE resume SET parse_status = 'queued' WHERE id = :id"), {"id": resume_id},
    )
    await record_audit(session, user, "resume.reparse", "resume", resume_id)
    await session.commit()
    return {"task_id": task_id, "parse_status": "queued"}


@router.delete("/resumes/{resume_id}")
async def delete_resume(resume_id: UUID, user: Principal = Depends(hr),
                        session: AsyncSession = Depends(get_session)):
    row = await require_resume(session, user, resume_id)
    await session.execute(text(
        "UPDATE task SET status = 'canceled', finished_at = now() "
        "WHERE resource_id = :id AND type = 'resume_parse' "
        "AND status IN ('queued', 'running')"
    ), {"id": resume_id})
    versions = (await session.execute(
        text("SELECT text_uri FROM resume_version WHERE resume_id = :id"), {"id": resume_id},
    )).scalars().all()
    await session.execute(text(
        "DELETE FROM assessment WHERE resume_version_id IN "
        "(SELECT id FROM resume_version WHERE resume_id = :id)"
    ), {"id": resume_id})
    await session.execute(text(
        "DELETE FROM evidence_conflict WHERE source_a_id IN (SELECT e.id FROM evidence e "
        "JOIN resume_claim c ON c.id = e.claim_id "
        "JOIN resume_version v ON v.id = c.resume_version_id WHERE v.resume_id = :id) "
        "OR source_b_id IN (SELECT e.id FROM evidence e "
        "JOIN resume_claim c ON c.id = e.claim_id "
        "JOIN resume_version v ON v.id = c.resume_version_id WHERE v.resume_id = :id)"
    ), {"id": resume_id})
    await session.execute(text(
        "DELETE FROM evidence WHERE claim_id IN (SELECT c.id FROM resume_claim c "
        "JOIN resume_version v ON v.id = c.resume_version_id WHERE v.resume_id = :id)"
    ), {"id": resume_id})
    await session.execute(text("DELETE FROM resume WHERE id = :id"), {"id": resume_id})
    await record_audit(session, user, "resume.delete", "resume", resume_id)
    await session.commit()
    await Storage().delete(row["file_uri"])
    for uri in versions:
        if uri:
            await Storage().delete(uri)
    return {"id": resume_id, "status": "deleted"}
