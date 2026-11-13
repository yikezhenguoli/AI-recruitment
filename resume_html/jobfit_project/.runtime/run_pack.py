"""仅用于受限沙箱内打包交付物。不属于交付代码。"""
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

ZIP = ROOT.parent / "jobfit_project.zip"
skip = {".runtime", "__pycache__"}
with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in sorted(ROOT.rglob("*")):
        rel_inside = p.relative_to(ROOT)
        if not p.is_file() or any(x in skip for x in rel_inside.parts):
            continue
        if p.suffix in (".pyc",) or p.name == ".DS_Store":
            continue
        z.write(p, p.relative_to(ROOT.parent))
print("ZIP:", ZIP, round(ZIP.stat().st_size / 1e6, 2), "MB")
with zipfile.ZipFile(ZIP) as z:
    for n in z.namelist():
        print(" ", n)
