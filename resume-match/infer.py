"""把训练好的 checkpoint 包成可复用的 ResumeMatcher。

这个文件的有意设计：
  * 模块顶层只 import 标准库 —— 后端/CLI 在没装 torch 的机器上也能 `--help`，
    import 本模块本身不会炸；真正缺依赖时在 __init__ 里给出明确错误。
  * 不 import 本目录的 common.py —— 因为约定里的 `python -I infer_cli.py`
    会移除脚本所在目录，infer_cli 会显式把目录插回 sys.path 再 import 本模块。
    这里保持自包含，便于单独拷走复用。

CLI 与类的输出结构必须完全一致（后端按字段名解析，不要改键名）：
    {"category", "confidence", "top_k": [{"code","score"}], "model_version", "scores"}
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# 标签文件允许放在 <model-dir>/label2id.json，也允许放在上一级（训练输出目录）。
# 两者都找不到就报错，绝不猜测标签顺序。
LABEL_FILES = ("label2id.json",)
DRY_RUN_MARKER = "DRY_RUN.txt"

_SPACE_RE = re.compile(r"[ \t]+")
_NEWLINE_RE = re.compile(r"\n{3,}")


class MatcherError(RuntimeError):
    """带退出码的错误，供 CLI 直接映射到非 0 退出码。"""

    def __init__(self, message: str, exit_code: int = 3):
        super().__init__(message)
        self.exit_code = exit_code


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("\xa0", " ").replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACE_RE.sub(" ", text)
    text = _NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _load_label_map(model_dir: Path) -> tuple[dict[str, int], dict[int, str], Path]:
    candidates = [model_dir / name for name in LABEL_FILES] + [model_dir.parent / name for name in LABEL_FILES]
    for path in candidates:
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise MatcherError(f"label2id.json 不是合法 JSON: {path} ({exc})") from exc
            if not isinstance(raw, dict) or not raw:
                raise MatcherError(f"label2id.json 结构不对: {path}")
            label2id = {str(k): int(v) for k, v in raw.items()}
            ids = sorted(label2id.values())
            if ids != list(range(len(ids))):
                raise MatcherError(
                    f"label2id.json 的 id 必须从 0 连续编号，实际为 {ids[:10]}...（{path}）"
                )
            id2label = {v: k for k, v in label2id.items()}
            return label2id, id2label, path
    raise MatcherError(
        "缺少 label2id.json：既不在模型目录也不在其上一级。"
        f"已查找: {[str(p) for p in candidates]}"
    )


def _optional_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_device(device: str | None, torch) -> str:
    requested = (device or "auto").lower()
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested.startswith("cuda") and not torch.cuda.is_available():
        raise MatcherError(
            f"指定了 device={requested!r}，但当前环境 torch.cuda.is_available() 为 False。"
            "若想自动回落到 CPU，请用 --device auto 或省略 --device。",
            exit_code=4,
        )
    if requested not in ("cpu", "cuda") and not requested.startswith("cuda:"):
        raise MatcherError(f"不支持的 device={requested!r}（可选 auto/cpu/cuda/cuda:N）", exit_code=2)
    return requested


def _softmax_rows(logits):
    """float64 里做 softmax + 逐行归一化，保证 scores 之和与 1 的误差远小于 1e-6。"""
    import torch

    logits = logits.double()
    logits = logits - logits.max(dim=-1, keepdim=True).values
    exp = torch.exp(logits)
    return exp / exp.sum(dim=-1, keepdim=True)


def build_result(probs, label2id: dict[str, int], model_version: str, top_k: int = 5) -> dict:
    """把一条样本的 24 维概率转成契约要求的 dict。"""
    id2label = {v: k for k, v in label2id.items()}
    n = len(id2label)
    if len(probs) != n:
        raise MatcherError(f"概率维度 {len(probs)} 与标签数 {n} 不一致")
    if not 1 <= top_k <= n:
        raise MatcherError(f"--top-k 应在 1..{n} 之间，收到 {top_k}", exit_code=2)

    values = [float(x) for x in probs]
    total = sum(values)
    if total <= 0 or total != total:  # 0 或 NaN
        raise MatcherError("模型输出概率非法（总和为 0 或 NaN）")
    # 双重保险：先按 float64 归一化，再转 Python float
    values = [v / total for v in values]
    order = sorted(range(n), key=lambda i: (-values[i], id2label[i]))
    scores = {id2label[i]: values[i] for i in range(n)}
    top = [{"code": id2label[i], "score": values[i]} for i in order[:top_k]]
    return {
        "category": top[0]["code"],
        "confidence": top[0]["score"],
        "top_k": top,
        "model_version": model_version,
        "scores": scores,
    }


class ResumeMatcher:
    """加载 best/ 目录，提供 predict(text) / predict_batch(texts) / predict_proba(texts)。"""

    def __init__(
        self,
        model_dir: str | os.PathLike,
        device: str | None = None,
        max_length: int | None = None,
        allow_dry_run: bool = False,
    ):
        self.model_dir = Path(model_dir).expanduser().resolve()
        if not self.model_dir.is_dir():
            raise MatcherError(f"模型目录不存在或不是目录: {self.model_dir}")

        if (self.model_dir / DRY_RUN_MARKER).is_file() and not allow_dry_run:
            raise MatcherError(
                f"{self.model_dir} 是 --dry-run 生成的随机权重检查点（含 {DRY_RUN_MARKER}），不能用于推理。"
                "如只是验证链路，请加 --allow-dry-run。"
            )

        try:
            import torch  # noqa: F401  （在这里 import，保证无 torch 时只报一条清晰错误）
        except ImportError as exc:
            raise MatcherError(
                "当前解释器没有安装 torch。请在训练/推理用的 venv 里执行 "
                "`pip install -r requirements-train.txt`。"
                "注意：如果依赖装在 --user 目录，`python -I` 会屏蔽 user site，请改用 venv。"
            ) from exc

        try:
            import transformers  # noqa: F401
        except ImportError as exc:
            raise MatcherError("当前解释器没有安装 transformers，请先安装 requirements-train.txt") from exc

        self.label2id, self.id2label, self.label_file = _load_label_map(self.model_dir)
        self.num_labels = len(self.label2id)

        cfg = _optional_json(self.model_dir / "infer_config.json")
        if not cfg:
            cfg = _optional_json(self.model_dir.parent / "infer_config.json")
        self.task = str(cfg.get("task") or "cls")
        if self.task not in ("cls", "pair"):
            raise MatcherError(f"infer_config.json 中的 task={self.task!r} 不受支持")
        self.jds: dict[str, dict[str, str]] = {}
        if self.task == "pair":
            jd_path = self.model_dir / "jds.json"
            if not jd_path.is_file():
                jd_path = self.model_dir.parent / "jds.json"
            raw_jds = _optional_json(jd_path)
            if not raw_jds:
                raise MatcherError(f"pair 模型缺少 jds.json（已查找 {jd_path}）")
            missing = sorted(set(self.label2id) - set(raw_jds))
            if missing:
                raise MatcherError(f"jds.json 缺少这些类别: {missing}")
            self.jds = {code: raw_jds[code] for code in self.label2id}
        self.max_length = int(max_length or cfg.get("max_length") or 256)
        if not 8 <= self.max_length <= 4096:
            raise MatcherError(f"max_length={self.max_length} 不合理（应在 8..4096）", exit_code=2)
        self.truncation = str(cfg.get("truncation") or "head")
        if self.truncation not in ("head", "head_tail", "only_first"):
            raise MatcherError(f"infer_config.json 中的 truncation={self.truncation!r} 不受支持")

        self.model_version = (
            cfg.get("model_version")
            or _optional_json(self.model_dir / "model_version.json").get("model_version")
            or _optional_json(self.model_dir.parent / "model_version.json").get("model_version")
            or f"{self.model_dir.name}@unknown"
        )

        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer_error: Exception | None = None
        self.tokenizer = None
        for use_fast in (True, False):
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(
                    str(self.model_dir), use_fast=use_fast
                )
                break
            except Exception as exc:  # noqa: BLE001 - 先 fast 再 slow
                tokenizer_error = exc
        if self.tokenizer is None:
            raise MatcherError(
                f"从 {self.model_dir} 加载 tokenizer 失败: {type(tokenizer_error).__name__}: {tokenizer_error}\n"
                "常见原因：模型目录不完整、缺少 sentencepiece/tokenizers、或处于离线环境。"
            ) from tokenizer_error

        try:
            self.model = AutoModelForSequenceClassification.from_pretrained(str(self.model_dir))
        except Exception as exc:  # noqa: BLE001
            raise MatcherError(
                f"从 {self.model_dir} 加载模型失败: {type(exc).__name__}: {exc}\n"
                "请确认该目录是 train.py 保存的 best/（含 config.json 和权重文件）。"
            ) from exc

        expected = 1 if self.task == "pair" else self.num_labels
        if int(getattr(self.model.config, "num_labels", -1)) != expected:
            raise MatcherError(
                "模型 num_labels 与 task 不一致："
                f"task={self.task}, config={getattr(self.model.config, 'num_labels', None)}, "
                f"期望 {expected}"
            )

        self.device = _resolve_device(device, torch)
        if self.device == "cpu":
            # CPU 单条推理时别让 torch 抢满所有核，否则与后端同机部署会互相拖慢。
            threads = max(1, min(8, os.cpu_count() or 1))
            torch.set_num_threads(threads)
        self.model.to(self.device)
        self.model.eval()
        self.torch = torch

    # ------------------------------------------------------------------ 推理
    def _batch_size(self, batch_size: int | None) -> int:
        if batch_size is None:
            batch_size = 16 if self.device.startswith("cuda") else 4
        return max(1, int(batch_size))

    def _pair_logits(self, pairs: list[tuple[str, str]], batch_size: int | None = None) -> list[float]:
        """pair 任务的前向：返回每对 (简历, JD) 的匹配 logit。"""
        cleaned = [(normalize_text(a), normalize_text(b)) for a, b in pairs]
        if any(not a or not b for a, b in cleaned):
            raise MatcherError("简历或 JD 为空（空白字符不算有效文本）", exit_code=2)
        batch_size = self._batch_size(batch_size)
        out: list[float] = []
        with self.torch.inference_mode():
            for start in range(0, len(cleaned), batch_size):
                chunk = cleaned[start : start + batch_size]
                encoded = self.tokenizer(
                    [a for a, _ in chunk],
                    [b for _, b in chunk],
                    truncation="only_first",
                    max_length=self.max_length,
                    padding=True,
                    return_tensors="pt",
                    return_token_type_ids=False,
                )
                encoded = {
                    k: v.to(self.device) for k, v in encoded.items()
                    if k in ("input_ids", "attention_mask")
                }
                logits = self.model(**encoded).logits.squeeze(-1)
                out.extend(logits.float().cpu().tolist())
        return out

    def predict_proba(self, texts: list[str], batch_size: int | None = None) -> list[list[float]]:
        """返回每条的 24 维类别分布（Python float，已归一化）。

        pair 任务下：拿该简历与 24 个参考 JD 各打一次分，再对分数做 softmax，
        形状与 cls 任务一致，后端无需区分。
        """
        if isinstance(texts, str):
            raise TypeError("predict_proba 需要 list[str]；单条请用 predict()")
        cleaned = [normalize_text(t) for t in texts]
        if any(not t for t in cleaned):
            raise MatcherError("输入文本为空（空白字符不算有效简历）", exit_code=2)
        if not cleaned:
            return []

        if self.task == "pair":
            codes = [""] * self.num_labels
            for code, index in self.label2id.items():
                codes[index] = code
            rows: list[list[float]] = []
            for text in cleaned:
                logits = self._pair_logits(
                    [(text, self.jds[code]["en"]) for code in codes], batch_size
                )
                probs = _softmax_rows(self.torch.tensor([logits], dtype=self.torch.float64))
                rows.append(probs[0].tolist())
            return rows

        batch_size = self._batch_size(batch_size)

        out: list[list[float]] = []
        with self.torch.inference_mode():
            for start in range(0, len(cleaned), batch_size):
                chunk = cleaned[start : start + batch_size]
                if self.truncation == "head_tail":
                    raw = self.tokenizer(
                        chunk, truncation=False, padding=False, return_attention_mask=True
                    )
                    ids_list = []
                    for ids in raw["input_ids"]:
                        if len(ids) > self.max_length:
                            head = self.max_length // 2
                            ids = ids[:head] + ids[-(self.max_length - head):]
                        ids_list.append(list(ids))
                    masks = [[1] * len(ids) for ids in ids_list]
                    encoded = self.tokenizer.pad(
                        {"input_ids": ids_list, "attention_mask": masks},
                        padding=True,
                        return_tensors="pt",
                    )
                else:
                    encoded = self.tokenizer(
                        chunk,
                        truncation=True,
                        max_length=self.max_length,
                        padding=True,
                        return_tensors="pt",
                    )
                # 只保留模型确定接受的键；DeBERTa 的 type_vocab_size=0 不想要 token_type_ids
                encoded = {
                    k: v.to(self.device) for k, v in encoded.items() if k in ("input_ids", "attention_mask")
                }
                logits = self.model(**encoded).logits
                probs = _softmax_rows(logits)
                out.extend(probs.cpu().tolist())
        return out

    def score_jd(self, text: str, jd_text: str) -> float:
        """pair 任务下：这份简历与该 JD 的匹配概率（0~1）。"""
        if self.task != "pair":
            raise MatcherError("当前模型不是 pair 任务，无法按 JD 单独打分")
        logit = self._pair_logits([(text, jd_text)])[0]
        return float(self.torch.sigmoid(self.torch.tensor(logit, dtype=self.torch.float64)))

    def score_pairs(self, pairs: list[tuple[str, str]], batch_size: int | None = None) -> list[float]:
        """批量给 (简历, JD) 打匹配概率，供评测脚本使用。"""
        if self.task != "pair":
            raise MatcherError("当前模型不是 pair 任务，无法按 JD 打分")
        logits = self._pair_logits(pairs, batch_size)
        return [float(self.torch.sigmoid(self.torch.tensor(x, dtype=self.torch.float64)))
                for x in logits]

    def predict(self, text: str, top_k: int = 5, jd_text: str | None = None) -> dict:
        if not isinstance(text, str):
            raise MatcherError("text 必须是 str", exit_code=2)
        if not normalize_text(text):
            raise MatcherError("输入文本为空（空白字符不算有效简历）", exit_code=2)
        probs = self.predict_proba([text])[0]
        result = build_result(probs, self.label2id, self.model_version, top_k=top_k)
        if self.task == "pair" and jd_text and jd_text.strip():
            # 这才是"这份简历对这个岗位"的真实分数；confidence 仍是 24 类里最高那一类的概率
            result["jd_match_score"] = round(self.score_jd(text, jd_text), 6)
        return result

    def predict_batch(self, texts: list[str], top_k: int = 5) -> list[dict]:
        probs_list = self.predict_proba(texts)
        return [build_result(p, self.label2id, self.model_version, top_k=top_k) for p in probs_list]
