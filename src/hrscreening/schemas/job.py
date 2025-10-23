from __future__ import annotations

from __future__ import annotations

from typing import Any

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SalaryRange(BaseModel):
    """Salary range for a job opportunity."""

    min_jpy: int | None = None
    max_jpy: int | None = None

    model_config = ConfigDict(extra="forbid")


class JobConstraints(BaseModel):
    """Hard requirements attached to a job description."""

    language: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    visa: str | None = None
    salary_range: SalaryRange | None = None

    model_config = ConfigDict(extra="forbid")


class JobDescription(BaseModel):
    """Provider-neutral job description schema."""

    job_id: str
    locale: str | None = None
    role_titles: list[str] = Field(default_factory=list)
    requirements_text: list[str] = Field(default_factory=list)
    key_phrases: list[str] = Field(default_factory=list)
    constraints: JobConstraints = Field(default_factory=JobConstraints)
    evaluation_overrides: dict[str, Any] = Field(default_factory=dict)
    evaluation_overrides: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")
