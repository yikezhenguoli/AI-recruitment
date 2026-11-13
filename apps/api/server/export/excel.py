"""Generate Excel export with ranking and screening details."""
from __future__ import annotations

import io
import json
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from models.schemas import ProcessedCandidateRecord


_HEADER_FILL = PatternFill(start_color="1A1A2E", end_color="1A1A2E", fill_type="solid")
_HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
_DATA_FONT = Font(name="Calibri", size=10)
_ALT_FILL = PatternFill(start_color="F0F4FF", end_color="F0F4FF", fill_type="solid")
_THIN = Side(border_style="thin", color="D0D0D0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

HEADERS = [
    "Name",
    "Email",
    "Phone",
    "Score",
    "Outcome",
    "Reason",
    "Graduation Year",
    "Grad Year Source",
    "Explanation",
    "Location",
    "Skills",
    "Education",
    "Work Experience",
    "Projects",
    "Publications",
    "Certifications",
    "Additional Info",
]
COL_WIDTHS = [28, 34, 18, 10, 14, 42, 16, 16, 80, 24, 36, 44, 56, 44, 34, 34, 30]


def generate_excel(records: list[ProcessedCandidateRecord]) -> bytes:
    """
    Build an Excel workbook from candidate results with screening outcomes.
    Returns raw bytes ready to be streamed as a download.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Candidate Rankings"

    # ── Header row ─────────────────────────────────────────────────────────────
    for col_idx, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDER

    ws.row_dimensions[1].height = 22

    # ── Data rows ──────────────────────────────────────────────────────────────
    sorted_records = sorted(records, key=_sort_key)

    for row_idx, record in enumerate(sorted_records, start=2):
        candidate = record.candidate
        resume = record.resume_structured
        name = candidate.name or "—"
        email = candidate.email or "—"
        phone = candidate.phone or "—"
        score = candidate.score if candidate.score is not None else "—"
        outcome = _format_outcome(candidate)
        reason = candidate.screening_reason or candidate.error or "—"
        graduation_year = (
            candidate.graduation_year_info.graduation_year
            if candidate.graduation_year_info.graduation_year is not None
            else "—"
        )
        graduation_source = candidate.graduation_year_info.source.replace("_", " ").title()
        explanation = _merge_explanation(candidate.explanation)
        location = resume.personal_info.location or "—"
        skills = _join_lines(resume.skills)
        education = _format_education(resume.education)
        work_experience = _format_work_experience(resume.work_experience)
        projects = _format_projects(resume.projects)
        publications = _format_publications(resume.publications)
        certifications = _format_certifications(resume.certifications)
        additional_info = _format_additional_info(resume.additional_info)

        row_data = [
            name,
            email,
            phone,
            score,
            outcome,
            reason,
            graduation_year,
            graduation_source,
            explanation,
            location,
            skills,
            education,
            work_experience,
            projects,
            publications,
            certifications,
            additional_info,
        ]
        fill = _ALT_FILL if row_idx % 2 == 0 else None

        for col_idx, value in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = _DATA_FONT
            cell.border = _BORDER
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
                horizontal="center" if col_idx == 4 else "left",
            )
            if fill:
                cell.fill = fill

        ws.row_dimensions[row_idx].height = 96

    # ── Column widths ──────────────────────────────────────────────────────────
    for col_idx, width in enumerate(COL_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # ── Freeze header ──────────────────────────────────────────────────────────
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _merge_explanation(bullets: list[str]) -> str:
    if not bullets:
        return "—"
    return "\n".join(f"• {b.lstrip('•').strip()}" for b in bullets)


def _join_lines(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return "\n".join(cleaned) if cleaned else "—"


def _format_education(entries: list) -> str:
    blocks = []
    for entry in entries:
        lines = []
        title = _join_parts([entry.degree, entry.field], " in ")
        if title:
            lines.append(title)
        if entry.institution:
            lines.append(entry.institution)
        meta = _join_parts(
            [
                f"GPA: {entry.score_gpa}" if entry.score_gpa else None,
                _format_date_range(entry.start_date, entry.end_date),
            ],
            " | ",
        )
        if meta:
            lines.append(meta)
        if lines:
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "—"


def _format_work_experience(entries: list) -> str:
    blocks = []
    for entry in entries:
        lines = []
        title = _join_parts([entry.role, entry.organization], " @ ")
        if title:
            lines.append(title)
        date_range = _format_date_range(entry.start_date, entry.end_date)
        if date_range:
            lines.append(date_range)
        responsibilities = _join_lines(entry.responsibilities)
        if responsibilities != "—":
            lines.append(responsibilities)
        if lines:
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "—"


def _format_projects(entries: list) -> str:
    blocks = []
    for entry in entries:
        lines = []
        if entry.name:
            lines.append(entry.name)
        if entry.description:
            lines.append(entry.description)
        technologies = ", ".join(item.strip() for item in entry.technologies if item and item.strip())
        if technologies:
            lines.append(f"Tech: {technologies}")
        if lines:
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "—"


def _format_publications(entries: list) -> str:
    blocks = []
    for entry in entries:
        line = _join_parts([entry.title, entry.journal, entry.year], " | ")
        if line:
            blocks.append(line)
    return "\n".join(blocks) if blocks else "—"


def _format_certifications(entries: list) -> str:
    blocks = []
    for entry in entries:
        line = _join_parts([entry.name, entry.issuer, entry.date], " | ")
        if line:
            blocks.append(line)
    return "\n".join(blocks) if blocks else "—"


def _format_additional_info(data: dict) -> str:
    if not data:
        return "—"
    return json.dumps(data, ensure_ascii=False, indent=2)


def _join_parts(parts: list[str | None], separator: str) -> str:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    return separator.join(cleaned)


def _format_date_range(start: str | None, end: str | None) -> str:
    if start and end:
        return f"{start} - {end}"
    return start or end or ""


def _format_outcome(candidate) -> str:
    if candidate.stage == "done":
        return "Ranked"
    if candidate.stage == "filtered":
        return "Filtered"
    if candidate.stage == "review":
        return "Manual Review"
    if candidate.stage == "skipped":
        return "Duplicate"
    if candidate.stage == "error":
        return "Error"
    return candidate.stage.replace("_", " ").title()


def _sort_key(record: ProcessedCandidateRecord) -> tuple[int, int]:
    candidate = record.candidate
    ranked_priority = 0 if candidate.stage == "done" else 1
    score = -(candidate.score or 0) if candidate.stage == "done" else 0
    return ranked_priority, score
