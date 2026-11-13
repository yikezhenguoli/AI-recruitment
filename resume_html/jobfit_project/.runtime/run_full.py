"""仅用于受限沙箱内验证全量训练。不属于交付代码。"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tempfile.tempdir = str(ROOT / ".runtime")
sys.path.insert(0, str(ROOT))

from jobfit.cli import main  # noqa: E402

main(["train", "--config", str(ROOT / "configs/default.json"),
      "--data-dir", "/Users/zhengrui/Documents/computer_programme/AI-recruitment/resume_html",
      "--epochs", "30", "--device", "cpu",
      "--out-dir", str(ROOT / ".runtime/full_outputs")])
