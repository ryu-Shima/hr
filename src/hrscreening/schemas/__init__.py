"\"\"\"Pydantic schema definitions for provider-neutral data structures.\"\"\""

from __future__ import annotations

from .candidate import (
    CandidateProfile,
    CandidateSkillAggregate,
    LanguageProficiency,
)
from .job import JobDescription

__all__ = [
    "CandidateProfile",
    "CandidateSkillAggregate",
    "JobDescription",
    "LanguageProficiency",
]
