"""jobfit：基于 PyTorch 的简历-岗位适配度模型。

快速开始（在项目根目录执行）：
    python -m jobfit.cli train --data-dir /path/to/resume_html
    python -m jobfit.cli match-jobs --resume-id 3 --top-k 5
    python -m jobfit.cli match-candidates --job HR --top-x 10
"""
from .config import Config
from .data import Corpus
from .model import JobFitModel
from .train import train

__all__ = ["Config", "Corpus", "JobFitModel", "JobFitPredictor", "train"]
__version__ = "1.0.0"


def __getattr__(name: str):
    # 延迟导入，避免仅查看配置时也强制加载推理依赖
    if name == "JobFitPredictor":
        from .inference import JobFitPredictor
        return JobFitPredictor
    raise AttributeError(name)
