"""仅用于受限沙箱内打包交付物（显式白名单版）。不属于交付代码。"""
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tempfile.tempdir = str(ROOT / ".runtime")
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
shutil.copy2(ROOT / ".runtime/full_outputs/jobfit.ckpt", OUT / "jobfit.ckpt")
shutil.copy2(ROOT / ".runtime/full_outputs/training_report.json", OUT / "training_report.json")

# 清掉受限沙箱 tempfile 探测失败留下的 0 字节随机名文件
probe = re.compile(r"^[a-z0-9_]{8}$")
removed = []
for p in ROOT.iterdir():
    if p.is_file() and probe.match(p.name) and p.stat().st_size == 0:
        try:
            p.unlink()
            removed.append(p.name)
        except OSError:
            pass

TOP_DIRS = ["configs", "examples", "jobfit", "outputs", "tests"]
TOP_FILES = ["requirements.txt"]
ZIP = ROOT.parent / "jobfit_project.zip"
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for d in TOP_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            rel = p.relative_to(ROOT)
            if p.is_file() and "__pycache__" not in rel.parts and p.suffix != ".pyc":
                z.write(p, p.relative_to(ROOT.parent))
    for f in TOP_FILES:
        z.write(ROOT / f, Path("jobfit_project") / f)
print("removed probe files:", removed)
print("ZIP:", ZIP, round(ZIP.stat().st_size / 1e6, 2), "MB")
with zipfile.ZipFile(ZIP) as z:
    for n in z.namelist():
        print(" ", n)
