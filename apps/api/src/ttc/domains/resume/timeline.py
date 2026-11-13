import re
from datetime import UTC, datetime


def month_index(value):
    if not isinstance(value, str):
        return None
    if value.strip() in ("至今", "现在", "present", "current"):
        now = datetime.now(UTC)
        return now.year * 12 + now.month - 1
    match = re.fullmatch(r"\s*(\d{4})[-/.年](\d{1,2})(?:[-/.月]\d{1,2}日?)?\s*", value)
    if not match or not 1 <= int(match[2]) <= 12:
        return None
    return int(match[1]) * 12 + int(match[2]) - 1


def build_timeline(claims):
    kinds = {"work", "education", "project", "publication", "patent"}
    items = []
    for claim in claims:
        if claim["type"] not in kinds:
            continue
        normalized = claim["normalized"]
        start = month_index(normalized.get("start"))
        end = month_index(normalized.get("end"))
        if start is not None and end is not None and start > end:
            items.append({"claim_id": claim["id"], "type": claim["type"],
                          "start": normalized.get("start"), "end": normalized.get("end"),
                          "needs_review": True})
            continue
        items.append({"claim_id": claim["id"], "type": claim["type"],
                      "start": normalized.get("start"), "end": normalized.get("end"),
                      "needs_review": bool(claim["needs_review"])})
    timed = []
    for claim in claims:
        if claim["type"] not in kinds:
            continue
        start = month_index(claim["normalized"].get("start"))
        end = month_index(claim["normalized"].get("end"))
        if start is not None and end is not None and start <= end:
            timed.append((start, end, claim))
    timed.sort(key=lambda item: item[0])
    conflicts = []
    for offset, (start, end, left) in enumerate(timed):
        for right_start, right_end, right in timed[offset + 1:]:
            if right_start > end:
                break
            left_full = left["normalized"].get("employment_type") == "full_time"
            right_full = right["normalized"].get("employment_type") == "full_time"
            study_work = {left["type"], right["type"]} == {"education", "work"}
            study = left if left["type"] == "education" else right
            full_time_study = study["normalized"].get("study_mode") == "full_time"
            kind = ("full_time_jobs" if left["type"] == right["type"] == "work" and
                    left_full and right_full else
                    "full_time_study_and_work" if study_work and full_time_study and
                    (left_full or right_full) else "overlap")
            conflicts.append({"type": kind, "claim_ids": [left["id"], right["id"]],
                              "start_month": max(start, right_start),
                              "end_month": min(end, right_end),
                              "note": "仅提示人工核对，重叠不等于简历造假"})
    spans = sorted((start, end) for start, end, claim in timed
                   if claim["type"] in ("work", "education", "project"))
    gaps = []
    if spans:
        latest = spans[0][1]
        for start, end in spans[1:]:
            if start - latest - 1 > 6:
                gaps.append({"from_month": latest + 1, "to_month": start - 1,
                             "months": start - latest - 1, "note": "存在空档，仅供人工核对"})
            latest = max(latest, end)
    return {"items": items, "conflicts": conflicts, "gaps": gaps}
