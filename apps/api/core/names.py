"""Display-only person-name formatting.

The resume model separates first_name / last_name. For CJK names the LLM often
puts the surname in last_name and the given name in first_name, so the Western
"first last" order reads backwards. This helper only formats the display name;
it does not change extraction, scoring, or any stored structured fields.
"""
from __future__ import annotations

import re

_CJK = re.compile(r"[㐀-䶿一-鿿]")


def format_person_name(first: str | None, last: str | None) -> str | None:
    first_name = (first or "").strip()
    last_name = (last or "").strip()

    if not first_name:
        return last_name or None
    if not last_name:
        return first_name

    if _CJK.search(first_name) and _CJK.search(last_name):
        return f"{last_name}{first_name}"

    return f"{first_name} {last_name}"
