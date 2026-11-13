"""数据层：读取 CSV / 标签、字段拼装、数值特征、分组分层切分、岗位表与伪 JD。

输入约定（与 resume_html 目录下的产物一致）：
  resumes.csv           上一轮抽取的宽表，主键 resume_id
  tag.csv               无表头或有表头，两列 resume_id,label；可选第 3 列 0-100 分数
  resume_experiences.csv 可选，用于估算工作年限
  structure_groups.csv   可选，content_duplicate=yes 的样本强制留在训练集
  jobs.csv               可选，job_id,label,title,jd_text,required_skills
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from .config import Config, NUMERIC_NAMES
from .text import FIELD_ORDER, Vocab, fields_from_raw_text, normalize, tokenize, vectorize_fields
from .utils import get_logger, stable_hash

LOG = get_logger()


# --------------------------------------------------------------------------- #
# 基础读取
# --------------------------------------------------------------------------- #
def load_tags(path: str | Path) -> dict[str, tuple[str, float | None]]:
    """返回 {resume_id: (岗位标签, 可选人工分数)}。兼容无表头 + 标签前后空格。"""
    out: dict[str, tuple[str, float | None]] = {}
    with open(path, encoding="utf-8-sig", newline="") as fp:
        for row in csv.reader(fp):
            if len(row) < 2 or not row[0].strip():
                continue
            rid = row[0].strip()
            if not rid.isdigit():        # 表头
                continue
            label = row[1].strip().upper().replace("_", "-")
            score = None
            if len(row) >= 3 and row[2].strip():
                try:
                    score = float(row[2])
                except ValueError:
                    score = None
            if label:
                out[rid] = (label, score)
    return out


def load_resumes(path: str | Path) -> dict[str, dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as fp:
        return {r["resume_id"]: r for r in csv.DictReader(fp)}


def load_years(path: str | Path | None, current_year: int = 2026) -> dict[str, float]:
    """按工作经历的起止年份合并区间，估算总工作年限。文件不存在则全 0。"""
    if not path or not Path(path).exists():
        return {}
    spans: dict[str, list[tuple[int, int]]] = defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as fp:
        rd = csv.DictReader(fp)
        cols = rd.fieldnames or []
        sc = next((c for c in cols if "start_year" in c), None)
        ec = next((c for c in cols if "end_year" in c), None)
        ed = next((c for c in cols if "end_date" in c), None)
        if not sc:
            return {}
        for r in rd:
            try:
                s = int(float(r.get(sc) or 0))
            except ValueError:
                continue
            e = None
            if ec:
                try:
                    e = int(float(r.get(ec) or 0)) or None
                except ValueError:
                    e = None
            if not e and ed and re.search(r"current|present", r.get(ed, ""), re.I):
                e = current_year
            e = e or s
            if 1950 <= s <= current_year + 1:
                e = min(max(e, s), current_year + 1)
                spans[r["resume_id"]].append((s, e))
    out: dict[str, float] = {}
    for rid, segs in spans.items():
        segs.sort()
        merged: list[list[int]] = []
        for s, e in segs:
            if merged and s <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        out[rid] = float(sum(e - s + 1 for s, e in merged))
    return out


def load_duplicate_flags(path: str | Path | None) -> set[str]:
    """content_duplicate=yes 的样本统一放进训练集，避免近重复样本跨集合泄漏。"""
    if not path or not Path(path).exists():
        return set()
    out: set[str] = set()
    with open(path, encoding="utf-8-sig", newline="") as fp:
        for r in csv.DictReader(fp):
            if (r.get("content_duplicate") or "").strip().lower() in ("yes", "true", "1"):
                m = re.search(r"(\d+)\.html", r.get("file", ""))
                if m:
                    out.add(m.group(1))
    return out


# --------------------------------------------------------------------------- #
# 记录
# --------------------------------------------------------------------------- #
@dataclass
class Job:
    job_id: int
    label: str
    title: str
    jd_text: str
    required_skills: str = ""
    n_train: int = 0


@dataclass
class ResumeRecord:
    rid: str
    file: str
    name: str
    summary: str
    skills: str
    label: str
    score: float | None
    fields: list[tuple[str, str]]
    numeric_raw: np.ndarray
    group: str


def _float(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except ValueError:
        return 0.0


def build_fields(row: dict[str, str]) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for name in FIELD_ORDER:
        if name == "other_sections":
            raw = (row.get("other_sections_json") or "").strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                text = " | ".join(str(v) for v in obj.values()) if isinstance(obj, dict) else str(obj)
            except (ValueError, TypeError):
                text = raw
            if text.strip():
                fields.append((name, text))
            continue
        text = (row.get(name) or "").strip()
        if text:
            fields.append((name, text))
    return fields


def build_numeric(row: dict[str, str], years: float) -> np.ndarray:
    skill_terms = len([s for s in re.split(r"[,|]", row.get("skills", "")) if s.strip()])
    vals = [
        math.log1p(_float(row, "n_experiences")),
        math.log1p(_float(row, "n_education")),
        math.log1p(_float(row, "n_sections")),
        math.log1p(_float(row, "n_items")),
        math.log1p(max(0.0, _float(row, "text_chars"))),
        math.log1p(max(0.0, years)),
        math.log1p(skill_terms),
        1.0 if (row.get("summary") or "").strip() else 0.0,
    ]
    return np.asarray(vals, dtype=np.float32)


def _group_key(fields: Sequence[tuple[str, str]]) -> str:
    text = " ".join(t for _, t in fields)
    words = tokenize(text)
    return stable_hash(" ".join(sorted(set(words)))) if words else stable_hash(normalize(text))


def stratified_group_split(records: Sequence[ResumeRecord], cfg: Config,
                           force_train: set[str]) -> dict[str, list[int]]:
    """按岗位分层 + 组内不拆分（内容相同的简历只能落在同一个集合）。"""
    rng = np.random.default_rng(cfg.seed)
    idx_by_label: dict[str, list[int]] = defaultdict(list)
    group_of: dict[int, str] = {}
    for i, r in enumerate(records):
        idx_by_label[r.label].append(i)
        group_of[i] = r.group

    splits: dict[str, list[int]] = {"train": [], "val": [], "test": []}
    forced = [i for i, r in enumerate(records) if r.rid in force_train]
    splits["train"].extend(forced)
    forced_set = set(forced)

    for label, idxs in idx_by_label.items():
        groups: dict[str, list[int]] = defaultdict(list)
        for i in idxs:
            if i not in forced_set:
                groups[group_of[i]].append(i)
        keys = list(groups.keys())
        rng.shuffle(keys)
        n_total = sum(len(groups[k]) for k in keys)
        n_train = max(1, int(round(n_total * cfg.train_ratio)))
        n_val = max(1, int(round(n_total * cfg.val_ratio)))
        c_train = sum(1 for i in idxs if i in forced_set)
        c_val = 0
        for k in keys:
            if c_train < n_train:
                splits["train"].extend(groups[k]); c_train += len(groups[k])
            elif c_val < n_val:
                splits["val"].extend(groups[k]); c_val += len(groups[k])
            else:
                splits["test"].extend(groups[k])
    for k in splits:
        splits[k] = sorted(splits[k])
    return splits


# --------------------------------------------------------------------------- #
# 岗位表 / 伪 JD
# --------------------------------------------------------------------------- #
def _pretty(label: str) -> str:
    return " ".join(w.capitalize() for w in label.replace("-", " ").split())


def _doc_tfidf(fields: Sequence[tuple[str, str]], vocab: Vocab,
               budgets: dict[str, int]) -> dict[str, float]:
    words = tokenize(" ".join(t[:budgets.get(n, 200)] for n, t in fields))
    tf: dict[str, int] = defaultdict(int)
    for w in words:
        tf[w if w in vocab.stoi else Vocab.UNK] += 1
    if vocab.use_bigrams:
        for a, b in zip(words, words[1:]):
            k = f"bi:{a}_{b}"
            if k in vocab.stoi:
                tf[k] += 1
    vec = {w: (1 + math.log(c)) * vocab.idf.get(w, 1.0) for w, c in tf.items()}
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {w: v / norm for w, v in vec.items()}


def build_pseudo_jd(train_records: Sequence[ResumeRecord], vocab: Vocab,
                    labels: Sequence[str], cfg: Config, top_terms: int = 35) -> dict[str, str]:
    """没有真实 JD 时，用「类内平均 tf-idf - 全局平均 tf-idf」挑出每个岗位最具判别力的词，
    拼成一份伪岗位描述。这样岗位塔从一开始就不是纯黑盒 id 查表，
    推理时换成真实 JD 文本也能落到同一个语义空间。"""
    cls_sum: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    all_sum: dict[str, float] = defaultdict(float)
    cnt: dict[str, int] = defaultdict(int)
    n_all = 0
    for r in train_records:
        vec = _doc_tfidf(r.fields, vocab, cfg.field_budgets)
        cnt[r.label] += 1
        n_all += 1
        for w, v in vec.items():
            cls_sum[r.label][w] += v
            all_sum[w] += v
    out: dict[str, str] = {}
    for label in labels:
        n = max(1, cnt[label])
        scored = [
            (v / n - all_sum[w] / max(1, n_all), w)
            for w, v in cls_sum[label].items()
            if w not in (Vocab.UNK, Vocab.PAD)
        ]
        scored.sort(reverse=True)
        terms = []
        for _, w in scored[:top_terms]:
            terms.append(w[3:].replace("_", " ") if w.startswith("bi:") else w)
        head = label.replace("-", " ").lower()
        out[label] = " ".join([head, head] + terms)
    return out


def load_jobs_csv(path: str | Path | None, jobs: list[Job],
                  label2id: dict[str, int]) -> list[Job]:
    """可选：覆盖已有岗位 JD，或追加新岗位（新岗位无训练标签，靠文本编码打分）。"""
    if not path or not Path(path).exists():
        return jobs
    with open(path, encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            label = (row.get("label") or row.get("category") or "").strip().upper().replace("_", "-")
            jd = (row.get("jd_text") or row.get("description") or "").strip()
            title = (row.get("title") or row.get("job_title") or "").strip()
            skills = (row.get("required_skills") or "").strip()
            if label and label in label2id:
                j = jobs[label2id[label]]
                if jd:
                    j.jd_text = jd
                if title:
                    j.title = title
                if skills:
                    j.required_skills = skills
            elif label or jd:
                label = label or f"NEW-{len(jobs)}"
                label2id[label] = len(jobs)
                jobs.append(Job(len(jobs), label, title or _pretty(label), jd, skills, 0))
    return jobs


def job_text_arrays(jobs: Sequence[Job], vocab: Vocab, cfg: Config
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    budgets = {n: 100000 for n in FIELD_ORDER}
    triplets = []
    for j in jobs:
        fields = [("header_text", j.title + " " + j.label.replace("-", " ")),
                  ("skills", j.jd_text + " " + j.required_skills),
                  ("summary", j.title)]
        triplets.append(vectorize_fields(fields, vocab, budgets=budgets,
                                         max_len=cfg.max_job_len,
                                         use_bigrams=cfg.use_bigrams))
    return (np.stack([t[0] for t in triplets]),
            np.stack([t[1] for t in triplets]),
            np.stack([t[2] for t in triplets]))


# --------------------------------------------------------------------------- #
# 语料
# --------------------------------------------------------------------------- #
class Corpus:
    """一次构建，训练/评估/推理共用；可随 checkpoint 一起序列化关键产物。"""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.records: list[ResumeRecord] = []
        self.vocab = Vocab()
        self.label2id: dict[str, int] = {}
        self.id2label: list[str] = []
        self.jobs: list[Job] = []
        self.splits: dict[str, list[int]] = {"train": [], "val": [], "test": []}
        self.num_mean = np.zeros(len(NUMERIC_NAMES), dtype=np.float32)
        self.num_std = np.ones(len(NUMERIC_NAMES), dtype=np.float32)
        self.X_ids = np.zeros((0, cfg.max_len), dtype=np.int64)
        self.X_w = np.zeros((0, cfg.max_len), dtype=np.float32)
        self.X_seg = np.zeros((0, cfg.max_len), dtype=np.int64)
        self.X_num = np.zeros((0, len(NUMERIC_NAMES)), dtype=np.float32)
        self.job_arrays: tuple[np.ndarray, np.ndarray, np.ndarray] = (
            np.zeros((0, cfg.max_job_len), dtype=np.int64),
            np.zeros((0, cfg.max_job_len), dtype=np.float32),
            np.zeros((0, cfg.max_job_len), dtype=np.int64),
        )

    @property
    def n_jobs(self) -> int:
        return len(self.jobs)

    @property
    def label_array(self) -> np.ndarray:
        return np.asarray([self.label2id[r.label] for r in self.records], dtype=np.int64)

    @classmethod
    def build(cls, cfg: Config, data_dir: str | Path | None = None) -> "Corpus":
        dd = Path(data_dir or cfg.data_dir)
        tags = load_tags(dd / cfg.tag_file)
        rows = load_resumes(dd / cfg.resume_file)
        if not tags or not rows:
            raise FileNotFoundError(f"未找到标签或简历表：{dd / cfg.tag_file} / {dd / cfg.resume_file}")
        years = load_years(dd / cfg.experience_file if cfg.experience_file else None)
        dup_flags = load_duplicate_flags(dd / cfg.structure_file if cfg.structure_file else None)

        common = sorted(set(tags) & set(rows), key=lambda x: int(x))
        if cfg.max_samples and cfg.max_samples < len(common):
            common = _round_robin(common, tags, cfg.max_samples)
        LOG.info("载入 %d 份简历 / %d 个岗位类别，数据目录 %s", len(common),
                 len({tags[r][0] for r in common}), dd)

        c = cls(cfg)
        c.id2label = sorted({tags[r][0] for r in common})
        c.label2id = {l: i for i, l in enumerate(c.id2label)}
        for rid in common:
            row = rows[rid]
            label, score = tags[rid]
            flds = build_fields(row)
            c.records.append(ResumeRecord(
                rid=rid, file=row.get("file", f"resume{rid}.html"),
                name=row.get("name", ""), summary=row.get("summary", ""),
                skills=row.get("skills", ""), label=label, score=score,
                fields=flds,
                numeric_raw=build_numeric(row, years.get(rid, 0.0)),
                group=_group_key(flds),
            ))
        c.splits = stratified_group_split(c.records, cfg, dup_flags)
        LOG.info("切分 train/val/test = %d/%d/%d（同组不跨集合）",
                 len(c.splits["train"]), len(c.splits["val"]), len(c.splits["test"]))

        # 只在训练集拟合词表 / idf / 数值标准化
        train_docs = [tokenize(" ".join(t[:cfg.field_budgets.get(n, 200)] for n, t in c.records[i].fields))
                      for i in c.splits["train"]]
        c.vocab = Vocab.build(train_docs, min_df=cfg.min_df, max_vocab=cfg.max_vocab,
                              use_bigrams=cfg.use_bigrams)
        raw = np.stack([r.numeric_raw for r in c.records])
        c.num_mean = raw[c.splits["train"]].mean(0) if len(c.splits["train"]) else raw.mean(0)
        c.num_std = np.maximum(raw[c.splits["train"]].std(0) if len(c.splits["train"]) else raw.std(0), 1e-3)
        c.X_num = ((raw - c.num_mean) / c.num_std).astype(np.float32)

        triplets = [vectorize_fields(r.fields, c.vocab, budgets=cfg.field_budgets,
                                     max_len=cfg.max_len, use_bigrams=cfg.use_bigrams)
                    for r in c.records]
        c.X_ids = np.stack([t[0] for t in triplets])
        c.X_w = np.stack([t[1] for t in triplets])
        c.X_seg = np.stack([t[2] for t in triplets])

        pseudo = build_pseudo_jd([c.records[i] for i in c.splits["train"]],
                                 c.vocab, c.id2label, cfg)
        n_train = defaultdict(int)
        for i in c.splits["train"]:
            n_train[c.records[i].label] += 1
        c.jobs = [Job(i, l, _pretty(l), pseudo.get(l, l), "", n_train[l])
                  for i, l in enumerate(c.id2label)]
        c.jobs = load_jobs_csv(dd / cfg.jobs_file if cfg.jobs_file else None,
                               c.jobs, c.label2id)
        c.job_arrays = job_text_arrays(c.jobs, c.vocab, cfg)
        LOG.info("词表 %d，岗位 %d，特征矩阵 %s", len(c.vocab), c.n_jobs, c.X_ids.shape)
        return c

    def index_by_rid(self) -> dict[str, int]:
        return {r.rid: i for i, r in enumerate(self.records)}

    def meta(self) -> list[dict[str, Any]]:
        return [{"rid": r.rid, "file": r.file, "name": r.name[:120],
                 "summary": r.summary[:200], "skills": r.skills[:200],
                 "label": r.label} for r in self.records]

    def encode_raw_resume(self, text: str | dict[str, str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """推理时把一份全新简历编码成模型输入（使用训练好的词表与标准化参数）。"""
        if isinstance(text, dict):
            fields = [(k, v) for k, v in text.items() if v]
            row = dict(text)
        else:
            fields = fields_from_raw_text(text)
            row = {"skills": "", "summary": text, "n_items": "0", "n_sections": "0",
                   "n_experiences": "0", "n_education": "0", "text_chars": str(len(text))}
        ids, w, seg = vectorize_fields(fields, self.vocab, budgets=self.cfg.field_budgets,
                                       max_len=self.cfg.max_len,
                                       use_bigrams=self.cfg.use_bigrams)
        num = ((build_numeric(row, 0.0) - self.num_mean) / self.num_std).astype(np.float32)
        return (ids[None, :], w[None, :], seg[None, :], num[None, :])

    def summary(self) -> dict[str, Any]:
        return {"n_resumes": len(self.records), "n_jobs": self.n_jobs,
                "n_vocab": len(self.vocab),
                "splits": {k: len(v) for k, v in self.splits.items()},
                "labels": [{"label": j.label, "n_train": j.n_train, "title": j.title}
                           for j in self.jobs]}


def _round_robin(ids: Sequence[str], tags: dict[str, tuple[str, float | None]], n: int) -> list[str]:
    """调试用小样本：按类别轮询抽样，保证 24 类都出现。"""
    buckets: dict[str, list[str]] = defaultdict(list)
    for rid in ids:
        buckets[tags[rid][0]].append(rid)
    keys = sorted(buckets)
    out: list[str] = []
    i = 0
    while len(out) < n:
        added = False
        for k in keys:
            if i < len(buckets[k]):
                out.append(buckets[k][i]); added = True
                if len(out) >= n:
                    break
        if not added:
            break
        i += 1
    return out
