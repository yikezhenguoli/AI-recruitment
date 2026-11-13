"""简历-岗位匹配小模型适配器。

小模型由 `resume-match/infer_cli.py` 以子进程方式暴露；本服务不 import torch，
只负责：写临时文本文件 -> 调子进程 -> 校验 stdout JSON 契约。

契约（stdout 一行 JSON）：
    {"category": "...", "confidence": 0.87,
     "top_k": [{"code": "...", "score": 0.87}, ...],
     "model_version": "deberta-v3-base@<run_id>",
     "scores": {"ACCOUNTANT": 0.001, ... 24 类 ...}}
"""

import asyncio
import json
import math
import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path

from ttc.core.config import get_settings
from ttc.core.errors import TTCError

# 数据集目录名，必须与 resume-match/jd/jobs_24.yaml 的 code 逐字一致
CATEGORY_CODES: frozenset[str] = frozenset({
    "ACCOUNTANT", "ADVOCATE", "AGRICULTURE", "APPAREL", "ARTS", "AUTOMOBILE",
    "AVIATION", "BANKING", "BPO", "BUSINESS-DEVELOPMENT", "CHEF", "CONSTRUCTION",
    "CONSULTANT", "DESIGNER", "DIGITAL-MEDIA", "ENGINEERING", "FINANCE", "FITNESS",
    "HEALTHCARE", "HR", "INFORMATION-TECHNOLOGY", "PUBLIC-RELATIONS", "SALES",
    "TEACHER",
})

# 仅在 RESUME_MATCH_ALLOW_KEYWORD_FALLBACK=true 时使用；只是让前端先能跑通的粗糙兜底，
# 不代表模型能力。每个类别给少量中英文关键词，命中数作为类别倾向。
KEYWORD_FALLBACK_HINTS: dict[str, tuple[str, ...]] = {
    "ACCOUNTANT": ("accounting", "accountant", "tax", "ledger", "financial statement",
                   "会计", "税务", "财务", "报表"),
    "ADVOCATE": ("lawyer", "legal", "litigation", "attorney", "law firm",
                 "律师", "法律", "诉讼", "合同"),
    "AGRICULTURE": ("agriculture", "crop", "farming", "agronomy", "irrigation",
                    "农业", "作物", "种植", "田间"),
    "APPAREL": ("apparel", "garment", "fashion", "textile", "clothing",
                "服装", "面料", "制版", "纺织"),
    "ARTS": ("artist", "artwork", "painting", "exhibition", "gallery",
             "艺术", "绘画", "展览", "作品"),
    "AUTOMOBILE": ("automotive", "vehicle", "engine", "mechanic", "repair",
                   "汽车", "发动机", "维修", "保养"),
    "AVIATION": ("aviation", "aircraft", "flight", "airline", "airport",
                 "航空", "飞机", "航班", "机务"),
    "BANKING": ("banking", "bank", "loan", "deposit", "credit",
                "银行", "贷款", "存款", "信贷"),
    "BPO": ("bpo", "outsourcing", "back office", "call center", "sla",
            "外包", "客服", "工单", "后台"),
    "BUSINESS-DEVELOPMENT": ("business development", "partnership", "channel", "deal",
                             "商务拓展", "渠道", "合作", "商务"),
    "CHEF": ("chef", "kitchen", "culinary", "cooking", "menu",
             "厨师", "厨房", "菜品", "烹饪"),
    "CONSTRUCTION": ("construction", "civil engineering", "concrete", "scaffold",
                     "建筑", "施工", "工地", "土木"),
    "CONSULTANT": ("consultant", "consulting", "advisory", "diagnosis",
                   "咨询", "顾问", "方案", "调研"),
    "DESIGNER": ("designer", "figma", "ui design", "ux", "visual design",
                 "设计", "交互", "视觉", "原型"),
    "DIGITAL-MEDIA": ("digital media", "social media", "content", "video editing",
                      "新媒体", "短视频", "内容运营", "剪辑"),
    "ENGINEERING": ("engineer", "mechanical", "electrical", "cad", "prototype",
                    "工程师", "机械", "电气", "图纸"),
    "FINANCE": ("finance", "financial analyst", "valuation", "investment", "modeling",
                "金融", "投资", "估值", "建模"),
    "FITNESS": ("fitness", "trainer", "personal training", "gym",
                "健身", "教练", "体能", "训练"),
    "HEALTHCARE": ("healthcare", "nurse", "nursing", "clinical", "patient",
                   "医疗", "护理", "临床", "患者"),
    "HR": ("human resources", "recruitment", "onboarding", "compensation",
           "人力资源", "招聘", "薪酬", "员工关系"),
    "INFORMATION-TECHNOLOGY": ("information technology", "it support", "backend", "api",
                               "database", "postgresql", "python", "docker", "kubernetes",
                               "devops", "network", "linux", "server",
                               "信息技术", "运维", "网络", "服务器", "后端", "数据库"),
    "PUBLIC-RELATIONS": ("public relations", "media relations", "press release",
                         "公关", "舆情", "媒体", "品牌传播"),
    "SALES": ("sales", "selling", "quota", "customer development",
              "销售", "客户开发", "业绩", "谈判"),
    "TEACHER": ("teacher", "teaching", "curriculum", "classroom", "lesson",
                "教师", "教学", "课程", "学生"),
}

