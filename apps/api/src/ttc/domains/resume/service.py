import base64
import io
import json
import logging
import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

import httpx
from docx import Document
from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ttc.adapters.llm import LLMAdapter
from ttc.adapters.storage import Storage
from ttc.core.config import get_settings
from ttc.core.errors import TTCError
from ttc.core.security import uuid7

logger = logging.getLogger(__name__)

CLAIM_TYPES = {"education", "work", "project", "publication", "patent", "award",
               "skill", "contact", "summary"}

IMAGE_MIMES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
OCR_MAX_PAGES = 20
OCR_RENDER_DPI = 200
OCR_TIMEOUT_SECONDS = 60
OCR_MIN_CHARS = 20

VLM_PROMPT = (
    "你是简历扫描件转写器。按阅读顺序逐行转写图片中的全部文字，"
    "尽量保留原有段落、列表与表格的换行结构。"
    "不要总结、不要改写、不要补全任何未出现的信息；"
    "无法辨认的字用 [不清] 代替。"
    "只输出转写文本，不要 Markdown 代码块，不要任何解释。"
)

_ocr_config: tuple[str, str | None] | None = None


def _vlm_models() -> list[str]:
    raw = get_settings().ocr_vlm_models or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _vlm_key() -> str | None:
    settings = get_settings()
    return settings.ocr_vlm_api_key or settings.dashscope_api_key


def _vlm_enabled() -> bool:
    return bool(_vlm_models() and _vlm_key())


def _ocr_quality(value: str) -> tuple[bool, str]:
    """粗粒度质量闸门：只挡明显坏结果，识别内容是否准确由后续字段校验负责。"""
    stripped = value.strip()
    if len(stripped) < OCR_MIN_CHARS:
        return False, "识别文字过少"
    noise = sum(1 for char in stripped
                if char == "�" or (ord(char) < 32 and char not in "\n\r\t"))
    if noise / len(stripped) > 0.02:
        return False, "识别结果乱码偏多"
    return True, ""


def _call_vlm(model: str, data: bytes, mime: str) -> str:
    settings = get_settings()
    encoded = base64.b64encode(data).decode()
    try:
        response = httpx.post(
            f"{settings.ocr_vlm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {_vlm_key()}"},
            json={
                "model": model,
                "temperature": 0,
                "max_tokens": 4096,
                "messages": [
                    {"role": "system", "content": VLM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                        {"type": "text", "text": "请转写这一页。"},
                    ]},
                ],
            },
            timeout=settings.ocr_vlm_timeout_seconds,
            trust_env=False,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except httpx.TimeoutException as exc:
        raise TTCError("TTC-3003", f"{model} 超时", 422) from exc
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise TTCError("TTC-3003", f"{model} 调用失败", 422) from exc
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content
                          if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise TTCError("TTC-3003", f"{model} 返回空内容", 422)
    return content


def _vlm_page(data: bytes, mime: str) -> tuple[str, str, list[str]]:
    """按模型链转写一页；质量不足或调用失败时换链上下一个（更强的）模型。

    链上全部失败直接报错，不回落 tesseract。
    """
    models = _vlm_models()
    warnings: list[str] = []
    reasons: list[str] = []
    for index, model in enumerate(models):
        try:
            value = _call_vlm(model, data, mime)
        except TTCError as exc:
            reasons.append(f"{model}：{exc.message}")
            if index + 1 < len(models):
                warnings.append(f"{model} 调用失败，改用 {models[index + 1]}")
            continue
        ok, reason = _ocr_quality(value)
        if ok:
            return value.strip(), model, warnings
        reasons.append(f"{model}：{reason}")
        if index + 1 < len(models):
            warnings.append(f"{model} {reason}，改用 {models[index + 1]}")
    raise TTCError("TTC-3003", "视觉 OCR 未通过：" + "；".join(reasons), 422)


