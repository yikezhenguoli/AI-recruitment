"""Disk-backed persistence for named saved job profiles."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from models.schemas import (
    JobDescriptionStructured,
    SavedJobProfile,
    SavedJobProfileSummary,
    ScoringSchema,
)


class SavedJobConflictError(ValueError):
    """Raised when attempting to save a duplicate job profile name."""


class SavedJobStore:
    def __init__(self, path: str):
        self.path = Path(path)

    def list_jobs(self) -> list[SavedJobProfileSummary]:
        data = self._load()
        jobs = [
            SavedJobProfileSummary(
                name=item["name"],
                role_title=item["structured"]["role_title"],
                updated_at=item["updated_at"],
            )
            for item in data.values()
        ]
        return sorted(jobs, key=lambda item: (item.updated_at, item.name.lower()), reverse=True)

    def get_job(self, name: str) -> SavedJobProfile | None:
        key = self._normalize_name(name)
        data = self._load()
        item = data.get(key)
        if not item:
            return None
        return SavedJobProfile(**item)

    def save_job(
        self,
        name: str,
        jd_text: str,
        structured: JobDescriptionStructured,
        scoring_schema: ScoringSchema,
    ) -> SavedJobProfile:
        key = self._normalize_name(name)
        data = self._load()
        if key in data:
            raise SavedJobConflictError(f"A saved job named '{name.strip()}' already exists")

        now = datetime.now(timezone.utc).isoformat()
        profile = SavedJobProfile(
            name=name.strip(),
            jd_text=jd_text,
            structured=structured,
            scoring_schema=scoring_schema,
            created_at=now,
            updated_at=now,
        )
        data[key] = profile.model_dump()
        self._write(data)
        return profile

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def _write(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)

    @staticmethod
    def _normalize_name(name: str) -> str:
        return name.strip().lower()
