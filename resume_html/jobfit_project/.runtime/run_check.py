"""仅用于受限沙箱内验证：预置 tempfile.tempdir 后运行 smoke_test。不属于交付代码。"""
import runpy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP = ROOT / ".runtime"
TEMP.mkdir(exist_ok=True)
tempfile.tempdir = str(TEMP)
sys.path.insert(0, str(ROOT))
sys.argv = ["smoke_test.py", "--data-dir",
            "/Users/zhengrui/Documents/computer_programme/AI-recruitment/resume_html"]
runpy.run_path(str(ROOT / "tests" / "smoke_test.py"), run_name="__main__")