_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "have", "has", "are",
    "was", "were", "will", "can", "you", "our", "your", "their", "his", "her",
    "not", "all", "any", "may", "must", "should", "would", "able", "use", "using",
    "job", "role", "work", "team", "years", "year", "plus", "etc",
})
_ASCII_TOKEN = re.compile(r"[a-z][a-z0-9+#./-]{2,}")
_CJK_RUN = re.compile(r"[㐀-鿿]{2,}")


def _repo_root() -> Path:
    # .../apps/api/src/ttc/adapters/matcher.py -> 仓库根目录
    return Path(__file__).resolve().parents[5]


def _resolve_cli() -> Path:
    settings = get_settings()
    if settings.resume_match_cli_path:
        return Path(settings.resume_match_cli_path).expanduser()
    return _repo_root() / "resume-match" / "infer_cli.py"


def _resolve_model_dir() -> Path:
    settings = get_settings()
    if settings.resume_match_model_dir:
        return Path(settings.resume_match_model_dir).expanduser()
    return _repo_root() / "resume-match" / "runs" / "latest" / "best"


def _tokens(value: str) -> set[str]:
    lowered = value.casefold()
    tokens = {token for token in _ASCII_TOKEN.findall(lowered) if token not in _STOPWORDS}
    for run in _CJK_RUN.findall(value):
        tokens.update(run[index:index + 2] for index in range(len(run) - 1))
    return tokens


def _jd_overlap(resume_text: str, jd_text: str) -> float:
    jd_tokens = _tokens(jd_text)
    if not jd_tokens:
        return 0.0
    resume_folded = resume_text.casefold()
    hits = sum(_hint_hit(resume_folded, token) for token in jd_tokens)
    return min(1.0, hits / len(jd_tokens))


def _hint_hit(folded: str, hint: str) -> bool:
    """英文关键词按词边界匹配，避免 engineer 命中 engine 这类子串误判；中文按子串。"""
    if hint.isascii():
        pattern = r"(?<![a-z0-9])" + re.escape(hint) + r"(?:s|es)?(?![a-z0-9])"
        return re.search(pattern, folded) is not None
    return hint in folded


def _keyword_fallback(text: str, jd_text: str | None) -> dict:
    """JD 关键词重叠度 + 类别关键词命中；只用于本地联调，不是模型结论。"""
    folded = text.casefold()
    raw: dict[str, float] = {}
    for code, hints in KEYWORD_FALLBACK_HINTS.items():
        hits = sum(_hint_hit(folded, hint) for hint in hints)
        # 用命中个数计分并加 0.1 平滑；不除以关键词总数，避免关键词多的类别被稀释
        raw[code] = hits + 0.1
    total = sum(raw.values())
    scores = {code: round(value / total, 6) for code, value in raw.items()}
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    overlap = _jd_overlap(text, jd_text or "")
    return {
        "category": ranked[0][0],
        "confidence": round(overlap, 4),
        "top_k": [{"code": code, "score": score} for code, score in ranked],
        "model_version": "keyword-fallback",
        "scores": scores,
    }


def _parse_output(stdout: bytes) -> dict:
    """取 stdout 最后一行可解析的 JSON，并做契约校验。"""
    lines: Iterable[str] = (line.strip() for line in
                            stdout.decode("utf-8", "replace").splitlines())
    payload = None
    for line in lines:
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
    if not isinstance(payload, dict):
        raise TTCError("TTC-5002", "匹配模型输出不是合法 JSON", 502)
    return _validate_payload(payload)


