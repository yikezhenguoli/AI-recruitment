"""人才库向量索引与检索。

两种后端，能力不同，接口会如实返回用的是哪一种：

- `embedding`：配置了 `EMBEDDING_BASE_URL/API_KEY/MODEL` 时调用 OpenAI 兼容的
  `/embeddings` 接口，能处理同义改写；
- `lexical`：未配置时用本地字符 n-gram 哈希向量（中文 unigram+bigram、英文词），
  只对字面重合敏感，**不具备语义泛化能力**。

检索在应用层做内积，租户候选人规模在万级以内足够；再大应换成 pgvector
或外部向量库。
"""

import hashlib
import math
import re
from uuid import UUID

import httpx
from sqlalchemy import text

from ttc.core.config import get_settings
from ttc.core.errors import TTCError
from ttc.core.security import uuid7

_CJK = re.compile(r"[㐀-鿿]+")
_WORD = re.compile(r"[a-zA-Z0-9+#.]{2,}")
_WEIGHTS = {1: 0.3, 2: 1.0}


def _tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for run in _CJK.findall(value):
        tokens.extend(run)
        tokens.extend(run[index:index + 2] for index in range(len(run) - 1))
    tokens.extend(word.lower() for word in _WORD.findall(value))
    return tokens


def _hash_index(token: str, dim: int) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % dim, (1.0 if value >> 63 else -1.0)


def local_vector(value: str, dim: int) -> list[float]:
    vector = [0.0] * dim
    for token in _tokens(value):
        index, sign = _hash_index(token, dim)
        vector[index] += sign * _WEIGHTS.get(len(token), 1.0)
    return vector


def _normalize(vector: list[float]) -> tuple[list[float], float]:
    norm = math.sqrt(sum(item * item for item in vector))
    if norm == 0:
        return vector, 1.0
    return [item / norm for item in vector], norm


def _embedding_configured() -> bool:
    settings = get_settings()
    return bool(settings.embedding_base_url and settings.embedding_api_key
                and settings.embedding_model)


