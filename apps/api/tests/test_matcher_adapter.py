import asyncio
import json
import sys

import pytest

from ttc.adapters.matcher import CATEGORY_CODES, ResumeMatchAdapter
from ttc.core.config import get_settings
from ttc.core.errors import TTCError

VALID_OUTPUT = {
    "category": "INFORMATION-TECHNOLOGY", "confidence": 0.87,
    "top_k": [{"code": "INFORMATION-TECHNOLOGY", "score": 0.87},
              {"code": "ENGINEERING", "score": 0.05}],
    "model_version": "deberta-v3-base@test-run",
    "scores": {code: (0.87 if code == "INFORMATION-TECHNOLOGY" else 0.13 / 23)
               for code in sorted(CATEGORY_CODES)},
}


def _configure(monkeypatch, *, cli, model_dir, fallback=False):
    settings = get_settings()
    monkeypatch.setattr(settings, "resume_match_cli_path", str(cli))
    monkeypatch.setattr(settings, "resume_match_model_dir", str(model_dir))
    monkeypatch.setattr(settings, "resume_match_allow_keyword_fallback", fallback)
    monkeypatch.setattr(settings, "resume_match_python", sys.executable)
    monkeypatch.setattr(settings, "resume_match_timeout_seconds", 30)


def test_keyword_fallback_contract(monkeypatch, tmp_path):
    _configure(monkeypatch, cli=tmp_path / "missing.py", model_dir=tmp_path / "missing",
               fallback=True)
    result = asyncio.run(ResumeMatchAdapter().predict(
        "Python backend engineer with PostgreSQL and Linux experience",
        jd_text="负责后端服务开发，熟悉 Python 与 PostgreSQL"))
    assert result["model_version"] == "keyword-fallback"
    assert set(result["scores"]) == CATEGORY_CODES
    assert result["category"] in CATEGORY_CODES
    assert 0 <= result["confidence"] <= 1
    assert result["fallback_reason"]


def test_fallback_avoids_substring_false_positives(monkeypatch, tmp_path):
    _configure(monkeypatch, cli=tmp_path / "missing.py", model_dir=tmp_path / "missing",
               fallback=True)
    result = asyncio.run(ResumeMatchAdapter().predict(
        "Senior backend engineer building Python services on Linux and PostgreSQL",
        jd_text="负责后端服务开发，熟悉 Python 与 PostgreSQL，熟悉 Linux 服务器"))
    ranked = [item["code"] for item in result["top_k"][:5]]
    # engineer 不应命中 engine（AUTOMOBILE），building 不应命中 building（CONSTRUCTION）
    assert "AUTOMOBILE" not in ranked
    assert "INFORMATION-TECHNOLOGY" in ranked


def test_missing_model_raises_503(monkeypatch, tmp_path):
    _configure(monkeypatch, cli=tmp_path / "missing.py", model_dir=tmp_path / "missing")
    with pytest.raises(TTCError) as caught:
        asyncio.run(ResumeMatchAdapter().predict("some resume"))
    assert caught.value.code == "TTC-5005"
    assert caught.value.status_code == 503


def test_subprocess_valid_output(monkeypatch, tmp_path):
    cli = tmp_path / "fake_infer.py"
    cli.write_text(
        "import json, sys\n"
        "args = sys.argv\n"
        "path = args[args.index('--text-file') + 1]\n"
        "assert open(path, encoding='utf-8').read()\n"
        f"payload = {json.dumps(VALID_OUTPUT)}\n"
        "print('loading model...')\n"
        "print(json.dumps(payload, ensure_ascii=False))\n",
        encoding="utf-8")
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    _configure(monkeypatch, cli=cli, model_dir=model_dir)
    result = asyncio.run(ResumeMatchAdapter().predict("算法工程师 Python", jd_text="Python"))
    assert result["category"] == "INFORMATION-TECHNOLOGY"
    assert result["model_version"] == "deberta-v3-base@test-run"
    assert len(result["top_k"]) == 2


def test_subprocess_invalid_contract(monkeypatch, tmp_path):
    cli = tmp_path / "bad_infer.py"
    cli.write_text(
        "import json\n"
        "print(json.dumps({'category': 'UNKNOWN', 'confidence': 0.9, 'top_k': [],"
        " 'model_version': 'x', 'scores': {'ACCOUNTANT': 1.0}}))\n",
        encoding="utf-8")
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    _configure(monkeypatch, cli=cli, model_dir=model_dir)
    with pytest.raises(TTCError) as caught:
        asyncio.run(ResumeMatchAdapter().predict("some resume"))
    assert caught.value.code == "TTC-5002"
    assert caught.value.status_code == 502
