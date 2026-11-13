"""分词、词表、TF-IDF 权重与向量化。

刻意不依赖 jieba / sklearn / 分词模型：这批数据是英文简历，
正则分词 + 词表 + idf 已足够，且保证整个包只需 torch + numpy。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Sequence

import numpy as np

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#&./'_-]*")
PLACEHOLDER_RE = re.compile(
    r"\b(company name|city,? state|city|state|n/?a|current|present|references available upon request)\b",
    re.I,
)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)

# 高频无判别力词。注意不要把岗位名（hr, sales, finance...）放进来。
STOPWORDS = set("""
a an the and or of to in for with on at by from as is are was were be been being this that these those
it its i my me we our you your their his her they them he she not no do does did done have has had having
will would can could should may might must shall about into over under per via plus also more most very
such other some any all each both few than then so if but because while during within across after before
years year month months day days time work working worked job jobs position positions role roles
name first last email phone address contact resume curriculum vitae objective references
company companies location employer employment duties duty responsible responsibilities
""".split())

# 字段顺序 = segment id 顺序（0 保留给 padding）
FIELD_ORDER = [
    "header_text", "summary", "skills", "highlights", "experience_text",
    "education_text", "technical_skills", "accomplishments", "certifications",
    "affiliations", "languages", "publications", "awards", "additional_info",
    "personal_info", "interests", "objective", "other_sections",
]
SEG2ID = {name: i + 1 for i, name in enumerate(FIELD_ORDER)}
N_SEGMENTS = len(FIELD_ORDER) + 1


def normalize(text: str) -> str:
    text = URL_RE.sub(" ", text or "")
    text = PLACEHOLDER_RE.sub(" ", text)
    text = text.replace("|", " ").replace("\u00a0", " ")
    return text.lower()


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for raw in TOKEN_RE.findall(normalize(text)):
        w = raw.strip(".,;:!?()[]{}\"'_-")
        if len(w) < 2 or w in STOPWORDS or w.isdigit():
            continue
        out.append(w)
    return out


class Vocab:
    """词表 + idf。词表只在训练集上拟合，避免验证/测试集信息泄漏。"""

    PAD = "[PAD]"
    UNK = "[UNK]"

    def __init__(self) -> None:
        self.itos: list[str] = [self.PAD, self.UNK]
        self.stoi: dict[str, int] = {self.PAD: 0, self.UNK: 1}
        self.idf: dict[str, float] = {self.UNK: 1.0, self.PAD: 1.0}
        self.use_bigrams = True

    def add(self, word: str) -> None:
        if word not in self.stoi:
            self.stoi[word] = len(self.itos)
            self.itos.append(word)

    def __len__(self) -> int:
        return len(self.itos)

    @classmethod
    def build(cls, docs: Sequence[Sequence[str]], *, min_df: int = 2,
              max_vocab: int = 30000, use_bigrams: bool = True) -> "Vocab":
        df_u: Counter = Counter()
        df_b: Counter = Counter()
        for toks in docs:
            df_u.update(set(toks))
            if use_bigrams:
                df_b.update({f"bi:{a}_{b}" for a, b in zip(toks, toks[1:])})
        n_uni_budget = int(max_vocab * 0.65)
        uni = [w for w, c in sorted(df_u.items(), key=lambda kv: (-kv[1], kv[0]))
               if c >= min_df][:n_uni_budget]
        bi = [w for w, c in sorted(df_b.items(), key=lambda kv: (-kv[1], kv[0]))
              if c >= min_df][:max_vocab - len(uni)]
        v = cls()
        v.use_bigrams = use_bigrams
        for w in uni + bi:
            v.add(w)
        n_docs = max(1, len(docs))
        for w in uni + bi:
            df = (df_b if w.startswith("bi:") else df_u).get(w, 1)
            v.idf[w] = math.log((1 + n_docs) / (1 + df)) + 1.0
        return v

    def encode_weighted(self, tokens: Sequence[str], use_bigrams: bool | None = None
                        ) -> tuple[list[int], list[float]]:
        """返回 (token_id 列表, tf-idf 权重列表)。unigram 在前，bigram 在后，
        这样截断时优先保留主词。权重做 l2 归一化，便于加权池化。"""
        use_bigrams = self.use_bigrams if use_bigrams is None else use_bigrams
        tf: dict[str, int] = {}
        order: list[str] = []
        for t in tokens:
            key = t if t in self.stoi else self.UNK
            if key not in tf:
                order.append(key)
                tf[key] = 0
            tf[key] += 1
        bi_order: list[str] = []
        if use_bigrams:
            for a, b in zip(tokens, tokens[1:]):
                k = f"bi:{a}_{b}"
                if k in self.stoi:
                    if k not in tf:
                        bi_order.append(k)
                        tf[k] = 0
                    tf[k] += 1
        features = order + bi_order
        ids = [self.stoi[f] for f in features]
        w = np.asarray([(1.0 + math.log(tf[f])) * self.idf.get(f, 1.0) for f in features],
                       dtype=np.float32)
        norm = float(np.linalg.norm(w))
        if norm > 0:
            w /= norm
        return ids, w.tolist()

    def to_dict(self) -> dict:
        return {"itos": self.itos, "idf": self.idf, "use_bigrams": self.use_bigrams}

    @classmethod
    def from_dict(cls, d: dict) -> "Vocab":
        v = cls()
        v.itos = list(d["itos"])
        v.stoi = {w: i for i, w in enumerate(v.itos)}
        v.idf = dict(d["idf"])
        v.use_bigrams = bool(d.get("use_bigrams", True))
        return v


def vectorize_fields(fields: Sequence[tuple[str, str]], vocab: Vocab, *,
                     budgets: dict[str, int], max_len: int,
                     use_bigrams: bool | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """把 (字段名, 文本) 列表编码为定长 (ids, weights, seg_ids)。"""
    L = int(max_len)
    ids = np.zeros(L, dtype=np.int64)
    weights = np.zeros(L, dtype=np.float32)
    segs = np.zeros(L, dtype=np.int64)
    pos = 0
    for name, text in fields:
        if not text or pos >= L:
            continue
        chunk = text[:int(budgets.get(name, 200))]
        tok_ids, tok_w = vocab.encode_weighted(tokenize(chunk), use_bigrams)
        sid = SEG2ID.get(name, 0)
        for tid, tw in zip(tok_ids, tok_w):
            if pos >= L:
                break
            ids[pos], weights[pos], segs[pos] = tid, tw, sid
            pos += 1
        if pos >= L:
            break
    return ids, weights, segs


def fields_from_raw_text(text: str) -> list[tuple[str, str]]:
    """推理时传入一段全新简历文本：按空行/换行粗分为 summary 与 skills 两段。"""
    text = (text or "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 4:
        cut = max(1, len(lines) // 3)
        return [("summary", " ".join(lines[:cut])), ("experience_text", " ".join(lines[cut:]))]
    return [("summary", " ".join(lines))] if lines else [("summary", "")]