def _ocr_language() -> tuple[str, str | None]:
    """返回 (tesseract 语言串, 降级说明)。语言包缺失时降级而不是整体失败。"""
    global _ocr_config
    if _ocr_config is not None:
        return _ocr_config
    try:
        proc = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                              text=True, timeout=15, check=True)
    except FileNotFoundError as exc:
        raise TTCError("TTC-3003", "扫描件需要 OCR，但服务器未安装 tesseract", 422) from exc
    except subprocess.SubprocessError as exc:
        raise TTCError("TTC-3003", "OCR 引擎不可用", 422) from exc
    available = set(proc.stdout.split())
    if "chi_sim" in available:
        _ocr_config = ("chi_sim+eng" if "eng" in available else "chi_sim", None)
    elif "eng" in available:
        _ocr_config = ("eng", "缺少 chi_sim 语言包，本次仅用英文模型识别")
    else:
        raise TTCError("TTC-3003", "OCR 引擎缺少可用语言包", 422)
    return _ocr_config


def _run_tesseract(path: Path, langs: str) -> str:
    try:
        proc = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", langs, "--psm", "3"],
            capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise TTCError("TTC-3003", "OCR 识别超时；请上传更小的文件", 422) from exc
    except OSError as exc:
        raise TTCError("TTC-3003", "OCR 引擎不可用", 422) from exc
    if proc.returncode != 0:
        raise TTCError("TTC-3003", "OCR 识别失败", 422)
    return proc.stdout


def _ensure_ocr_text(texts: list[str]) -> None:
    """只有所有页面都没识别出文字时才判整份失败。"""
    if not any(text.strip() for text in texts):
        raise TTCError(
            "TTC-3003",
            "扫描件所有页面均未识别出文字；请上传可复制文本的 PDF 或更清晰的图片",
            422,
        )


