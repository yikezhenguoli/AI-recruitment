import re
from datetime import UTC, datetime

PRESENT = ("至今", "现在", "present", "current")
START_KEYS = ("start", "start_date", "start_year", "from", "from_year")
END_KEYS = ("end", "end_date", "end_year", "to", "to_year")
# 抽取模型对这些键的命名并不统一（实测同一份简历里有 start/end 也有
# start_year/end_year），所以按别名逐个尝试，认不出就当作没有时间。
_MONTH = re.compile(r"\s*(\d{4})\s*[-/.年]\s*(\d{1,2})(?:\s*[-/.月]\s*\d{1,2}\s*日?)?\s*")
_YEAR = re.compile(r"\s*(\d{4})\s*年?\s*")


def _pick(normalized, keys):
    for key in keys:
        value = normalized.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def parse_period(value, bound="start"):
    """把时间值解析成 (排序用月序号, 展示文本)；认不出返回 (None, None)。

    只给年份时按整年计：起点落在 1 月、终点落在 12 月，避免"2021 年入职"
    与"2021 年毕业"被判成零重叠。
    """
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        return None, None
    text = value.strip()
    if not text:
        return None, None
    if text.casefold() in PRESENT:
        now = datetime.now(UTC)
        return now.year * 12 + now.month - 1, "至今"
    match = _MONTH.fullmatch(text)
    if match and 1 <= int(match[2]) <= 12:
        year, month = int(match[1]), int(match[2])
        return year * 12 + month - 1, f"{year:04d}-{month:02d}"
    match = _YEAR.fullmatch(text)
    if match:
        year = int(match[1])
        return year * 12 + (11 if bound == "end" else 0), f"{year:04d}"
    return None, None


def period_of(normalized):
    start_index, start_text = parse_period(_pick(normalized, START_KEYS), "start")
    end_index, end_text = parse_period(_pick(normalized, END_KEYS), "end")
    return start_index, start_text, end_index, end_text


def _is_year_only(text):
    return isinstance(text, str) and len(text) == 4 and text.isdigit()


def _flag_overlap(left_start, left_end, right_start, right_end, coarse):
    """只有年份的时间跨度精度是 ±1 年，重叠不到 12 个月不构成"时间重叠"。

    "2015-2019 读本科、2019 入职"与"2021 换工作"这类边界年同框是正常路径，
    按月份直接算会得到整年重叠，进而弹出假告警。
    """
    overlap = min(left_end, right_end) - max(left_start, right_start) + 1
    return overlap > (12 if coarse else 0)


def build_timeline(claims):
    kinds = {"work", "education", "project", "publication", "patent"}
    items = []
    for claim in claims:
        if claim["type"] not in kinds:
            continue
        start_index, start_text, end_index, end_text = period_of(claim["normalized"])
        reversed_span = (start_index is not None and end_index is not None
                         and start_index > end_index)
        items.append({"claim_id": claim["id"], "type": claim["type"],
                      "start": start_text, "end": end_text,
                      "needs_review": bool(claim["needs_review"]) or reversed_span})
    timed = []
    for claim in claims:
        if claim["type"] not in kinds:
            continue
        start_index, start_text, end_index, end_text = period_of(claim["normalized"])
        if start_index is not None and end_index is not None and start_index <= end_index:
            coarse = _is_year_only(start_text) or _is_year_only(end_text)
            timed.append((start_index, end_index, coarse, claim))
    timed.sort(key=lambda item: item[0])
    conflicts = []
    for offset, (start, end, coarse_left, left) in enumerate(timed):
        for right_start, right_end, coarse_right, right in timed[offset + 1:]:
            if right_start > end:
                break
            if not _flag_overlap(start, end, right_start, right_end,
                                 coarse_left or coarse_right):
                continue
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
    spans = sorted((start, end) for start, end, coarse, claim in timed
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
