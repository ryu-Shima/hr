from __future__ import annotations

import pytest
from pydantic import ValidationError

from hrscreening.schemas import CandidateProfile, CandidateSkillAggregate, JobDescription


def test_candidate_profile_defaults():
    profile = CandidateProfile(provider="bizreach", candidate_id="C-001")

    assert profile.provider == "bizreach"
    assert profile.provider_ids.primary is None
    assert profile.provider_ids.others == {}
    assert profile.education == []
    assert profile.experiences == []
    assert profile.skills == []
    assert profile.languages == []
    assert profile.management_experience.has_experience is False
    assert profile.management_experience.team_size_range is None
    assert profile.provider_raw.text is None
    assert profile.provider_raw.fields == {}


def test_candidate_profile_skill_aggregate_mapping():
    profile = CandidateProfile(
        provider="green",
        candidate_id="C-002",
        skills_agg={
            "Terraform": {"years": 2.5, "last_used": "2025-06"},
            "AWS": CandidateSkillAggregate(years=3.0, last_used="2025-09"),
        },
    )

    assert isinstance(profile.skills_agg["Terraform"], CandidateSkillAggregate)
    assert profile.skills_agg["Terraform"].years == pytest.approx(2.5)
    assert profile.skills_agg["AWS"].last_used == "2025-09"


def test_candidate_profile_requires_provider():
    with pytest.raises(ValidationError):
        CandidateProfile(candidate_id="C-003")  # type: ignore[call-arg]


def test_job_description_defaults():
    jd = JobDescription(job_id="JD-123")

    assert jd.role_titles == []
    assert jd.requirements_text == []
    assert jd.key_phrases == []
    assert jd.constraints.language == []
    assert jd.constraints.location == []
    assert jd.constraints.salary_range is None

