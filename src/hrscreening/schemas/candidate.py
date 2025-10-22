from __future__ import annotations

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderIdentifiers(BaseModel):
    """Identifier mapping for resume providers."""

    primary: str | None = None
    others: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ContactInfo(BaseModel):
    """Contact channels for a candidate."""

    email: str | None = None
    phone: str | None = None

    model_config = ConfigDict(extra="forbid")


class EducationEntry(BaseModel):
    """Structured education history entry."""

    school: str = ""
    major: str | None = None
    degree: str | None = None
    start: str | None = None
    end: str | None = None

    model_config = ConfigDict(extra="forbid")


class ExperienceEntry(BaseModel):
    """Employment history entry."""

    company: str = ""
    title: str = ""
    start: str | None = None
    end: str | None = None
    employment_type: str | None = None
    summary: str = ""
    bullets: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class LanguageProficiency(BaseModel):
    """Language proficiency descriptor."""

    language: str
    level: str | None = None

    model_config = ConfigDict(extra="forbid")


class ManagementExperience(BaseModel):
    """Managerial background metadata."""

    has_experience: bool = False
    team_size_range: str | None = None

    model_config = ConfigDict(extra="forbid")


class ProviderRawPayload(BaseModel):
    """Raw provider payload snapshot."""

    text: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class CandidateSkillAggregate(BaseModel):
    """Aggregated skill metadata."""

    years: float | None = None
    last_used: str | None = None

    model_config = ConfigDict(extra="forbid")


class CandidateConstraints(BaseModel):
    """Candidate-specific hard constraints."""

    language: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    visa: str | None = None

    model_config = ConfigDict(extra="forbid")


class CandidateProfile(BaseModel):
    """Provider-neutral candidate document."""

    provider: str
    candidate_id: str
    provider_ids: ProviderIdentifiers = Field(
        default_factory=ProviderIdentifiers
    )
    name: str | None = None
    gender: str | None = None
    age: int | None = None
    location: str | None = None
    contact: ContactInfo = Field(default_factory=ContactInfo)
    education: list[EducationEntry] = Field(default_factory=list)
    experiences: list[ExperienceEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    languages: list[LanguageProficiency] = Field(default_factory=list)
    current_salary_min_jpy: int | None = None
    current_salary_max_jpy: int | None = None
    desired_salary_min_jpy: int | None = None
    desired_salary_max_jpy: int | None = None
    management_experience: ManagementExperience = Field(
        default_factory=ManagementExperience
    )
    awards: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    notes: str | None = None
    skills_agg: dict[str, CandidateSkillAggregate] = Field(default_factory=dict)
    languages_detail: list[LanguageProficiency] | None = None
    constraints: CandidateConstraints | None = None
    provider_raw: ProviderRawPayload = Field(default_factory=ProviderRawPayload)

    model_config = ConfigDict(extra="allow")

