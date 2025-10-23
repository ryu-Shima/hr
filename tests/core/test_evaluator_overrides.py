from __future__ import annotations

import pytest

from hrscreening.core.evaluators.jd_matcher import JDMatcher
from hrscreening.core.evaluators.salary import SalaryEvaluator
from hrscreening.schemas import CandidateProfile, ExperienceEntry, JobDescription


def test_salary_evaluator_respects_tolerance_override():
    evaluator = SalaryEvaluator()
    candidate = CandidateProfile(
        provider="test",
        candidate_id="C-override",
        desired_salary_min_jpy=13_000_000,
        desired_salary_max_jpy=14_000_000,
    )
    job = JobDescription(
        job_id="JD-override",
        constraints={"salary_range": {"min_jpy": 7_000_000, "max_jpy": 12_000_000}},
    )

    context = {
        "job": job.model_dump(mode="python"),
        "evaluation_overrides": {"salary": {"tolerance_ratio": 0.25}},
    }

    result = evaluator.evaluate(candidate.model_dump(mode="python"), context)

    assert result["scores"]["salary_pass"] == 1.0
    assert result["metadata"]["tolerance_ratio"] == pytest.approx(0.25)


def test_jd_matcher_uses_keyword_overrides():
    evaluator = JDMatcher()
    candidate = CandidateProfile(
        provider="test",
        candidate_id="C-jd",
        experiences=[
            ExperienceEntry(
                company="Example",
                title="カスタマーサクセス リード",
                summary="顧客課題を定義しオンボーディングプロジェクトを推進、生成AI 支援施策を企画",
            )
        ],
    )
    job = JobDescription(job_id="JD-jd")

    overrides = {
        "jd_keywords": {
            "must": ["顧客課題", "オンボーディング"],
            "nice": ["生成AI"],
            "nice_to_have": ["プロジェクト"],
            "weights": {"must": 1.0, "nice": 0.75, "nice_to_have": 0.5},
            "title_bonus": 0.2,
        }
    }
    context = {
        "job": job.model_dump(mode="python"),
        "evaluation_overrides": overrides,
    }

    result = evaluator.evaluate(candidate.model_dump(mode="python"), context)

    assert result["scores"]["jd_pass"] == 1.0
    assert result["metadata"]["weights"] == {"must": 1.0, "nice": 0.75, "nice_to_have": 0.5}
    assert result["scores"]["title_bonus"] == pytest.approx(0.2)
    assert result["metadata"]["hits"]["must"] == ["顧客課題", "オンボーディング"]
    assert result["metadata"]["hits"]["nice"] == ["生成AI"]


def test_salary_evaluator_neutral_when_insufficient():
    evaluator = SalaryEvaluator()
    candidate = CandidateProfile(provider="test", candidate_id="C-neutral")
    job = JobDescription(
        job_id="JD-neutral",
        constraints={"salary_range": {"min_jpy": 7_000_000, "max_jpy": 12_000_000}},
    )
    context = {"job": job.model_dump(mode="python"), "evaluation_overrides": {}}

    result = evaluator.evaluate(candidate.model_dump(mode="python"), context)

    assert result["scores"]["salary_pass"] == pytest.approx(0.5)
    assert result["metadata"]["status"] == "insufficient_data"
