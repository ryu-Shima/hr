"\"\"\"Pydantic schema definitions for provider-neutral data structures.\"\"\""

from __future__ import annotations

from .candidate import (
    CandidateProfile,
    CandidateSkillAggregate,
    CandidateConstraints,
    ExperienceEntry,
    EducationEntry,
    LanguageProficiency,
)
from .job import JobDescription

__all__ = [
    "CandidateProfile",
    "CandidateSkillAggregate",
    "CandidateConstraints",
    "JobDescription",
    "LanguageProficiency",
    "ExperienceEntry",
    "EducationEntry",
]
