#!/usr/bin/env python3
"""500 份全合成简历 × 24 个 JD 的 GBDT 24 选 1 评测。

数据：synth/resumes.csv（全合成，300 训练 / 100 验证 / 100 测试）+ jd/jobs_24.yaml。
模型：sklearn HistGradientBoostingClassifier 二分类，每条 (简历, JD) 一个样本，
正样本 = 该简历的真实类别，负样本 = 其余 23 个 JD。训练集 300×24=7200 对。

指标口径沿用 evaluate_pair.py：Recall@1/3/5、MRR、mean/median rank、
mean/min/p10 margin；TF-IDF 余弦基线；配对 bootstrap（2000 次）给
模型−基线的 Recall@1 差值、95%CI 与双侧 p；按类 per_class。

三条证伪：
  * JD 只留标题：用标题重建全部 JD 侧特征并重新训练同款 GBDT；
  * JD 只留正文：去掉标题、标题类特征置 0，重新训练；
  * JD 打乱：完整模型，评测时 JD 列表整体循环右移一位，真实类别的 JD 落到
    相邻列，指标仍按原列判定，Recall@1 不应高于随机水平 1/24（通常为 0），
    mean_rank 应接近 12.5。

诚实性：合成简历由 JD 模板生成，指标近似"上限"，不代表真实简历泛化能力。

只依赖 numpy / scikit-learn / PyYAML，不 import torch。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import yaml
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

FEATURE_NAMES = [
    "cos_char2_4",        # 中文 char 2-4 gram TF-IDF 余弦
    "cos_char1_2",        # 中文 char 1-2 gram TF-IDF 余弦
    "latin_jaccard",      # 拉丁 token Jaccard
    "latin_coverage",     # JD 拉丁 token 被简历覆盖的比例
    "skill_hit_ratio",    # JD 技能短语命中比例
    "skill_hit_count",    # JD 技能短语命中数
    "years_diff",         # 简历年限 − JD 最低年限
    "years_ok",           # 是否达到 JD 最低年限
    "edu_diff",           # 简历学历等级 − JD 学历等级
    "intent_title_cos",   # 求职意向 vs JD 标题 char 余弦
    "intent_hit_title",   # 求职意向是否包含/被包含于 JD 标题
    "log_resume_len",     # log1p(简历字数)
    "log_jd_len",         # log1p(JD 字数)
    "len_ratio",          # 简历字数 / JD 字数
]

GBDT_PARAMS = dict(
    max_iter=400,
    learning_rate=0.06,
    max_leaf_nodes=31,
    l2_regularization=1.0,
    class_weight="balanced",
    random_state=42,
    early_stopping=False,
)

EDU_LEVELS = (
    ("博士", 5),
    ("硕士", 4),
    ("本科", 3),
    ("学士", 3),
    ("专科", 2),
    ("大专", 2),
    ("高职", 2),
    ("中专", 1),
    ("中职", 1),
    ("高中", 1),
)

def json_default(value):
    """numpy 标量 → 原生类型；其他对象转 str。"""
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


_SPACE_RE = re.compile(r"[ \t　]+")
_NEWLINE_RE = re.compile(r"\n{2,}")
_LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./\-]*")
_EDU_LINE_RE = re.compile(r"教育背景[：:]([^\n]+)")
_INTENT_RE = re.compile(r"求职意向[：:]\s*([^\n]+)")
_YEARS_RE = re.compile(r"工作经验[：:]\s*(\d+)\s*年")


# --------------------------------------------------------------------- 文本工具
def normalize_text(text: str) -> str:
    """清理不可见字符与冗余空白，保留换行。"""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\xa0", " ").replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("​", "")
    text = _SPACE_RE.sub(" ", text)
    text = _NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def latin_tokens(text: str) -> set[str]:
    return {tok.lower() for tok in _LATIN_RE.findall(text)}


def split_terms(text: str) -> list[str]:
    """把 JD 技能句拆成短语：去掉「XX技能：」前缀，括号当分隔符。"""
    if not text:
        return []
    body = text.split("：", 1)[-1]
    body = re.sub(r"[（(【\[]", "、", body)
    body = re.sub(r"[）)】\]]", "、", body)
    terms = re.split(r"[、，,；;]", body)
    cleaned = (term.strip(" 。.") for term in terms)
    return [term for term in cleaned if len(term) >= 2]


def jd_skills(job: dict) -> list[str]:
    terms: list[str] = []
    for item in job.get("required_skills_zh") or []:
        terms.extend(split_terms(str(item)))
    seen: list[str] = []
    for term in terms:
        if term not in seen:
            seen.append(term)
    return seen


def parse_min_years(spec: str) -> int | None:
    numbers = [int(n) for n in re.findall(r"\d+", spec or "")]
    return numbers[0] if numbers else None


def edu_level(text: str) -> int | None:
    for word, level in EDU_LEVELS:
        if word in text:
            return level
    return None


def parse_resume(row: dict) -> dict:
    text = normalize_text(row["Resume_str"])
    years_m = _YEARS_RE.search(text)
    intent_m = _INTENT_RE.search(text)
    edu_line_m = _EDU_LINE_RE.search(text)
    edu_text = edu_line_m.group(1) if edu_line_m else text
    return {
        "id": row["ID"].strip(),
        "text": text,
        "text_lower": text.lower(),
        "category": row["Category"].strip(),
        "years": int(years_m.group(1)) if years_m else None,
        "intent": intent_m.group(1).strip() if intent_m else "",
        "edu": edu_level(edu_text),
        "latin": latin_tokens(text),
        "length": len(text),
    }


def jd_body_zh(job: dict) -> str:
    """职责 + 技能 + 学历 + 年限；刻意不含 summary（中文 summary 常是百科长文）。"""
    parts: list[str] = []
    for field in ("responsibilities", "required_skills"):
        value = job.get(f"{field}_zh") or []
        if isinstance(value, str):
            value = [value]
        parts.extend(str(item).strip() for item in value if str(item).strip())
    edu = str(job.get("education_zh") or "").strip()
    if edu:
        parts.append(edu)
    years = job.get("experience_years")
    if years:
        parts.append(f"{years} 年经验")
    return "\n".join(parts)


def parse_jd(job: dict) -> dict:
    title = str(job.get("title_zh") or job["code"]).strip()
    return {
        "code": job["code"],
        "title": title,
        "body": jd_body_zh(job),
        "skills": jd_skills(job),
        "years": parse_min_years(str(job.get("experience_years") or "")),
        "edu": edu_level(str(job.get("education_zh") or "")),
    }


# --------------------------------------------------------------------- 数据加载
def resolve_path(value: str | None, candidates: list[Path]) -> Path:
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (Path.cwd() / path).resolve()
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(f"找不到数据文件，尝试过: {[str(c) for c in candidates]}")


def load_resumes(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle)
        missing = {"ID", "Resume_str", "Category"} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{csv_path} 缺少列 {sorted(missing)}")
        for row in reader:
            if not (row.get("ID") or "").strip():
                continue
            rows.append(parse_resume(row))
    if not rows:
        raise SystemExit(f"{csv_path} 没有读到任何行")
    return rows


def read_split(split_path: Path) -> dict[str, dict[str, str]]:
    table: dict[str, dict[str, str]] = {}
    with split_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = {"ID", "Category", "split"} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{split_path} 缺少列 {sorted(missing)}")
        for row in reader:
            rid = (row.get("ID") or "").strip()
            if rid:
                table[rid] = {"category": (row.get("Category") or "").strip(),
                              "split": (row.get("split") or "").strip()}
    return table


def attach_splits(resumes: list[dict], table: dict[str, dict[str, str]]) -> None:
    """以 split.csv 为准，并逐行校验与 resumes.csv 的类别一致。"""
    problems: list[str] = []
    for item in resumes:
        entry = table.get(item["id"])
        if entry is None:
            problems.append(f"{item['id']}: 不在 split.csv")
            continue
        if entry["category"] != item["category"]:
            problems.append(f"{item['id']}: 类别 {entry['category']} != {item['category']}")
        if entry["split"] not in ("train", "val", "test"):
            problems.append(f"{item['id']}: 非法 split={entry['split']!r}")
        item["split"] = entry["split"]
    extra = set(table) - {item["id"] for item in resumes}
    if extra:
        problems.append(f"split.csv 多出 {len(extra)} 个 ID: {sorted(extra)[:5]}")
    if problems:
        raise SystemExit("数据校验失败:\n  " + "\n  ".join(problems[:20]))


def load_jobs(jd_path: Path) -> list[dict]:
    jobs = yaml.safe_load(jd_path.read_text(encoding="utf-8"))
    if not isinstance(jobs, list) or not jobs:
        raise SystemExit(f"{jd_path} 不是非空列表")
    return [parse_jd(job) for job in jobs]


# --------------------------------------------------------------------- 特征
def variant_jd_texts(jd_docs: list[dict], variant: str) -> list[str]:
    if variant in ("full", "shuffled"):
        return [doc["title"] + "\n" + doc["body"] for doc in jd_docs]
    if variant == "title":
        return [doc["title"] for doc in jd_docs]
    if variant == "body":
        return [doc["body"] for doc in jd_docs]
    raise ValueError(variant)


def build_features(resumes: list[dict], jd_docs: list[dict], variant: str,
                   fit_texts: list[str]) -> np.ndarray:
    """返回 (n_resume, 24, n_feature)。

    variant 决定 JD 侧哪些信息可用：
      full/shuffled：标题 + 正文全部特征；
      title       ：JD 文本=标题，技能/年限/学历三类结构化特征置 0；
      body        ：JD 文本=正文（无标题），标题类特征（intent_title_cos /
                    intent_hit_title）置 0。
    """
    docs = jd_docs
    jd_texts = variant_jd_texts(docs, variant)
    n_res, n_jd = len(resumes), len(docs)

    vec24 = TfidfVectorizer(analyzer="char", ngram_range=(2, 4),
                            sublinear_tf=True, min_df=2)
    vec24.fit(fit_texts + jd_texts)
    res24 = normalize(vec24.transform([r["text"] for r in resumes]))
    jd24 = normalize(vec24.transform(jd_texts))
    cos24 = np.asarray((res24 @ jd24.T).todense(), dtype=np.float64)

    vec12 = TfidfVectorizer(analyzer="char", ngram_range=(1, 2),
                            sublinear_tf=True, min_df=2)
    vec12.fit(fit_texts + jd_texts)
    res12 = normalize(vec12.transform([r["text"] for r in resumes]))
    jd12 = normalize(vec12.transform(jd_texts))
    cos12 = np.asarray((res12 @ jd12.T).todense(), dtype=np.float64)

    intents = [r["intent"] for r in resumes]
    intent12 = normalize(vec12.transform(intents))
    title12 = normalize(vec12.transform([doc["title"] for doc in docs]))
    intent_cos = np.asarray((intent12 @ title12.T).todense(), dtype=np.float64)

    jd_latin = [latin_tokens(text) for text in jd_texts]
    jd_len = [len(text) for text in jd_texts]

    use_structured = variant != "title"   # 技能/年限/学历是否可用
    use_title = variant in ("full", "shuffled")

    X = np.zeros((n_res, n_jd, len(FEATURE_NAMES)), dtype=np.float64)
    for i, resume in enumerate(resumes):
        r_latin = resume["latin"]
        r_lower = resume["text_lower"]
        r_len = resume["length"]
        r_years = resume["years"]
        r_edu = resume["edu"]
        r_intent = resume["intent"]
        for j, doc in enumerate(docs):
            j_latin = jd_latin[j]
            union = r_latin | j_latin
            inter = r_latin & j_latin
            jaccard = len(inter) / len(union) if union else 0.0
            coverage = len(inter) / len(j_latin) if j_latin else 0.0

            skill_ratio = skill_count = 0.0
            years_diff = years_ok = edu_diff = 0.0
            if use_structured:
                skills = doc["skills"]
                hits = sum(1 for phrase in skills if phrase.lower() in r_lower)
                skill_count = float(hits)
                skill_ratio = hits / len(skills) if skills else 0.0
                if r_years is not None and doc["years"] is not None:
                    years_diff = float(r_years - doc["years"])
                    years_ok = 1.0 if r_years >= doc["years"] else 0.0
                if r_edu is not None and doc["edu"] is not None:
                    edu_diff = float(r_edu - doc["edu"])

            hit_title = 0.0
            title_cos = 0.0
            if use_title:
                title_cos = float(intent_cos[i, j])
                if r_intent and doc["title"] and (doc["title"] in r_intent
                                                  or r_intent in doc["title"]):
                    hit_title = 1.0

            X[i, j] = (
                cos24[i, j],
                cos12[i, j],
                jaccard,
                coverage,
                skill_ratio,
                skill_count,
                years_diff,
                years_ok,
                edu_diff,
                title_cos,
                hit_title,
                math.log1p(r_len),
                math.log1p(jd_len[j]),
                r_len / max(1, jd_len[j]),
            )
    return X


# --------------------------------------------------------------------- 指标
def rank_of_true(probs: np.ndarray, true_index: int) -> int:
    order = np.argsort(-probs)
    return int(np.where(order == true_index)[0][0]) + 1


def ranking_metrics(probs: np.ndarray, true_indices: list[int]) -> tuple[dict, list[int]]:
    ranks = [rank_of_true(probs[i], true) for i, true in enumerate(true_indices)]
    n = len(ranks)
    margins = []
    for i, true in enumerate(true_indices):
        others = np.delete(probs[i], true)
        margins.append(float(probs[i, true] - others.mean()))
    return {
        "n": n,
        "recall_at_1": sum(r <= 1 for r in ranks) / n,
        "recall_at_3": sum(r <= 3 for r in ranks) / n,
        "recall_at_5": sum(r <= 5 for r in ranks) / n,
        "mrr": sum(1.0 / r for r in ranks) / n,
        "mean_rank": statistics.fmean(ranks),
        "median_rank": statistics.median(ranks),
        "mean_margin": statistics.fmean(margins),
        "min_margin": min(margins),
        "p10_margin": float(np.percentile(margins, 10)),
    }, ranks


def bootstrap_diff(hits_a: list[int], hits_b: list[int], n_boot: int, seed: int) -> dict:
    """同一批简历上的配对 bootstrap（与 evaluate_pair.py 同口径）。"""
    rng = np.random.default_rng(seed)
    a = np.asarray(hits_a, dtype=np.float64)
    b = np.asarray(hits_b, dtype=np.float64)
    n = len(a)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        diffs[i] = a[idx].mean() - b[idx].mean()
    return {
        "mean": float(a.mean() - b.mean()),
        "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
        "p_two_sided": float(min(1.0, 2 * min((diffs <= 0).mean(), (diffs >= 0).mean()))),
        "n_boot": n_boot,
        "seed": seed,
    }


def hits_of(ranks: list[int]) -> list[int]:
    return [1 if rank <= 1 else 0 for rank in ranks]


# --------------------------------------------------------------------- 训练/打分
def fit_gbdt(X_pairs: np.ndarray, y: np.ndarray) -> HistGradientBoostingClassifier:
    clf = HistGradientBoostingClassifier(**GBDT_PARAMS)
    clf.fit(X_pairs, y)
    return clf


def score_matrix(clf: HistGradientBoostingClassifier, X: np.ndarray,
                 indices: list[int]) -> np.ndarray:
    sub = X[indices].reshape(len(indices) * X.shape[1], X.shape[2])
    probs = clf.predict_proba(sub)[:, 1]
    return probs.reshape(len(indices), X.shape[1])


def pair_labels(indices: list[int], resumes: list[dict], label2id: dict[str, int],
                n_jd: int) -> np.ndarray:
    labels = np.empty(len(indices) * n_jd, dtype=np.int8)
    cursor = 0
    for i in indices:
        true = label2id[resumes[i]["category"]]
        for j in range(n_jd):
            labels[cursor] = 1 if j == true else 0
            cursor += 1
    return labels


def per_class_table(indices: list[int], resumes: list[dict], ranks: list[int]) -> list[dict]:
    grouped: dict[str, list[int]] = {}
    for pos, i in enumerate(indices):
        grouped.setdefault(resumes[i]["category"], []).append(ranks[pos])
    return [
        {
            "category": code,
            "n": len(values),
            "recall_at_1": sum(r <= 1 for r in values) / len(values),
            "mean_rank": statistics.fmean(values),
        }
        for code, values in sorted(grouped.items())
    ]


def split_metrics(clf: HistGradientBoostingClassifier, X_model: np.ndarray,
                  cos_baseline: np.ndarray, indices: list[int],
                  resumes: list[dict], label2id: dict[str, int],
                  n_boot: int, seed: int) -> dict:
    true_indices = [label2id[resumes[i]["category"]] for i in indices]
    scores = score_matrix(clf, X_model, indices)
    model_metrics, ranks = ranking_metrics(scores, true_indices)
    base_metrics, base_ranks = ranking_metrics(cos_baseline[indices], true_indices)
    hits_model = hits_of(ranks)
    hits_base = hits_of(base_ranks)
    return {
        "n_examples": len(indices),
        "model": model_metrics,
        "tfidf_cosine": base_metrics,
        "bootstrap_model_minus_tfidf": bootstrap_diff(hits_model, hits_base, n_boot, seed),
        "per_class": per_class_table(indices, resumes, ranks),
        "_ranks": ranks,
        "_scores": scores,
        "_true_indices": true_indices,
    }


def clean(block: dict) -> dict:
    return {k: v for k, v in block.items() if not k.startswith("_")}


# --------------------------------------------------------------------- 主流程
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", default=None)
    parser.add_argument("--split", default=None)
    parser.add_argument("--jd", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--bootstrap-n", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    started = time.time()
    csv_path = resolve_path(args.csv, [PROJECT_ROOT / "data" / "resumes.csv",
                                       PROJECT_ROOT / "synth" / "resumes.csv"])
    split_path = resolve_path(args.split, [PROJECT_ROOT / "data" / "split.csv",
                                           PROJECT_ROOT / "synth" / "split.csv"])
    jd_path = resolve_path(args.jd, [PROJECT_ROOT / "jd" / "jobs_24.yaml"])
    out_dir = Path(args.out).expanduser().resolve() if args.out else PROJECT_ROOT / "gbdt"
    out_dir.mkdir(parents=True, exist_ok=True)

    resumes = load_resumes(csv_path)
    attach_splits(resumes, read_split(split_path))
    jd_docs = load_jobs(jd_path)

    codes = sorted(doc["code"] for doc in jd_docs)
    label2id = {code: i for i, code in enumerate(codes)}
    if len(codes) != len(jd_docs) or set(codes) != {doc["code"] for doc in jd_docs}:
        raise SystemExit("JD 类别有重复或缺失")
    jd_docs = sorted(jd_docs, key=lambda d: d["code"])
    n_jd = len(jd_docs)

    train_idx = [i for i, r in enumerate(resumes) if r["split"] == "train"]
    val_idx = [i for i, r in enumerate(resumes) if r["split"] == "val"]
    test_idx = [i for i, r in enumerate(resumes) if r["split"] == "test"]
    if not train_idx or not val_idx or not test_idx:
        raise SystemExit(f"空 split: train={len(train_idx)} val={len(val_idx)} "
                         f"test={len(test_idx)}")

    per_class: dict[str, dict[str, int]] = {}
    for item in resumes:
        bucket = per_class.setdefault(item["category"], {"train": 0, "val": 0, "test": 0})
        bucket[item["split"]] += 1
    missing_codes = set(codes) - set(per_class)
    if missing_codes:
        raise SystemExit(f"这些类别没有简历: {sorted(missing_codes)}")

    # 合成数据上限诊断：生成器把目标岗位名写进了简历（自我评价恒含 title，
    # 求职意向 85% 含 title），这决定了任务的难度上限。
    title_by_code = {doc["code"]: doc["title"] for doc in jd_docs}

    def title_diagnostics(indices: list[int]) -> dict:
        stats = {"n": len(indices), "contains_own_title": 0, "has_intent": 0,
                 "intent_matches_title": 0}
        for i in indices:
            item = resumes[i]
            title = title_by_code[item["category"]]
            if title and title in item["text"]:
                stats["contains_own_title"] += 1
            if item["intent"]:
                stats["has_intent"] += 1
                if title and (title in item["intent"] or item["intent"] in title):
                    stats["intent_matches_title"] += 1
        n = max(1, stats["n"])
        return {
            "n": stats["n"],
            "contains_own_title_frac": stats["contains_own_title"] / n,
            "has_intent_frac": stats["has_intent"] / n,
            "intent_matches_title_frac": stats["intent_matches_title"] / n,
        }

    all_idx = list(range(len(resumes)))
    title_leak = {"overall": title_diagnostics(all_idx),
                  "test": title_diagnostics(test_idx),
                  "note": ("生成器让每份简历的自我评价恒含目标岗位名，求职意向约 86% 含目标岗位名；"
                           "因此仅凭岗位名即可 24 选 1，指标必然饱和。")}

    print("== 数据 ==")
    print(f"总简历 {len(resumes)}  train={len(train_idx)} val={len(val_idx)} "
          f"test={len(test_idx)}  类别数={len(codes)}")
    sizes = [sum(v.values()) for v in per_class.values()]
    print(f"每类样本数 {min(sizes)}–{max(sizes)}  训练 pair={len(train_idx) * n_jd}")
    print(f"合成上限诊断: 简历含自身岗位名 {title_leak['overall']['contains_own_title_frac']:.1%}，"
          f"有求职意向 {title_leak['overall']['has_intent_frac']:.1%}，"
          f"意向匹配岗位名 {title_leak['overall']['intent_matches_title_frac']:.1%}")
    print(f"简历: {csv_path}")
    print(f"划分: {split_path}")
    print(f"JD  : {jd_path}")

    train_texts = [resumes[i]["text"] for i in train_idx]
    print("\n== 构建特征（TF-IDF 只在 train 简历 + 全部 JD 上 fit）==")
    t0 = time.time()
    X_full = build_features(resumes, jd_docs, "full", train_texts)
    print(f"full 特征 {X_full.shape}  {time.time() - t0:.1f}s")
    X_title = build_features(resumes, jd_docs, "title", train_texts)
    print(f"title-only 特征 {X_title.shape}")
    X_body = build_features(resumes, jd_docs, "body", train_texts)
    print(f"body-only 特征 {X_body.shape}")
    shuffled_docs = jd_docs[1:] + jd_docs[:1]   # 与 evaluate_pair.py 同向整体右移一位
    # 列 j 对应原 jd_docs[(j+1) % 24]，真实类别索引保持不变
    X_shuffled = build_features(resumes, shuffled_docs, "shuffled", train_texts)
    print(f"shuffled-JD 特征 {X_shuffled.shape}")

    # TF-IDF 余弦基线（char 2-4 gram，与特征 1 同一配置；只在 train 简历 + 全部 JD 上 fit）
    jd_full_texts = variant_jd_texts(jd_docs, "full")
    base_vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 4),
                               sublinear_tf=True, min_df=2)
    base_vec.fit(train_texts + jd_full_texts)
    base_res = normalize(base_vec.transform([r["text"] for r in resumes]))
    base_jd = normalize(base_vec.transform(jd_full_texts))
    cos24_baseline = np.asarray((base_res @ base_jd.T).todense(), dtype=np.float64)

    # 词级 TF-IDF 基线仅作参考（中文未分词，预期偏弱），不参与 bootstrap
    word_vec = TfidfVectorizer(sublinear_tf=True, min_df=2, ngram_range=(1, 2))
    word_vec.fit(train_texts + jd_full_texts)
    word_res = normalize(word_vec.transform([r["text"] for r in resumes]))
    word_jd = normalize(word_vec.transform(jd_full_texts))
    cos_word = np.asarray((word_res @ word_jd.T).todense(), dtype=np.float64)

    # ---- 训练
    print("\n== 训练 GBDT ==")
    y_train = pair_labels(train_idx, resumes, label2id, n_jd)
    print(f"train pairs={len(y_train)} 正样本={int(y_train.sum())} "
          f"负样本={int(len(y_train) - y_train.sum())}")

    t0 = time.time()
    clf_full = fit_gbdt(X_full[train_idx].reshape(-1, len(FEATURE_NAMES)), y_train)
    fit_seconds_full = time.time() - t0
    print(f"full 模型 {fit_seconds_full:.1f}s")

    val_block = split_metrics(clf_full, X_full, cos24_baseline, val_idx, resumes,
                              label2id, args.bootstrap_n, args.seed)
    test_block = split_metrics(clf_full, X_full, cos24_baseline, test_idx, resumes,
                               label2id, args.bootstrap_n, args.seed)
    word_val, _ = ranking_metrics(cos_word[val_idx],
                                  [label2id[resumes[i]["category"]] for i in val_idx])
    word_test, _ = ranking_metrics(cos_word[test_idx],
                                   [label2id[resumes[i]["category"]] for i in test_idx])

    # ---- 证伪 1/2：重新训练
    print("\n== 证伪：只留标题 / 只留正文（各自重新训练）==")
    t0 = time.time()
    clf_title = fit_gbdt(X_title[train_idx].reshape(-1, len(FEATURE_NAMES)), y_train)
    print(f"title-only 模型 {time.time() - t0:.1f}s")
    t0 = time.time()
    clf_body = fit_gbdt(X_body[train_idx].reshape(-1, len(FEATURE_NAMES)), y_train)
    print(f"body-only 模型 {time.time() - t0:.1f}s")

    def fals_metrics(clf, X, indices):
        true_indices = [label2id[resumes[i]["category"]] for i in indices]
        scores = score_matrix(clf, X, indices)
        metrics, ranks = ranking_metrics(scores, true_indices)
        return metrics, ranks

    title_val, title_val_ranks = fals_metrics(clf_title, X_title, val_idx)
    title_test, title_test_ranks = fals_metrics(clf_title, X_title, test_idx)
    body_val, body_val_ranks = fals_metrics(clf_body, X_body, val_idx)
    body_test, body_test_ranks = fals_metrics(clf_body, X_body, test_idx)

    # ---- 证伪 3：完整模型 + JD 打乱
    shuffled_val, shuffled_val_ranks = fals_metrics(clf_full, X_shuffled, val_idx)
    shuffled_test, shuffled_test_ranks = fals_metrics(clf_full, X_shuffled, test_idx)

    full_val_ranks = val_block["_ranks"]
    full_test_ranks = test_block["_ranks"]

    falsification = {
        "note": ("title_only/body_only 都是重新训练的独立模型；title 变体把技能/年限/学历"
                 "三类 JD 结构化特征置 0，body 变体把标题类特征置 0。"
                 "shuffled 用完整模型，评测时 JD 列整体循环右移一位：真实类别的 JD 落到"
                 "相邻列，指标仍按原列判定，故 Recall@1 不高于随机水平 1/24=0.0417"
                 "（实测为 0 属正常），mean_rank 应接近 12.5。"),
        "test": {
            "title_only_jd": title_test,
            "body_only_jd": body_test,
            "shuffled_jd": shuffled_test,
        },
        "val": {
            "title_only_jd": title_val,
            "body_only_jd": body_val,
            "shuffled_jd": shuffled_val,
        },
    }

    ablation_diff = {
        "test": {
            "full_minus_title": bootstrap_diff(hits_of(full_test_ranks),
                                               hits_of(title_test_ranks),
                                               args.bootstrap_n, args.seed),
            "full_minus_body": bootstrap_diff(hits_of(full_test_ranks),
                                              hits_of(body_test_ranks),
                                              args.bootstrap_n, args.seed),
            "title_minus_body": bootstrap_diff(hits_of(title_test_ranks),
                                               hits_of(body_test_ranks),
                                               args.bootstrap_n, args.seed),
        },
        "val": {
            "full_minus_title": bootstrap_diff(hits_of(full_val_ranks),
                                               hits_of(title_val_ranks),
                                               args.bootstrap_n, args.seed),
            "full_minus_body": bootstrap_diff(hits_of(full_val_ranks),
                                              hits_of(body_val_ranks),
                                              args.bootstrap_n, args.seed),
            "title_minus_body": bootstrap_diff(hits_of(title_val_ranks),
                                               hits_of(body_val_ranks),
                                               args.bootstrap_n, args.seed),
        },
        "note": "同一批样本上的配对 bootstrap，避免拿两个独立读数直接相减。",
    }

    import sklearn

    report = {
        "data": {
            "source": "全合成简历（JD 模板生成，非真人数据）",
            "csv": str(csv_path),
            "split": str(split_path),
            "jd": str(jd_path),
            "n_total": len(resumes),
            "n_train": len(train_idx),
            "n_val": len(val_idx),
            "n_test": len(test_idx),
            "n_classes": len(codes),
            "n_train_pairs": int(len(train_idx) * n_jd),
            "n_negative_per_positive": n_jd - 1,
            "per_class_counts": per_class,
            "per_class_min": min(sizes),
            "per_class_max": max(sizes),
            "title_leak_diagnostics": title_leak,
        },
        "config": {
            "task": "24-choose-1 ranking",
            "model": "sklearn.ensemble.HistGradientBoostingClassifier",
            "gbdt_params": {k: (v if not isinstance(v, np.generic) else v.item())
                            for k, v in GBDT_PARAMS.items()},
            "feature_names": FEATURE_NAMES,
            "tfidf_baseline": {
                "analyzer": "char", "ngram_range": [2, 4],
                "sublinear_tf": True, "min_df": 2,
                "fit_on": "train 简历 + 全部 JD（测试集不参与 fit）",
            },
            "tfidf_word_baseline": {
                "analyzer": "word(默认)", "ngram_range": [1, 2],
                "sublinear_tf": True, "min_df": 2,
                "note": "中文未分词，仅作参考，不参与 bootstrap。",
            },
            "bootstrap_n": args.bootstrap_n,
            "seed": args.seed,
            "fit_seconds_full": round(fit_seconds_full, 2),
            "environment": {"python": sys.version.split()[0],
                            "sklearn": sklearn.__version__,
                            "numpy": np.__version__},
        },
        "val": clean(val_block) | {"tfidf_word_cosine": word_val},
        "test": clean(test_block) | {"tfidf_word_cosine": word_test},
        "falsification": falsification,
        "ablation_diff": ablation_diff,
        "per_class": test_block["per_class"],
        "caveat": ("合成简历由 JD 模板生成：每份简历的自我评价恒含目标岗位名、"
                   "约 86% 的求职意向含目标岗位名、技能词与职责句在简历与 JD 之间逐字重合。"
                   "因此指标是合成数据上的上限，不代表真实简历场景的泛化性能；"
                   "shuffled_jd 塌到随机水平说明排序能力来自模板/岗位名词面重叠，"
                   "而不是对真实简历的语义理解。"),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    # numpy 标量转原生类型
    report = json.loads(json.dumps(report, ensure_ascii=False, default=json_default))

    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- predictions.csv（test 集）
    pred_path = out_dir / "predictions.csv"
    with pred_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "true_category", "top1", "rank", "prob_true", "prob_top1"])
        scores = test_block["_scores"]
        for pos, i in enumerate(test_idx):
            top = int(np.argmax(scores[pos]))
            writer.writerow([
                resumes[i]["id"], resumes[i]["category"], codes[top],
                test_block["_ranks"][pos],
                f"{scores[pos, test_block['_true_indices'][pos]]:.6f}",
                f"{scores[pos, top]:.6f}",
            ])
    val_pred_path = out_dir / "val_predictions.csv"
    with val_pred_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "true_category", "top1", "rank", "prob_true", "prob_top1"])
        scores = val_block["_scores"]
        for pos, i in enumerate(val_idx):
            top = int(np.argmax(scores[pos]))
            writer.writerow([
                resumes[i]["id"], resumes[i]["category"], codes[top],
                val_block["_ranks"][pos],
                f"{scores[pos, val_block['_true_indices'][pos]]:.6f}",
                f"{scores[pos, top]:.6f}",
            ])

    # ---- 控制台摘要
    def line(name, m):
        return (f"{name:<12} R@1={m['recall_at_1']:.4f} @3={m['recall_at_3']:.4f} "
                f"@5={m['recall_at_5']:.4f} MRR={m['mrr']:.4f} "
                f"平均名次={m['mean_rank']:.2f} 中位={m['median_rank']}")

    print("\n" + "=" * 78)
    for which, block, word in (("val", val_block, word_val), ("test", test_block, word_test)):
        diff = block["bootstrap_model_minus_tfidf"]
        print(f"\n== {which} 集（{block['n_examples']} 条，24 选 1）==")
        print(line("GBDT 完整", block["model"]))
        print(line("TF-IDF char", block["tfidf_cosine"]))
        print(line("TF-IDF word", word))
        print(f"差值 GBDT−TF-IDF(char) {diff['mean']:+.4f} "
              f"95%CI [{diff['ci95'][0]:+.4f}, {diff['ci95'][1]:+.4f}] "
              f"p={diff['p_two_sided']:.4f}")
        print(f"margin 均值={block['model']['mean_margin']:+.4f} "
              f"最小={block['model']['min_margin']:+.4f} "
              f"p10={block['model']['p10_margin']:+.4f}")

    print("\n== 证伪（test）==")
    print(line("只留标题", title_test))
    print(line("只留正文", body_test))
    print(line("JD 打乱", shuffled_test))
    print(f"随机水平 1/24 = {1 / 24:.4f}")
    for name, label in (("full_minus_title", "完整−只留标题"),
                        ("full_minus_body", "完整−只留正文"),
                        ("title_minus_body", "只留标题−只留正文")):
        diff = ablation_diff["test"][name]
        print(f"消融 {label} {diff['mean']:+.4f} "
              f"95%CI [{diff['ci95'][0]:+.4f}, {diff['ci95'][1]:+.4f}] "
              f"p={diff['p_two_sided']:.4f}")

    weak = [row for row in test_block["per_class"] if row["recall_at_1"] < 1.0]
    if weak:
        print("\n== test 弱类（R@1 < 1.0）==")
        for row in weak:
            print(f"{row['category']:<26} n={row['n']:<2} "
                  f"R@1={row['recall_at_1']:.2f} 平均名次={row['mean_rank']:.2f}")
    else:
        print("\ntest 所有类别 R@1 = 1.0")

    print(f"\n产物目录 {out_dir}")
    print(f"  metrics.json / predictions.csv / val_predictions.csv")
    print(f"总耗时 {report['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
