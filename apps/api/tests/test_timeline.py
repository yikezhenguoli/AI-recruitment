from ttc.domains.resume.timeline import build_timeline


def claim(claim_id, kind, **normalized):
    return {"id": claim_id, "type": kind, "needs_review": False, "normalized": normalized}


def test_timeline_reads_year_only_fields_the_extractor_actually_emits():
    report = build_timeline([claim("job", "work", title="后端", start_year=2019, end_year=2021)])
    assert report["items"][0]["start"] == "2019"
    assert report["items"][0]["end"] == "2021"


def test_timeline_keeps_month_precision_when_present():
    report = build_timeline([claim("job", "work", start="2019-03", end="2021/07")])
    assert (report["items"][0]["start"], report["items"][0]["end"]) == ("2019-03", "2021-07")


def test_timeline_marks_missing_dates_as_unknown_instead_of_present():
    report = build_timeline([claim("bullet", "work", title="负责订单服务")])
    assert report["items"][0]["start"] is None
    assert report["items"][0]["end"] is None


def test_year_only_boundary_years_are_not_reported_as_overlap():
    report = build_timeline([
        claim("study", "education", start="2015", end="2019", study_mode="full_time"),
        claim("first", "work", start="2019", end="2021", employment_type="full_time"),
        claim("second", "work", start="2021", end="2025", employment_type="full_time"),
    ])
    assert report["conflicts"] == []


def test_year_only_spans_still_report_a_real_multi_year_overlap():
    report = build_timeline([
        claim("a", "work", start="2019", end="2023", employment_type="full_time"),
        claim("b", "work", start="2020", end="2022", employment_type="full_time"),
    ])
    assert report["conflicts"][0]["type"] == "full_time_jobs"


def test_timeline_reports_overlap_without_accusation_and_long_gaps():
    claims = [
        {"id": "study", "type": "education", "needs_review": False,
         "normalized": {"start": "2020-01", "end": "2021-12", "study_mode": "full_time"}},
        {"id": "job", "type": "work", "needs_review": False,
         "normalized": {"start": "2021-01", "end": "2021-06",
                        "employment_type": "full_time"}},
        {"id": "later", "type": "work", "needs_review": False,
         "normalized": {"start": "2023-01", "end": "2024-01"}},
    ]
    report = build_timeline(claims)
    assert report["conflicts"][0]["type"] == "full_time_study_and_work"
    assert report["gaps"][0]["months"] == 12
    assert all("造假" not in item["note"] for item in report["gaps"])