async def remote_embedding(values: list[str]) -> list[list[float]]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            response = await client.post(
                settings.embedding_base_url.rstrip("/") + "/embeddings",
                headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                json={"model": settings.embedding_model, "input": values},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TTCError("TTC-5004", "向量模型不可用", 503) from exc
    try:
        items = sorted(payload["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in items]
    except (KeyError, TypeError, IndexError) as exc:
        raise TTCError("TTC-5002", "向量模型输出不符合契约", 502) from exc


async def embed_texts(values: list[str]) -> tuple[str, str, list[list[float]], str | None]:
    """返回 (backend, model, vectors, warning)。"""
    settings = get_settings()
    if _embedding_configured():
        try:
            return ("embedding", settings.embedding_model,
                    await remote_embedding(values), None)
        except TTCError as exc:
            warning = f"向量模型调用失败，已回落本地词面向量：{exc.message}"
            return ("lexical", f"hash-ngram-{settings.embedding_dim}",
                    [local_vector(value, settings.embedding_dim) for value in values],
                    warning)
    return ("lexical", f"hash-ngram-{settings.embedding_dim}",
            [local_vector(value, settings.embedding_dim) for value in values], None)


async def index_candidate(session, *, tenant_id: UUID, candidate_id: UUID,
                          resume_version_id: UUID, content: str,
                          warning_sink: list[str] | None = None) -> dict:
    backend, model, vectors, warning = await embed_texts([content])
    if warning and warning_sink is not None:
        warning_sink.append(warning)
    vector = vectors[0]
    norm = math.sqrt(sum(item * item for item in vector)) or 1.0
    digest = hashlib.sha256(content.encode()).hexdigest()
    row = (await session.execute(text(
        "INSERT INTO talent_index (id, tenant_id, candidate_id, resume_version_id, backend, "
        "model, dim, vector, norm, content_hash) "
        "VALUES (:id, :tenant, :candidate, :version, :backend, :model, :dim, "
        "CAST(:vector AS double precision[]), :norm, :hash) "
        "ON CONFLICT (candidate_id, resume_version_id, backend, model) DO UPDATE SET "
        "vector = EXCLUDED.vector, norm = EXCLUDED.norm, dim = EXCLUDED.dim, "
        "content_hash = EXCLUDED.content_hash, updated_at = now() "
        "RETURNING id, backend, model, dim, updated_at"
    ), {"id": uuid7(), "tenant": tenant_id, "candidate": candidate_id,
        "version": resume_version_id, "backend": backend, "model": model,
        "dim": len(vector), "vector": vector, "norm": norm, "hash": digest})).mappings().one()
    return dict(row)


def _cosine(left: list[float], left_norm: float,
            right: list[float], right_norm: float) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


async def search_candidates(session, *, tenant_id: UUID, query: str, limit: int,
                            backend_filter: str | None = None) -> dict:
    backend, model, vectors, warning = await embed_texts([query])
    query_vector = vectors[0]
    query_norm = math.sqrt(sum(item * item for item in query_vector)) or 1.0
    rows = (await session.execute(text(
        "SELECT ti.candidate_id, ti.backend, ti.model, ti.vector, ti.norm, ti.dim, "
        "c.display_name, ti.resume_version_id "
        "FROM talent_index ti JOIN candidate c ON c.id = ti.candidate_id "
        "WHERE ti.tenant_id = :tenant "
        "AND (CAST(:backend AS text) IS NULL OR ti.backend = CAST(:backend AS text))"
    ), {"tenant": tenant_id, "backend": backend_filter})).mappings().all()
    scored = []
    for row in rows:
        score = _cosine(query_vector, query_norm, list(row["vector"]), row["norm"])
        if score > 0:
            scored.append({"candidate_id": row["candidate_id"],
                           "display_name": row["display_name"],
                           "score": round(score, 6), "backend": row["backend"],
                           "model": row["model"],
                           "resume_version_id": row["resume_version_id"]})
    scored.sort(key=lambda item: item["score"], reverse=True)
    top = scored[:limit]
    await _attach_snippets(session, top, query)
    return {"query": query, "backend": backend, "model": model,
            "indexed": len(rows), "items": top, "warning": warning}


async def _attach_snippets(session, items: list[dict], query: str) -> None:
    if not items:
        return
    needles = [token for token in _tokens(query) if len(token) >= 2][:8]
    if not needles:
        return
    rows = (await session.execute(text(
        "SELECT rc.resume_version_id, rc.raw_text FROM resume_claim rc "
        "WHERE rc.resume_version_id = ANY(CAST(:versions AS uuid[])) "
        "AND rc.claim_type NOT IN ('contact')"
    ), {"versions": [item["resume_version_id"] for item in items]})).mappings().all()
    by_version: dict[UUID, list[str]] = {}
    for row in rows:
        by_version.setdefault(row["resume_version_id"], []).append(row["raw_text"])
    for item in items:
        matched = []
        for raw in by_version.get(item["resume_version_id"], []):
            if any(needle in raw for needle in needles):
                matched.append(raw[:160])
            if len(matched) >= 3:
                break
        item["snippets"] = matched


async def similar_to(session, *, tenant_id: UUID, candidate_id: UUID,
                     limit: int) -> dict:
    source = (await session.execute(text(
        "SELECT id, vector, norm, backend, model, resume_version_id FROM talent_index "
        "WHERE tenant_id = :tenant AND candidate_id = :candidate "
        "ORDER BY updated_at DESC LIMIT 1"
    ), {"tenant": tenant_id, "candidate": candidate_id})).mappings().one_or_none()
    if source is None:
        raise TTCError("TTC-2002", "该候选人尚未建立索引，请先重建索引", 409)
    rows = (await session.execute(text(
        "SELECT ti.candidate_id, ti.vector, ti.norm, ti.backend, ti.model, "
        "ti.resume_version_id, c.display_name FROM talent_index ti "
        "JOIN candidate c ON c.id = ti.candidate_id "
        "WHERE ti.tenant_id = :tenant AND ti.candidate_id <> :candidate "
        "AND ti.backend = :backend AND ti.model = :model AND ti.dim = :dim"
    ), {"tenant": tenant_id, "candidate": candidate_id, "backend": source["backend"],
        "model": source["model"], "dim": len(source["vector"])})).mappings().all()
    scored = [{"candidate_id": row["candidate_id"], "display_name": row["display_name"],
               "score": round(_cosine(list(source["vector"]), source["norm"],
                                      list(row["vector"]), row["norm"]), 6),
               "backend": row["backend"], "model": row["model"],
               "resume_version_id": row["resume_version_id"]}
              for row in rows]
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {"candidate_id": candidate_id, "backend": source["backend"],
            "model": source["model"], "items": scored[:limit]}