def _ocr_pdf(data: bytes) -> tuple[list[str], str, list[str]]:
    warnings: list[str] = []
    use_vlm = _vlm_enabled()
    langs = ""
    if not use_vlm:
        langs, warning = _ocr_language()
        warnings = [warning] if warning else []
    with tempfile.TemporaryDirectory(prefix="ttc-ocr-") as tmp:
        root = Path(tmp)
        source = root / "input.pdf"
        source.write_bytes(data)
        try:
            subprocess.run(
                ["pdftoppm", "-r", str(OCR_RENDER_DPI), "-png", "-f", "1",
                 "-l", str(OCR_MAX_PAGES), str(source), str(root / "page")],
                capture_output=True, timeout=OCR_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise TTCError("TTC-3003", "服务器缺少 pdftoppm，无法渲染扫描件", 422) from exc
        except subprocess.TimeoutExpired as exc:
            raise TTCError("TTC-3003", "扫描件渲染超时", 422) from exc
        images = sorted(root.glob("page*.png"))
        if not images:
            raise TTCError("TTC-3003", "扫描件没有可识别的页面", 422)
        if not use_vlm:
            texts = []
            for page_no, image in enumerate(images, 1):
                try:
                    texts.append(_run_tesseract(image, langs))
                except TTCError as exc:
                    texts.append("")
                    warnings.append(f"第 {page_no} 页 OCR 失败，已跳过：{exc.message}")
            _ensure_ocr_text(texts)
            return texts, f"tesseract:{langs}", warnings
        texts: list[str] = []
        used: list[str] = []
        for page_no, image in enumerate(images, 1):
            try:
                page_text, model, page_warnings = _vlm_page(image.read_bytes(),
                                                            "image/png")
            except TTCError as exc:
                # 空白页、分隔页、纯图表页在扫描简历里很常见；单页识别失败
                # 不应让整份简历失败。保留空占位，避免 claim 页码错位。
                texts.append("")
                warnings.append(f"第 {page_no} 页未识别出文字，已跳过：{exc.message}")
                continue
            texts.append(page_text)
            used.append(model)
            warnings.extend(f"第 {page_no} 页：{item}" for item in page_warnings)
        _ensure_ocr_text(texts)
        label = "+".join(dict.fromkeys(used))
        return texts, f"vlm:{label}", warnings


def _ocr_image(data: bytes, mime: str) -> tuple[list[str], str, list[str]]:
    if _vlm_enabled():
        try:
            text, model, warnings = _vlm_page(data, mime)
        except TTCError as exc:
            raise TTCError("TTC-3003", f"图片 {exc.message}", 422) from exc
        return [text], f"vlm:{model}", warnings
    langs, warning = _ocr_language()
    warnings = [warning] if warning else []
    with tempfile.TemporaryDirectory(prefix="ttc-ocr-") as tmp:
        target = Path(tmp) / f"upload{IMAGE_MIMES[mime]}"
        target.write_bytes(data)
        return [_run_tesseract(target, langs)], f"tesseract:{langs}", warnings


def _matches_image_format(data: bytes, mime: str) -> bool:
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    return data.startswith(b"RIFF") and data[8:12] == b"WEBP"


def validate_document(data: bytes, mime: str) -> None:
    """上传阶段的轻校验：只验证格式与可读性，不做 OCR。

    OCR 很慢（扫描 PDF 每页数百毫秒），放到解析任务里跑；这里提前挡掉
    扩展名伪装、加密 PDF 和损坏文件。
    """
    try:
        if mime == "application/pdf":
            if not data.startswith(b"%PDF-"):
                raise TTCError("TTC-3004", "文件内容与扩展名不符", 422)
            if PdfReader(io.BytesIO(data)).is_encrypted:
                raise TTCError("TTC-3003", "不支持加密 PDF", 422)
        elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            if not data.startswith(b"PK\x03\x04"):
                raise TTCError("TTC-3004", "文件内容与扩展名不符", 422)
            Document(io.BytesIO(data))
        elif mime in IMAGE_MIMES:
            if not _matches_image_format(data, mime):
                raise TTCError("TTC-3004", "文件内容与扩展名不符", 422)
        else:
            data.decode("utf-8-sig")
    except TTCError:
        raise
    except Exception as exc:
        raise TTCError("TTC-3003", "文件损坏或无法读取", 422) from exc


def extract_text_with_meta(data: bytes, mime: str) -> tuple[str, list[str], dict]:
    """抽取文本；扫描件走 OCR，并在 meta 里说明是否降级。"""
    warnings: list[str] = []
    ocr: str | None = None
    try:
        if mime == "application/pdf":
            if not data.startswith(b"%PDF-"):
                raise TTCError("TTC-3004", "文件内容与扩展名不符", 422)
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise TTCError("TTC-3003", "不支持加密 PDF", 422)
            pages = [page.extract_text() or "" for page in reader.pages]
            if not "\n".join(pages).strip():
                pages, label, ocr_warnings = _ocr_pdf(data)
                warnings.extend(ocr_warnings)
                ocr = f"ocr:{label}"
        elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            if not data.startswith(b"PK\x03\x04"):
                raise TTCError("TTC-3004", "文件内容与扩展名不符", 422)
            document = Document(io.BytesIO(data))
            pages = ["\n".join(paragraph.text for paragraph in document.paragraphs)]
        elif mime in IMAGE_MIMES:
            if not _matches_image_format(data, mime):
                raise TTCError("TTC-3004", "文件内容与扩展名不符", 422)
            pages, label, ocr_warnings = _ocr_image(data, mime)
            warnings.extend(ocr_warnings)
            ocr = f"ocr:{label}"
        else:
            pages = [data.decode("utf-8-sig")]
    except TTCError:
        raise
    except Exception as exc:
        raise TTCError("TTC-3003", "文件损坏或无法提取文本", 422) from exc
    value = "\n".join(pages).strip()
    if not value:
        if ocr:
            raise TTCError("TTC-3003",
                           "扫描件未能识别出文字；请上传可复制文本的 PDF 或更清晰的图片", 422)
        raise TTCError("TTC-3003", "文件没有可解析的文字", 422)
    return value, pages, {"ocr": ocr, "warnings": warnings}


def extract_text(data: bytes, mime: str) -> tuple[str, list[str]]:
    value, pages, _ = extract_text_with_meta(data, mime)
    return value, pages


async def parse_resume(session: AsyncSession, resume_id, *, llm=None, storage=None) -> int:
    resume = (await session.execute(
        text("SELECT r.id, r.file_uri, r.mime, r.candidate_id, c.tenant_id FROM resume r "
             "JOIN candidate c ON c.id = r.candidate_id WHERE r.id = :id"),
        {"id": resume_id},
    )).mappings().one()
    storage = storage or Storage()
    data = await storage.get(resume["file_uri"])
    resume_text, pages, extraction = extract_text_with_meta(data, resume["mime"])
    model = get_settings().llm_model or "unconfigured"
    if extraction["ocr"]:
        model = f"{model}+{extraction['ocr']}"
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
