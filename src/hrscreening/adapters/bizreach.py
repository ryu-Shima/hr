"\"\"\"BizReach resume adapter.\"\"\""

from __future__ import annotations

import json
from typing import Any

from ..schemas import (
    CandidateProfile,
    EducationEntry,
    ExperienceEntry,
    LanguageProficiency,
)


class BizReachAdapter:
    """Adapter converting BizReach JSON payloads into CandidateProfile dicts."""

    provider = "bizreach"

    def can_handle(self, blob: bytes | str, metadata: dict[str, Any]) -> bool:
        provider = metadata.get("provider")
        if provider and provider.lower() == self.provider:
            return True
        try:
            data = self._load(blob)
        except ValueError:
            return False
        return str(data.get("provider", "")).lower() == self.provider

    def split_candidates(self, text: str) -> list[str]:
        return [text]

    def parse_candidate(self, section: str) -> dict[str, Any]:
        data = self._load(section)
        payload = data.get("payload", data)

        experiences = [
            ExperienceEntry(
                company=item.get("company", ""),
                title=item.get("title", ""),
                start=item.get("start"),
                end=item.get("end"),
                employment_type=item.get("employment_type"),
                summary=item.get("summary", ""),
                bullets=item.get("bullets", []),
            )
            for item in payload.get("experiences", [])
        ]

        languages = [
            LanguageProficiency(
                language=entry.get("language", ""),
                level=entry.get("level"),
            )
            for entry in payload.get("languages", [])
        ]

        education = [
            EducationEntry(
                school=item.get("school", ""),
                major=item.get("major"),
                degree=item.get("degree"),
                start=item.get("start"),
                end=item.get("end"),
            )
            for item in payload.get("education", [])
        ]

        candidate = CandidateProfile(
            provider=self.provider,
            candidate_id=payload.get("candidate_id", ""),
            name=payload.get("name"),
            desired_salary_min_jpy=payload.get("desired_salary_min_jpy"),
            desired_salary_max_jpy=payload.get("desired_salary_max_jpy"),
            experiences=experiences,
            skills=payload.get("skills", []),
            languages=languages,
            education=education,
            constraints=payload.get("constraints"),
        )

        return candidate.model_dump(mode="python")

    @staticmethod
    def _load(blob: bytes | str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(blob, dict):
            return blob
        if isinstance(blob, bytes):
            blob = blob.decode("utf-8")
        try:
            return json.loads(blob)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid BizReach payload") from exc

