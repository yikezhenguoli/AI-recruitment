import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reset_demo_database.py"
SPEC = importlib.util.spec_from_file_location("reset_demo_database", SCRIPT)
assert SPEC and SPEC.loader
RESET_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESET_MODULE)


def test_demo_job_presets_are_complete_and_unique() -> None:
    titles = [job["title"] for job in RESET_MODULE.DEMO_JOB_PRESETS]
    assert len(titles) == 5
    assert len(set(titles)) == 5
    assert RESET_MODULE.EXPECTED_MIGRATION == "0011_interview_markdown_report"

    for job in RESET_MODULE.DEMO_JOB_PRESETS:
        assert job["template"] in RESET_MODULE.DEMO_WEIGHT_TEMPLATES
        assert job["template"] in RESET_MODULE.DEMO_INTERVIEW_ROUNDS
        assert len(job["responsibilities"]) >= 4
        assert len(job["requirements"]) >= 4
        assert len(job["skills"]) >= 4
        jd_text = RESET_MODULE.job_jd_text(job)
        assert len(jd_text) >= 20
        assert job["title"] in jd_text
        assert all(skill in jd_text for skill in job["skills"])


def test_demo_weight_plans_total_one_hundred_percent() -> None:
    for template in RESET_MODULE.DEMO_WEIGHT_TEMPLATES:
        dimensions = RESET_MODULE.weight_dimensions(template)
        assert len(dimensions) == 5
        assert sum(item["weight_pct"] for item in dimensions) == 100
        assert len({item["key"] for item in dimensions}) == 5


def test_demo_login_accounts_match_frontend_defaults() -> None:
    assert RESET_MODULE.DEMO_ADMIN_EMAIL == "web.test.hr@ttc.local"
    assert RESET_MODULE.DEMO_HR_EMAIL == "hr.demo@ttc.local"
    assert RESET_MODULE.DEMO_CANDIDATE_EMAIL == "demo.candidate@ttc.local"
    assert RESET_MODULE.DEMO_PASSWORD == "SeedDemo#2026"
