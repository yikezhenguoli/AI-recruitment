"""仅用于受限沙箱内验证最终 checkpoint 的两个业务功能。不属于交付代码。"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tempfile.tempdir = str(ROOT / ".runtime")
sys.path.insert(0, str(ROOT))

from jobfit.cli import main  # noqa: E402

CKPT = str(ROOT / ".runtime/full_outputs/jobfit.ckpt")
main(["info", "--ckpt", CKPT])
main(["match-jobs", "--ckpt", CKPT, "--resume-id", "3", "--top-k", "5",
      "--explain", "--csv", str(ROOT / ".runtime/resume3_jobs.csv")])
main(["match-candidates", "--ckpt", CKPT, "--job", "HR", "--top-x", "10",
      "--csv", str(ROOT / ".runtime/hr_top10.csv")])
main(["match-candidates", "--ckpt", CKPT, "--job", "HR", "--top-x", "5",
      "--score-mode", "percentile"])