def _validate_payload(payload: dict) -> dict:
    scores = payload.get("scores")
    if not isinstance(scores, dict) or set(scores) != CATEGORY_CODES:
        raise TTCError("TTC-5002", "匹配模型输出的 24 类分数不完整", 502)
    try:
        clean_scores = {code: float(value) for code, value in scores.items()}
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise TTCError("TTC-5002", "匹配模型输出分数不是数字", 502) from exc
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise TTCError("TTC-5002", "匹配模型输出的 confidence 越界", 502)
    if any(not math.isfinite(value) or not 0 <= value <= 1
           for value in clean_scores.values()):
        raise TTCError("TTC-5002", "匹配模型输出的类别分数越界", 502)
    category = payload.get("category")
    if not isinstance(category, str) or category not in CATEGORY_CODES:
        raise TTCError("TTC-5002", "匹配模型输出的 category 不在 24 类内", 502)
    top_k = payload.get("top_k")
    if not isinstance(top_k, list) or not top_k:
        raise TTCError("TTC-5002", "匹配模型输出的 top_k 无效", 502)
    clean_top = []
    for item in top_k:
        if not isinstance(item, dict) or item.get("code") not in CATEGORY_CODES:
            raise TTCError("TTC-5002", "匹配模型输出的 top_k 含未知类别", 502)
        try:
            score = float(item.get("score"))
        except (TypeError, ValueError) as exc:
            raise TTCError("TTC-5002", "匹配模型输出的 top_k 分数无效", 502) from exc
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise TTCError("TTC-5002", "匹配模型输出的 top_k 分数越界", 502)
        clean_top.append({"code": item["code"], "score": round(score, 6)})
    model_version = payload.get("model_version")
    if not isinstance(model_version, str) or not model_version.strip():
        raise TTCError("TTC-5002", "匹配模型输出缺少 model_version", 502)
    result = {"category": category, "confidence": round(confidence, 6),
              "top_k": clean_top, "model_version": model_version.strip(),
              "scores": {key: round(value, 6) for key, value in clean_scores.items()}}
    # pair 模型额外给出「这份简历对这个 JD」的概率；旧模型没有这个字段
    raw_jd_score = payload.get("jd_match_score")
    if raw_jd_score is not None:
        try:
            jd_score = float(raw_jd_score)
        except (TypeError, ValueError) as exc:
            raise TTCError("TTC-5002", "jd_match_score 不是数字", 502) from exc
        if not math.isfinite(jd_score) or not 0 <= jd_score <= 1:
            raise TTCError("TTC-5002", "jd_match_score 越界", 502)
        result["jd_match_score"] = round(jd_score, 6)
    return result


class ResumeMatchAdapter:
    async def predict(self, text: str, *, jd_text: str | None = None) -> dict:
        settings = get_settings()
        cli = _resolve_cli()
        model_dir = _resolve_model_dir()
        fallback_allowed = settings.resume_match_allow_keyword_fallback
        if not cli.is_file() or not model_dir.is_dir():
            if fallback_allowed:
                return {**_keyword_fallback(text, jd_text),
                        "fallback_reason": "匹配模型文件未就绪，已使用关键词兜底"}
            raise TTCError("TTC-5005", "简历-岗位匹配模型未就绪", 503)
        handle, path = tempfile.mkstemp(prefix="ttc-resume-", suffix=".txt")
        jd_handle = jd_path = None
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as output:
                output.write(text)
            jd_args: list[str] = []
            if jd_text and jd_text.strip():
                jd_handle, jd_path = tempfile.mkstemp(prefix="ttc-jd-", suffix=".txt")
                with os.fdopen(jd_handle, "w", encoding="utf-8") as output:
                    output.write(jd_text)
                jd_args = ["--jd-file", jd_path]
            process = await asyncio.create_subprocess_exec(
                # -E 而不是 -I：-I 会同时屏蔽 user site-packages，而本机的
                # transformers/torch 正装在 ~/.local 下；-E 仍能挡住 PYTHONPATH
                # 里的 ROS 路径污染。
                settings.resume_match_python, "-E", str(cli),
                "--model-dir", str(model_dir), "--text-file", path, *jd_args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=settings.resume_match_timeout_seconds,
                )
            except TimeoutError as exc:
                process.kill()
                await process.communicate()
                raise TTCError("TTC-5001", "匹配模型推理超时", 504) from exc
        finally:
            Path(path).unlink(missing_ok=True)
            if jd_path:
                Path(jd_path).unlink(missing_ok=True)
        if process.returncode != 0:
            if fallback_allowed:
                return {**_keyword_fallback(text, jd_text),
                        "fallback_reason": "匹配模型调用失败，已使用关键词兜底"}
            detail = stderr.decode("utf-8", "replace").strip().splitlines()
            raise TTCError("TTC-5005", "简历-岗位匹配模型调用失败", 503,
                           details={"stderr": detail[-1] if detail else ""})
        return _parse_output(stdout)
