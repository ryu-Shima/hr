from __future__ import annotations

from hrscreening.core.evaluators.salary import SalaryEvaluator
from hrscreening.schemas import CandidateProfile, JobDescription


def build_candidate(min_salary: int | None, max_salary: int | None) -> dict:
    profile = CandidateProfile(
        provider="test",
        candidate_id="C-200",
        desired_salary_min_jpy=min_salary,
        desired_salary_max_jpy=max_salary,
    )
    return profile.model_dump(mode="python")


def build_job(min_salary: int | None, max_salary: int | None) -> dict:
    job = JobDescription(
        job_id="JD-200",
        constraints={"salary_range": {"min_jpy": min_salary, "max_jpy": max_salary}},
    )
    return job.model_dump(mode="python")


def test_salary_overlap_within_tolerance_passes():
    evaluator = SalaryEvaluator()
    candidate = build_candidate(8_000_000, 10_000_000)
    job = build_job(7_000_000, 12_000_000)

    result = evaluator.evaluate(candidate, {"job": job})

    assert result["scores"]["salary_pass"] == 1.0
    assert result["metadata"]["overlap_span"] > 0


def test_salary_outside_tolerance_fails():
    evaluator = SalaryEvaluator()
    candidate = build_candidate(15_000_000, 16_000_000)
    job = build_job(7_000_000, 9_000_000)

    outcome = evaluator.evaluate(candidate, {"job": job})

    assert outcome["scores"]["salary_pass"] == 0.0
    assert outcome["metadata"]["overlap_span"] is None


def test_salary_missing_candidate_range_passes_by_default():
    evaluator = SalaryEvaluator()
    candidate = build_candidate(None, None)
    job = build_job(7_000_000, 10_000_000)

    result = evaluator.evaluate(candidate, {"job": job})

    assert result["scores"]["salary_pass"] == 1.0
    assert result["metadata"]["message"] == "insufficient_data"

