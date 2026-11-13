from ttc.domains.resume.timeline import build_timeline


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
