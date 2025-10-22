from __future__ import annotations

from hrscreening.core.evaluators import JDMatcher
from hrscreening.schemas import CandidateProfile, ExperienceEntry, JobDescription


def build_candidate(experiences: list[dict], skills: list[str] | None = None) -> dict:
    profile = CandidateProfile(
        provider="test",
        candidate_id="C-300",
        experiences=[ExperienceEntry(**exp) for exp in experiences],
        skills=skills or [],
    )
    return profile.model_dump(mode="python")


def build_job(must: list[str], nice: list[str] | None = None) -> dict:
    job = JobDescription(
        job_id="JD-300",
        key_phrases=must,
        role_titles=nice or [],
    )
    return job.model_dump(mode="python")


def test_jd_matcher_passes_when_all_must_keywords_present():
    candidate = build_candidate(
        [
            {
                "company": "Acme",
                "title": "Site Reliability Engineer",
                "start": "2022-01",
                "end": "2024-12",
                "bullets": ["TerraformでAWS基盤をIaC化", "Prometheusで監視設計"],
            }
        ],
        skills=["AWS", "Terraform"],
    )
    job = build_job(["Terraform", "AWS", "Prometheus"])
    matcher = JDMatcher()

    result = matcher.evaluate(candidate, {"job": job})

    assert result["scores"]["jd_pass"] == 1.0
    assert result["metadata"]["must_hits"] == ["Terraform", "AWS", "Prometheus"]


def test_jd_matcher_fails_when_must_keyword_missing():
    candidate = build_candidate(
        [
            {
                "company": "Acme",
                "title": "Backend Engineer",
                "start": "2022-01",
                "end": "2024-12",
                "bullets": ["Python API 開発", "Docker 運用"],
            }
        ],
        skills=["Python", "Docker"],
    )
    job = build_job(["Terraform", "AWS"])
    matcher = JDMatcher()

    outcome = matcher.evaluate(candidate, {"job": job})

    assert outcome["scores"]["jd_pass"] == 0.0
    assert outcome["metadata"]["must_hits"] == []

