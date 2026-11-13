"""推理 / 业务 API：两个方向共用一个模型、同一把分数尺子。

    p = JobFitPredictor("outputs/jobfit.ckpt")
    p.rank_jobs_for_resume(resume_id=3, top_k=5)                 # 一人多岗
    p.rank_resumes_for_job("INFORMATION-TECHNOLOGY", top_x=10)   # 一岗多人

分数说明
  score              0-100 主分，默认 spread 模式：100*clip((z-z_lo)/(z_hi-z_lo))，
                     z=logit/T，锚点取验证集分位数；非饱和、跨查询可比
  match_probability  100*sigmoid(a*z+b)，校准后的匹配概率×100（强匹配会接近 100）
  job_share          一人多岗时该岗位在候选岗位集合中的置信度占比（同一行合计 100）
  percentile         本次查询候选池内的相对百分位（0-100）
  evidence           字段消融得到的分数贡献 + 与岗位描述重合的关键词，用于解释打分
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import torch

from .calibrate import Calibrator, percentile_scores
from .config import Config
from .data import Job, build_numeric, job_text_arrays, load_years  # noqa: F401
from .model import JobFitModel
from .text import (FIELD_ORDER, N_SEGMENTS, Vocab, fields_from_raw_text,
                   tokenize, vectorize_fields)
from .utils import chunks, get_device, get_logger

LOG = get_logger()
ID2SEG = {0: "padding", **{i + 1: n for i, n in enumerate(FIELD_ORDER)}}


@dataclass
class JobMatch:
    rank: int
    job_id: int
    label: str
    title: str
    score: float
    match_probability: float
    job_share: float
    percentile: float
    raw_logit: float
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("score", "match_probability", "job_share", "percentile", "raw_logit"):
            d[k] = round(float(d[k]), 2)
        return d


@dataclass
class CandidateMatch:
    rank: int
    resume_id: str
    file: str
    name: str
    true_label: str
    score: float
    match_probability: float
    percentile: float
    raw_logit: float
    summary: str
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("score", "match_probability", "percentile", "raw_logit"):
            d[k] = round(float(d[k]), 2)
        return d


def write_csv(records: Iterable[dict[str, Any]], path: str | Path) -> None:
    records = list(records)
    if not records:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(records[0].keys()))
        w.writeheader()
        w.writerows(records)


class JobFitPredictor:
    """checkpoint 自包含：加载后无需原始 HTML/CSV 即可对库内 2484 份简历打分。"""

    def __init__(self, ckpt_path: str | Path, device: str = "auto") -> None:
        self.device = get_device(device)
        d = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        self.cfg = Config.from_dict(d["cfg"])
        self.vocab = Vocab.from_dict(d["vocab"])
        self.jobs = [Job(**j) for j in d["jobs"]]
        self.label2id: dict[str, int] = d["label2id"]
        self.id2label: list[str] = d["id2label"]
        self.calib = Calibrator.from_dict(d["calibrator"])
        self.meta: list[dict[str, Any]] = d["meta"]
        self.rid2row = {m["rid"]: i for i, m in enumerate(self.meta)}
        self.splits = d.get("splits", {})
        self.metrics = d.get("metrics", {})
        self.X_ids = np.asarray(d["X_ids"])
        self.X_w = np.asarray(d["X_w"])
        self.X_seg = np.asarray(d["X_seg"])
        self.X_num = np.asarray(d["X_num"])
        self.num_mean = np.asarray(d["num_mean"], dtype=np.float32)
        self.num_std = np.asarray(d["num_std"], dtype=np.float32)

        self.model = JobFitModel(self.cfg, len(self.vocab), len(self.jobs),
                                 len(d["numeric_names"]), d.get("n_segments", N_SEGMENTS))
        self.model.set_job_text(job_text_arrays(self.jobs, self.vocab, self.cfg))
        self.model.load_state_dict(d["model"])
        self.model.to(self.device).eval()

    # ------------------------------------------------------------------ #
    # 底层编码
    # ------------------------------------------------------------------ #
    def _rows_arrays(self, rows: Sequence[int]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        r = np.asarray(rows, dtype=np.int64)
        return self.X_ids[r], self.X_w[r], self.X_seg[r], self.X_num[r]

    def encode_raw(self, text: str | dict[str, str]
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """全新简历（不在库内）编码成 1×L 的四组数组。"""
        if isinstance(text, dict):
            fields = [(k, str(v)) for k, v in text.items() if v]
            row = dict(text)
        else:
            fields = fields_from_raw_text(text)
            row = {"skills": "", "summary": str(text), "text_chars": str(len(str(text)))}
        ids, w, seg = vectorize_fields(fields, self.vocab, budgets=self.cfg.field_budgets,
                                       max_len=self.cfg.max_len,
                                       use_bigrams=self.cfg.use_bigrams)
        num = ((build_numeric(row, 0.0) - self.num_mean) / self.num_std).astype(np.float32)
        return ids[None, :], w[None, :], seg[None, :], num[None, :]

    def _jd_tensors(self, title: str, jd_text: str, skills: str = "") -> tuple[torch.Tensor, ...]:
        budgets = {n: 100000 for n in FIELD_ORDER}
        fields = [("header_text", title), ("skills", jd_text + " " + skills),
                  ("summary", title)]
        ids, w, seg = vectorize_fields(fields, self.vocab, budgets=budgets,
                                       max_len=self.cfg.max_job_len,
                                       use_bigrams=self.cfg.use_bigrams)
        return (torch.as_tensor(ids[None], dtype=torch.long, device=self.device),
                torch.as_tensor(w[None], dtype=torch.float, device=self.device),
                torch.as_tensor(seg[None], dtype=torch.long, device=self.device))

    @torch.no_grad()
    def _logits(self, arrays: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
                job_ids: Sequence[int] | None = None,
                custom_jd: tuple[torch.Tensor, ...] | None = None,
                chunk_size: int = 256) -> np.ndarray:
        ids, w, seg, num = arrays
        out = []
        for start in range(0, len(ids), chunk_size):
            sl = slice(start, start + chunk_size)
            batch = {"ids": torch.as_tensor(ids[sl], dtype=torch.long, device=self.device),
                     "weights": torch.as_tensor(w[sl], dtype=torch.float, device=self.device),
                     "seg": torch.as_tensor(seg[sl], dtype=torch.long, device=self.device),
                     "numeric": torch.as_tensor(num[sl], dtype=torch.float, device=self.device)}
            logits = self.model(batch, job_ids=job_ids, custom_job=custom_jd)["logits"]
            out.append(logits.float().cpu().numpy())
        return np.concatenate(out, axis=0) if out else np.zeros((0, len(job_ids or [1])))

    def _resolve_job(self, job: str | int) -> int:
        if isinstance(job, int) or (isinstance(job, str) and job.isdigit()):
            j = int(job)
            if 0 <= j < len(self.jobs):
                return j
        key = str(job).strip().upper().replace("_", "-")
        if key in self.label2id:
            return self.label2id[key]
        for i, j in enumerate(self.jobs):
            if j.title.lower() == key.lower():
                return i
        raise KeyError(f"未知岗位 {job!r}。可用岗位：{[j.label for j in self.jobs]}")

    # ------------------------------------------------------------------ #
    # 解释：字段消融 + 关键词重合
    # ------------------------------------------------------------------ #
    @torch.no_grad()
    def _explain(self, arrays, job_ids, custom_jd, col: int, job_text: str,
                 top_fields: int = 4, top_terms: int = 8) -> dict[str, Any]:
        ids, w, seg, num = arrays
        base = float(self._logits(arrays, job_ids, custom_jd)[0, col])
        seg_ids = [s for s in np.unique(seg[0]) if s]
        drops = []
        for s in seg_ids:
            m = seg[0] == s
            if not m.any():
                continue
            i2, w2, g2 = ids.copy(), w.copy(), seg.copy()
            i2[0, m], w2[0, m], g2[0, m] = 0, 0, 0
            new = float(self._logits((i2, w2, g2, num), job_ids, custom_jd)[0, col])
            drops.append((ID2SEG.get(int(s), str(s)), round(base - new, 3)))
        drops.sort(key=lambda x: -x[1])
        jd_terms = set(tokenize(job_text))
        cand: dict[str, float] = {}
        for tid, wt in zip(ids[0], w[0]):
            if tid == 0:
                continue
            term = self.vocab.itos[int(tid)] if int(tid) < len(self.vocab) else ""
            if term and not term.startswith("bi:") and term in jd_terms:
                cand[term] = max(cand.get(term, 0.0), float(wt) * self.vocab.idf.get(term, 1.0))
        terms = [t for t, _ in sorted(cand.items(), key=lambda kv: -kv[1])[:top_terms]]
        return {"field_contribution": [{"field": f, "logit_drop": v} for f, v in drops[:top_fields]],
                "matched_terms": terms}

    # ------------------------------------------------------------------ #
    # 功能 1：一个求职者 -> 多个岗位，按适配度排序 + 百分制打分
    # ------------------------------------------------------------------ #
    def rank_jobs_for_resume(self, resume_id: str | int | None = None,
                             resume_text: str | dict[str, str] | None = None,
                             job_ids: Sequence[int] | None = None,
                             top_k: int | None = None,
                             score_mode: str | None = None,
                             explain: bool = False) -> list[JobMatch]:
        mode = score_mode or self.cfg.score_mode
        if resume_id is not None:
            rid = str(resume_id)
            if rid not in self.rid2row:
                raise KeyError(f"库内没有 resume_id={rid}，可改用 resume_text 传入新简历")
            arrays = self._rows_arrays([self.rid2row[rid]])
        elif resume_text is not None:
            arrays = self.encode_raw(resume_text)
        else:
            raise ValueError("需要 resume_id 或 resume_text 之一")

        jids = list(job_ids) if job_ids is not None else list(range(len(self.jobs)))
        logits = self._logits(arrays, jids)                       # [1, M]
        scores = np.asarray(self.calib.scores(logits, mode)).reshape(-1)
        shares = self.calib.share(logits).reshape(-1)
        probs = self.calib.platt(logits).reshape(-1)
        pcts = percentile_scores(scores)
        order = np.argsort(-scores)
        if top_k:
            order = order[:top_k]
        results = []
        for rank, col in enumerate(order, 1):
            jid = jids[int(col)]
            jd_text = self.jobs[jid].jd_text if jid < len(self.jobs) else ""
            ev = (self._explain(arrays, jids, None, int(col), jd_text)
                  if explain else {})
            results.append(JobMatch(
                rank=rank, job_id=jid, label=self.jobs[jid].label,
                title=self.jobs[jid].title, score=float(scores[col]),
                match_probability=float(probs[col]),
                job_share=float(shares[col]), percentile=float(pcts[col]),
                raw_logit=float(logits[0, col]), evidence=ev))
        return results

    # ------------------------------------------------------------------ #
    # 功能 2：一个岗位 -> 多个求职者，选最合适的前 x 人
    # ------------------------------------------------------------------ #
    def rank_resumes_for_job(self, job: str | int | None = None,
                             jd_text: str | None = None,
                             jd_file: str | Path | None = None,
                             job_title: str = "Custom Position",
                             required_skills: str = "",
                             candidate_ids: Sequence[str | int] | None = None,
                             top_x: int | None = 10,
                             score_mode: str | None = None,
                             explain: bool = False) -> list[CandidateMatch]:
        mode = score_mode or self.cfg.score_mode
        if mode == "share":
            raise ValueError("share 模式只适用于「一人多岗」，请改用 platt 或 percentile")
        custom = None
        job_ids = None
        if jd_file:
            jd_text = Path(jd_file).read_text(encoding="utf-8", errors="replace")
        if jd_text:
            custom = self._jd_tensors(job_title, jd_text, required_skills)
            jd_for_explain = jd_text + " " + required_skills
            jid_col_label = "CUSTOM_JD"
        else:
            if job is None:
                raise ValueError("需要 job（岗位标签/编号）或 jd_text / jd_file 之一")
            jid = self._resolve_job(job)
            job_ids = [jid]
            jd_for_explain = self.jobs[jid].jd_text + " " + self.jobs[jid].required_skills
            jid_col_label = self.jobs[jid].label

        if candidate_ids is None:
            rows = list(range(len(self.meta)))
        else:
            rows = [self.rid2row[str(i)] for i in candidate_ids if str(i) in self.rid2row]
        if not rows:
            raise ValueError("候选简历为空")
        arrays = self._rows_arrays(rows)
        logits = self._logits(arrays, job_ids, custom)             # [N, 1]
        base = self.calib.absolute(logits, mode)[:, 0]
        scores = percentile_scores(base) if mode == "percentile" else base
        pcts = percentile_scores(base)
        probs = self.calib.platt(logits[:, 0])
        order = np.argsort(-scores)
        if top_x:
            order = order[:top_x]
        out = []
        for rank, k in enumerate(order, 1):
            row = rows[int(k)]
            one = (arrays[0][k:k + 1], arrays[1][k:k + 1],
                   arrays[2][k:k + 1], arrays[3][k:k + 1])
            ev = (self._explain(one, job_ids, custom, 0, jd_for_explain)
                  if explain else {})
            m = self.meta[row]
            out.append(CandidateMatch(
                rank=rank, resume_id=m["rid"], file=m["file"], name=m["name"],
                true_label=m["label"], score=float(scores[k]),
                match_probability=float(probs[k]),
                percentile=float(pcts[k]), raw_logit=float(logits[k, 0]),
                summary=m["summary"], evidence=ev))
        return out

    # ------------------------------------------------------------------ #
    def score_all_for_job(self, job: str | int, score_mode: str = "spread") -> np.ndarray:
        """返回全库简历对某岗位的主分，顺序与 self.meta 一致。"""
        if score_mode == "share":
            raise ValueError("share 模式只适用于「一人多岗」")
        jid = self._resolve_job(job)
        logits = self._logits(self._rows_arrays(list(range(len(self.meta)))), [jid])
        base = self.calib.absolute(logits, score_mode)[:, 0]
        return percentile_scores(base) if score_mode == "percentile" else base

    def info(self) -> dict[str, Any]:
        return {"n_resumes": len(self.meta), "n_jobs": len(self.jobs),
                "n_vocab": len(self.vocab), "score_mode": self.cfg.score_mode,
                "calibrator": self.calib.to_dict(), "metrics": self.metrics,
                "jobs": [{"job_id": j.job_id, "label": j.label, "title": j.title,
                          "n_train": j.n_train} for j in self.jobs]}
