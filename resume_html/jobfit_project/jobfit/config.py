"""全局配置：所有超参数集中在这里，可用 JSON 文件覆盖，也可用 --set k=v 覆盖。

设计原则：Config 是可 JSON 序列化的纯数据对象，随 checkpoint 一起保存，
保证推理时用完全相同的文本/模型配置重建网络。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

# 简历字段 -> 允许参与建模的最大字符数。顺序即模型看到的顺序，
# 前面的字段优先占用 max_len 的 token 预算（信息密度高的放前面）。
DEFAULT_FIELD_BUDGETS = {
    "header_text": 160,
    "summary": 900,
    "skills": 700,
    "highlights": 550,
    "experience_text": 1400,
    "education_text": 500,
    "technical_skills": 300,
    "accomplishments": 400,
    "certifications": 200,
    "affiliations": 150,
    "languages": 100,
    "publications": 150,
    "awards": 150,
    "additional_info": 200,
    "personal_info": 150,
    "interests": 100,
    "objective": 200,
    "other_sections": 400,
}

# 数值特征名（顺序固定，改动需同步 data.py 的 build_numeric）
NUMERIC_NAMES = [
    "log_n_experiences", "log_n_education", "log_n_sections", "log_n_items",
    "log_text_chars", "log_years_experience", "log_skill_terms", "has_summary",
]


@dataclass
class Config:
    # ---- 数据 ----
    data_dir: str = "./data"
    out_dir: str = "./outputs"
    tag_file: str = "tag.csv"
    resume_file: str = "resumes.csv"
    experience_file: str = "resume_experiences.csv"   # 可选，用于估算工作年限
    structure_file: str = "structure_groups.csv"       # 可选，重复内容分组提示
    jobs_file: str = "jobs.csv"                         # 可选，自定义岗位 JD

    # ---- 文本向量化 ----
    max_len: int = 384
    max_job_len: int = 96
    min_df: int = 2
    max_vocab: int = 30000
    use_bigrams: bool = True
    field_budgets: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_FIELD_BUDGETS))

    # ---- 模型 ----
    d_emb: int = 128
    d_model: int = 128
    cnn_kernels: list[int] = field(default_factory=lambda: [2, 3, 4])
    dropout: float = 0.2
    init_temp: float = 0.07          # 余弦 logits 初始温度
    use_score_supervision: bool = False  # tag.csv 带第 3 列 0-100 分数时才开

    # ---- 训练 ----
    seed: int = 42
    epochs: int = 40
    batch_size: int = 32
    lr: float = 2e-3
    weight_decay: float = 1e-4
    warmup_ratio: float = 0.1
    label_smoothing: float = 0.05
    balanced: bool = True           # 类别不平衡加权
    margin_weight: float = 0.1      # 难负样本排序损失权重
    margin: float = 0.4
    patience: int = 6
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    # test_ratio = 1 - train_ratio - val_ratio
    max_samples: int = 0            # >0 时只取前 N 份，调试用
    num_workers: int = 0
    device: str = "auto"
    log_every: int = 0              # 每 N 个 batch 打印一次，0=每轮一次

    # ---- 打分 ----
    score_mode: str = "spread"      # spread | platt | share | percentile

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Config":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def load(cls, path: str | Path | None) -> "Config":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8"))) if path else cls()

    def update(self, overrides: dict[str, Any]) -> "Config":
        """按字段名覆盖；自动做基础类型推断（int/float/bool/list）。"""
        known = {f.name: f for f in fields(self)}
        for k, v in overrides.items():
            if k not in known or v is None:
                continue
            cur = getattr(self, k)
            if isinstance(v, str):
                low = v.lower()
                if isinstance(cur, bool):
                    v = low in ("1", "true", "yes", "y", "on")
                elif isinstance(cur, int) and not isinstance(cur, bool):
                    v = int(v)
                elif isinstance(cur, float):
                    v = float(v)
                elif isinstance(cur, (list, dict)):
                    v = json.loads(v)
            setattr(self, k, v)
        return self
